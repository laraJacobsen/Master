"""Hint unlocking (backend/hint_policy.py's hint_state()) and how the submit path,
the student's hint state and the lecturer's release use it. Temporary DB only
(tests/conftest.py)."""

import pytest
from fastapi.testclient import TestClient

from backend import hint_policy, main, rate_limit, store
from backend.hint_policy import HintPolicy, hint_state


def state(policy, attempts, now, releases=()):
    return hint_state(policy, list(attempts), list(releases), now)


# --- the replay ------------------------------------------------------------------

ATTEMPT = HintPolicy(free_attempts=1, unlock="attempt")
BOTH = HintPolicy(free_attempts=1, unlock="both", interval_seconds=60)
TIMER = HintPolicy(free_attempts=1, unlock="timer", interval_seconds=60)


def test_free_attempts_get_no_hint():
    s = state(HintPolicy(free_attempts=2), [0, 10], now=10)
    assert (s.level, s.counted_attempts, s.free_attempts_left, s.needs_attempt) == (0, 2, 1, True)
    assert state(HintPolicy(free_attempts=2), [0, 10, 20], now=20).level == 1
    assert state(HintPolicy(free_attempts=0), [0], now=0).level == 1


def test_attempt_mode_is_one_hint_per_counted_attempt():
    assert [state(ATTEMPT, [0, 1, 2, 3][:n], now=3).level for n in range(1, 5)] == [0, 1, 2, 3]


def test_both_needs_an_attempt_after_the_wait():
    attempts = [0, 10]  # hint 1 at 10
    s = state(BOTH, attempts + [30], now=40)  # too early: doesn't unlock
    assert (s.level, s.needs_attempt, s.unlock_at) == (1, True, 70)
    s = state(BOTH, attempts + [30], now=100)  # waited, but no attempt since
    assert (s.level, s.needs_attempt, s.unlock_at) == (1, True, None)
    s = state(BOTH, attempts + [30, 80], now=85)
    assert (s.level, s.unlock_at) == (2, 140)


def test_timer_unlocks_on_its_own_once_tried():
    attempts = [0, 10, 20]  # hint 1 at 10, a try at 20
    s = state(TIMER, attempts, now=50)
    assert (s.level, s.needs_attempt, s.unlock_at) == (1, False, 70)  # countdown, no new attempt needed
    s = state(TIMER, attempts, now=75)
    assert (s.level, s.needs_attempt, s.unlock_at) == (2, True, 130)  # unlocked at 70; next needs a try


def test_timer_never_unlocks_by_waiting_alone():
    s = state(TIMER, [0, 10], now=10_000)
    assert (s.level, s.needs_attempt) == (1, True)


def test_timer_attempt_after_the_due_time_unlocks_at_the_attempt():
    s = state(TIMER, [0, 10, 200], now=200)
    assert s.level == 2
    assert state(TIMER, [0, 10, 200], now=259).unlock_at == 260  # next due 60 s after 200


def test_attempts_while_waiting_dont_stack_in_timer_mode():
    s = state(TIMER, [0, 10, 20, 25, 30, 35], now=69)
    assert s.level == 1
    assert state(TIMER, [0, 10, 20, 25, 30, 35], now=131).level == 2  # one unlock at 70, none at 130


def test_release_unlocks_regardless_of_policy():
    s = state(BOTH, [], now=5, releases=[(5, 1)])
    assert (s.level, s.released_level, s.free_attempts_left) == (1, 1, 0)
    # Free attempt still doesn't escalate; the wait runs from the release.
    s = state(BOTH, [10, 30], now=30, releases=[(5, 1)])
    assert s.level == 1
    assert state(BOTH, [10, 70], now=70, releases=[(5, 1)]).level == 2


def test_release_never_lowers_a_level():
    s = state(ATTEMPT, [0, 1, 2, 3], now=4, releases=[(4, 1)])
    assert (s.level, s.released_level) == (3, 1)
    assert state(ATTEMPT, [], now=4, releases=[(1, 1), (2, 2)]).level == 2


