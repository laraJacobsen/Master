"""Rate limits (backend/rate_limit.py) and where main.py's guard middleware and the
login/join routes apply them. Every test swaps in fresh limits on a fake clock, so
nothing here waits in real time."""

import pytest
from fastapi.testclient import TestClient

from backend import main, rate_limit, store
from backend.rate_limit import Limits, SlidingWindow, TokenBucket


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(rate_limit, "LIMITS", Limits.default(clock=c))
    monkeypatch.delenv("RATE_LIMITS", raising=False)
    return c


@pytest.fixture
def client():
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def lecture():
    """A live lecture with its lobby open (ending any other one first)."""
    active = store.get_active_lecture()
    if active:
        store.end_lecture(active["id"])
    lec = store.create_lecture("Rate limit tests")
    store.open_lobby(lec["id"])
    yield store.get_active_lecture()
    store.end_lecture(lec["id"])


# --- the two strategies -------------------------------------------------------

def test_token_bucket_bursts_then_refills():
    c = Clock()
    bucket = TokenBucket(3, 1, clock=c)
    assert [bucket.take("k") for _ in range(3)] == [0, 0, 0]
    assert bucket.take("k") == pytest.approx(1.0)  # empty: one token a second
    c.now += 0.5
    assert bucket.take("k") == pytest.approx(0.5)
    c.now += 0.5
    assert bucket.take("k") == 0
    assert bucket.take("other") == 0  # keys are independent
    c.now += 100
    assert [bucket.take("k") for _ in range(3)] == [0, 0, 0]  # refills only up to capacity
    assert bucket.take("k") > 0


def test_sliding_window_counts_only_recent_failures():
    c = Clock()
    window = SlidingWindow(3, 60, clock=c)
    for _ in range(3):
        assert window.retry_after("k") == 0
        window.record("k")
        c.now += 10
    assert window.retry_after("k") == pytest.approx(30)  # first failure was 30 s ago
    c.now += 30
    assert window.retry_after("k") == 0  # it slid out of the window
    window.record("k")
    assert window.retry_after("k") > 0
    window.reset("k")
    assert window.retry_after("k") == 0


def test_state_is_capped_per_limiter():
    bucket = TokenBucket(1, 0.001, max_keys=100, clock=Clock())
    for i in range(1000):
        bucket.take(f"spoofed-{i}")
    assert len(bucket._state) == 100


def test_llm_budget(clock, monkeypatch):
    for _ in range(rate_limit.LIMITS.llm_calls.capacity):
        rate_limit.take_llm_call()
    with pytest.raises(rate_limit.RateLimited):
        rate_limit.take_llm_call()
    clock.now += 2
    rate_limit.take_llm_call()
    monkeypatch.setenv("RATE_LIMITS", "off")
    for _ in range(500):
        rate_limit.take_llm_call()


# --- lecturer password ------------------------------------------------------

def test_login_locks_out_after_wrong_passwords(clock, client, monkeypatch):
    monkeypatch.setenv("LECTURER_PASSWORD", "right")
    monkeypatch.setattr(main.anyio, "sleep", _no_sleep)
    for _ in range(10):
        assert client.post("/api/lecturer/login", json={"password": "wrong"}).status_code == 401
    r = client.post("/api/lecturer/login", json={"password": "right"})
    assert r.status_code == 429, r.text  # even the right one: no oracle while locked
    assert int(r.headers["Retry-After"]) > 0 and "Try again in" in r.json()["detail"]
    clock.now += 15 * 60 + 1
    assert client.post("/api/lecturer/login", json={"password": "right"}).status_code == 200


def test_password_header_guesses_count_too(clock, client, monkeypatch):
    monkeypatch.setenv("LECTURER_PASSWORD", "right")
    monkeypatch.setattr(main.anyio, "sleep", _no_sleep)
    for _ in range(10):
        r = client.get("/api/lecturer/questions", headers={"X-Lecturer-Token": "guess"})
        assert r.status_code == 401
    assert client.get("/api/lecturer/questions", headers={"X-Lecturer-Token": "right"}).status_code == 429
    assert client.post("/api/lecturer/login", json={"password": "right"}).status_code == 429


def test_logged_in_lecturer_is_not_locked_out_by_guessers(clock, client, monkeypatch):
    monkeypatch.setenv("LECTURER_PASSWORD", "right")
    monkeypatch.setattr(main.anyio, "sleep", _no_sleep)
    assert client.post("/api/lecturer/login", json={"password": "right"}).status_code == 200
    for _ in range(150):  # trips the global window too
        client.post("/api/lecturer/login", json={"password": "wrong"})
    assert client.get("/api/lecturer/questions").status_code == 200  # session cookie still works


