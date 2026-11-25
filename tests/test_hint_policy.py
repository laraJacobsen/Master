"""Per-task hint policy: validation, defaults, task.yaml and the setup API
(backend/hint_policy.py)."""

import pytest
from fastapi.testclient import TestClient

from backend import hint_policy, main, store
from backend import task_format as tf
from backend.task_import import question_fields, spec_of_question
from tests.test_task_format import TASK_YAML, pytest_task, problems_of


def test_defaults():
    p = hint_policy.DEFAULT
    assert (p.free_attempts, p.unlock, p.interval_seconds, p.duplicate_similarity, p.penalty) == (1, "both", 60, 1.0, False)
    assert hint_policy.from_dict(None) == p and hint_policy.from_dict({}) == p
    assert hint_policy.from_dict({"unlock": "timer"}).interval_seconds == 60  # missing keys take defaults


@pytest.mark.parametrize("raw, fragment", [
    ({"free_attempts": -1}, "free_attempts"),
    ({"free_attempts": 2.5}, "free_attempts"),
    ({"free_attempts": True}, "free_attempts"),
    ({"unlock": "sometimes"}, "unlock must be one of attempt, timer, both"),
    ({"interval_seconds": 99999}, "interval_seconds"),
    ({"duplicate_similarity": 0.2}, "duplicate_similarity"),
    ({"penalty": "yes"}, "penalty"),
    ({"hints": False}, "unknown key"),
    (["attempt"], "must be a mapping"),
])
def test_problems(raw, fragment):
    problems = hint_policy.problems_of(raw)
    assert problems and fragment in " ".join(problems)
    with pytest.raises(ValueError):
        hint_policy.from_dict(raw)


def test_old_question_gets_defaults():
    qid = store.create_question({"title": "No policy", "prompt": "p", "language": "python", "test_cases": []})
    assert store.get_question_row(qid)["hint_policy"] == hint_policy.DEFAULT.to_dict()


def test_task_yaml_block_round_trips():
    yaml = TASK_YAML + "hint_policy:\n  free_attempts: 2\n  unlock: timer\n  interval_seconds: 90\n  penalty: true\n"
    spec = tf.parse_task(pytest_task(**{"task.yaml": yaml}))
    assert spec.hint_policy == {"free_attempts": 2, "unlock": "timer", "interval_seconds": 90,
                                "duplicate_similarity": 1.0, "penalty": True}
    qid = store.create_question(question_fields(spec))
    row = store.get_question_row(qid)
    assert row["hint_policy"]["unlock"] == "timer"
    exported = tf.task_yaml(spec_of_question(row))
    assert "hint_policy:" in exported and "unlock: timer" in exported


def test_default_policy_is_not_written_on_export():
    spec = tf.parse_task(pytest_task())
    qid = store.create_question(question_fields(spec))
    assert "hint_policy" not in tf.task_yaml(spec_of_question(store.get_question_row(qid)))


def test_bad_task_yaml_block_is_a_format_problem():
    yaml = TASK_YAML + "hint_policy:\n  unlock: never\n"
    assert any("hint_policy: unlock must be one of" in p for p in problems_of(pytest_task(**{"task.yaml": yaml})))


def test_setup_api_validates_and_stores():
    with TestClient(main.app) as client:
        body = {"title": "Policy via API", "prompt": "p", "test_cases": [],
                "hint_policy": {"free_attempts": 0, "unlock": "attempt"}}
        r = client.post("/api/lecturer/questions", json=body)
        assert r.status_code == 200, r.text
        assert r.json()["hint_policy"] == {**hint_policy.DEFAULT.to_dict(), "free_attempts": 0, "unlock": "attempt"}
        qid = r.json()["id"]
        r = client.put(f"/api/lecturer/questions/{qid}", json={"hint_policy": {"interval_seconds": -5}})
        assert r.status_code == 400 and "interval_seconds" in r.json()["detail"]
        r = client.put(f"/api/lecturer/questions/{qid}", json={"hint_policy": {"penalty": True}})
        assert r.status_code == 200 and r.json()["hint_policy"]["penalty"] is True