# --- through the API ----------------------------------------------------------------

FAILING = [  # what run_test_cases() returns: the example passes, the graded test doesn't
    {"stdin": "1 2", "expected_stdout": "3", "stdout": "3\n", "stderr": "", "status_id": 3,
     "status_description": "Accepted", "exit_code": 0, "passed": True},
    {"stdin": "2 2", "expected_stdout": "4", "stdout": "5\n", "stderr": "", "status_id": 4,
     "status_description": "Wrong Answer", "exit_code": 0, "passed": False},
]


@pytest.fixture
def live(monkeypatch):
    """A live stdout task in an open lecture, Judge0 mocked to always answer wrong."""
    monkeypatch.setattr(rate_limit, "LIMITS", rate_limit.Limits.default())
    monkeypatch.setattr(main, "run_test_cases", lambda *a, **k: [dict(r) for r in FAILING])
    active = store.get_active_lecture()
    if active:
        store.end_lecture(active["id"])
    lecture = store.create_lecture("Hint unlock tests")
    store.open_lobby(lecture["id"])
    qid = store.create_question({
        "title": "Add two", "prompt": "Add the two numbers.", "language": "python",
        "test_cases": [{"stdin": "1 2", "expected_stdout": "3"}, {"stdin": "2 2", "expected_stdout": "4"}],
        "reference_solution": "a, b = map(int, input().split())\nprint(a + b)\n",
        "hint_policy": {"free_attempts": 1, "unlock": "attempt"},
    })
    store.update_question(qid, {"status": "live", "lecture_id": lecture["id"], "validated": 1})
    with TestClient(main.app) as client:
        token = store.join_student(lecture["id"], "Ada")["token"]
        yield client, qid, {"X-Student-Token": token}
    store.end_lecture(lecture["id"])


def submit(client, qid, headers, code):
    r = client.post("/api/submit", json={"question_id": qid, "source_code": code}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_rejected_submissions_dont_count(live):
    client, qid, headers = live
    r = submit(client, qid, headers, "   ")
    assert r["counted"] is False and r["not_counted_reason"] == "rejected"
    assert r["hint_state"]["counted_attempts"] == 0
    first = submit(client, qid, headers, "a, b = map(int, input().split())\nprint(a + b + 1)\n")
    assert first["counted"] is True and first["hint_tier"] == 0  # the free attempt
    assert first["hint_state"]["counted_attempts"] == 1
    second = submit(client, qid, headers, "a, b = map(int, input().split())\nprint(a * b + 1)\n")
    assert second["hint_tier"] == 1 and second["hint_state"]["level"] == 1


def test_lecturer_release_shows_the_next_hint_without_resubmitting(live):
    client, qid, headers = live
    submit(client, qid, headers, "a, b = map(int, input().split())\nprint(a + b + 1)\n")
    before = client.get("/api/lecture/hint_state", params={"question_id": qid}, headers=headers).json()
    assert before["state"]["level"] == 0 and before["hint"]["hint_tier"] == 0
    assert client.post(f"/api/lecturer/questions/{qid}/hint_release").json() == {"released_level": 1}
    after = client.get("/api/lecture/hint_state", params={"question_id": qid}, headers=headers).json()
    assert after["state"]["level"] == 1 and after["state"]["released_level"] == 1
    assert after["hint"]["hint_tier"] == 1 and after["hint"]["feedback"] != before["hint"]["feedback"]
    assert client.get(f"/api/lecturer/questions/{qid}/hint_release").json() == {"released_level": 1}


def test_release_only_while_live(live):
    client, qid, _ = live
    store.update_question(qid, {"status": "closed"})
    assert client.post(f"/api/lecturer/questions/{qid}/hint_release").status_code == 409


def test_policy_defaults_apply_to_existing_rows():
    assert hint_policy.of_question({"hint_policy": None}) == hint_policy.DEFAULT
