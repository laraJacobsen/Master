"""The penalty counter and the "likely spamming" flag (backend/hint_policy.py), and the
per-student numbers the lecturer's dashboard gets. Temporary DB only."""

from backend import store
from backend.hint_policy import HintPolicy, penalty, spam_reason
from tests.test_duplicates import WRONG_A, WRONG_B, judge_calls  # noqa: F401  (fixture)
from tests.test_hint_unlock import live, submit  # noqa: F401  (fixture)


def test_penalty_counts_wrong_attempts_after_the_free_ones():
    p = HintPolicy(free_attempts=1, penalty=True)
    assert penalty(p, []) == 0
    assert penalty(p, ["incorrect"]) == 0  # the free attempt
    assert penalty(p, ["incorrect", "incorrect", "partially_correct"]) == 2
    assert penalty(HintPolicy(free_attempts=0, penalty=True), ["error", "incorrect"]) == 2


def test_penalty_stops_at_the_first_correct_attempt():
    p = HintPolicy(free_attempts=1, penalty=True)
    assert penalty(p, ["incorrect", "incorrect", "correct", "incorrect", "incorrect"]) == 1


def test_spam_flag():
    assert spam_reason([0, 100, 200, 300, 400], 0) is None
    assert spam_reason([0, 10, 20, 30, 40], 0) == "5 submits within 60 s"
    assert spam_reason([40, 0, 30, 10, 20], 0) == "5 submits within 60 s"  # any order
    assert spam_reason([0, 100], 3) == "3 resubmissions of the same code"
    assert spam_reason([0, 100], 2) is None


def activity_row(client, qid, name="Ada"):
    rows = client.get(f"/api/lecturer/questions/{qid}/activity").json()
    return next(r for r in rows if r["student_name"] == name)


def test_dashboard_counts_and_flag(live, judge_calls):
    client, qid, headers = live
    submit(client, qid, headers, "")  # rejected before running
    submit(client, qid, headers, WRONG_A)
    for _ in range(3):
        submit(client, qid, headers, WRONG_A)  # duplicates
    submit(client, qid, headers, WRONG_B)
    row = activity_row(client, qid)
    assert (row["counted_attempts"], row["rejected"], row["duplicates"]) == (2, 1, 3)
    assert row["penalty"] is None  # the task doesn't show one
    assert row["spam"] == "3 resubmissions of the same code"


def test_penalty_shown_only_when_the_task_turns_it_on(live, judge_calls):
    client, qid, headers = live
    store.update_question(qid, {"hint_policy": {"free_attempts": 1, "unlock": "attempt", "penalty": True}})
    submit(client, qid, headers, WRONG_A)  # free
    r = submit(client, qid, headers, WRONG_B)
    assert r["hint_state"]["penalty"] == 1
    submit(client, qid, headers, WRONG_B)  # a duplicate adds nothing
    assert activity_row(client, qid)["penalty"] == 1
    state = client.get("/api/lecture/hint_state", params={"question_id": qid}, headers=headers).json()["state"]
    assert state["penalty"] == 1 and state["duplicates"] == 1