# --- joining ----------------------------------------------------------------

def test_wrong_join_codes_lock_out(clock, client, lecture):
    wrong = "000000" if lecture["join_code"] != "000000" else "111111"
    for _ in range(50):
        r = client.post("/api/lecture/join", json={"code": wrong, "student_name": "Bot"})
        assert r.status_code == 403
    r = client.post("/api/lecture/join", json={"code": lecture["join_code"], "student_name": "Real"})
    assert r.status_code == 429 and "wrong codes" in r.json()["detail"]
    clock.now += 10 * 60 + 1
    r = client.post("/api/lecture/join", json={"code": lecture["join_code"], "student_name": "Real"})
    assert r.status_code == 200


def test_a_whole_class_can_join_from_one_address_but_not_a_bot_army(clock, client, lecture):
    for i in range(400):  # one lecture hall behind one NAT address
        r = client.post("/api/lecture/join", json={"code": lecture["join_code"], "student_name": f"Student {i}"})
        assert r.status_code == 200, (i, r.text)
    r = client.post("/api/lecture/join", json={"code": lecture["join_code"], "student_name": "Bot 401"})
    assert r.status_code == 429
    clock.now += 5
    r = client.post("/api/lecture/join", json={"code": lecture["join_code"], "student_name": "Late student"})
    assert r.status_code == 200


# --- per-student request budgets ---------------------------------------------

def _join(client, lecture, name):
    r = client.post("/api/lecture/join", json={"code": lecture["join_code"], "student_name": name})
    assert r.status_code == 200, r.text
    return {"X-Student-Token": r.json()["token"]}


def test_runs_are_limited_per_student_not_per_address(clock, client, lecture):
    ada, bo = _join(client, lecture, "Ada"), _join(client, lecture, "Bo")
    body = {"question_id": "no-such-task", "source_code": "print(1)", "stdin": ""}
    for _ in range(10):
        assert client.post("/api/run", json=body, headers=ada).status_code != 429
    r = client.post("/api/run", json=body, headers=ada)
    assert r.status_code == 429 and "running code very quickly" in r.json()["detail"]
    assert client.post("/api/run", json=body, headers=bo).status_code != 429  # same address, own budget
    clock.now += 3
    assert client.post("/api/run", json=body, headers=ada).status_code != 429


def test_polling_student_stays_under_the_limit(clock, client, lecture):
    ada = _join(client, lecture, "Ada")
    for _ in range(600):  # 20 minutes of a 2 s status poll plus a 10 s heartbeat
        assert client.get("/api/lecture/status", headers=ada).status_code == 200
        clock.now += 2
    flood = [client.get("/api/lecture/status", headers=ada).status_code for _ in range(100)]
    assert 429 in flood


def test_made_up_tokens_fall_back_to_the_address_limit(clock, client):
    codes = [client.get("/api/lecture/status", headers={"X-Student-Token": f"fake-{i}"}).status_code
             for i in range(700)]
    assert codes.count(429) > 0


# --- AI routes and the off switch --------------------------------------------

def test_hint_drafts_are_limited(clock, client, monkeypatch):
    monkeypatch.delenv("LECTURER_PASSWORD", raising=False)
    monkeypatch.setattr(main, "draft_hint_ladder", lambda *a: ["a", "b", "c"])
    body = {"prompt": "p", "language": "python", "reference_solution": "print(1)"}
    for _ in range(5):
        assert client.post("/api/lecturer/hints/draft", json=body).status_code == 200
    r = client.post("/api/lecturer/hints/draft", json=body)
    assert r.status_code == 429 and "drafted several times" in r.json()["detail"]


def test_llm_budget_exhausted_gives_429_for_drafts(clock, client, monkeypatch):
    monkeypatch.delenv("LECTURER_PASSWORD", raising=False)

    def over_budget(*a):
        raise rate_limit.RateLimited(12)

    monkeypatch.setattr(main, "draft_hint_ladder", over_budget)
    body = {"prompt": "p", "language": "python", "reference_solution": "print(1)"}
    r = client.post("/api/lecturer/hints/draft", json=body)
    assert r.status_code == 429 and r.headers["Retry-After"] == "12"


def test_off_switch(clock, client, monkeypatch):
    monkeypatch.setenv("RATE_LIMITS", "off")
    codes = {client.get("/api/lecture/status").status_code for _ in range(1000)}
    assert codes == {200}


async def _no_sleep(_seconds):
    return None
