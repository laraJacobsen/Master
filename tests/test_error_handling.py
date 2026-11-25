"""What a client sees when something fails inside: a plain sentence, never exception
text, tracebacks, database errors, internal URLs or sandbox details -- those go to
the server log only (main.py's error helpers and handlers, judge0_client)."""

import logging
import sqlite3

import pytest
import requests
from fastapi.testclient import TestClient

from backend import judge0_client, main, store
from backend.judge0_client import Judge0Error

INTERNAL = "http://10.20.30.40:2358"  # stands in for any internal detail


@pytest.fixture
def client():
    # raise_server_exceptions=False: answer like the real server does, instead of
    # re-raising unhandled errors into the test.
    with TestClient(main.app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def caplog_server(caplog):
    caplog.set_level(logging.INFO, logger="uvicorn.error")
    return caplog


def _stdout_question():
    return store.create_question({
        "title": "Error handling", "prompt": "p", "language": "python", "reference_solution": "print(1)",
        "test_cases": [{"stdin": "", "expected_stdout": "1"}, {"stdin": "", "expected_stdout": "1"}],
    })


def test_judge0_down_is_a_plain_message(client, caplog_server, monkeypatch):
    def down(*a, **k):
        raise Judge0Error(f"Could not reach Judge0 at {INTERNAL}: HTTPConnectionPool(host='10.20.30.40')")

    monkeypatch.setattr(main, "run_test_cases", down)
    r = client.post(f"/api/lecturer/questions/{_stdout_question()}/validate")
    assert r.status_code == 502
    assert r.json() == {"detail": main.RUNNER_UNAVAILABLE}
    assert "10.20.30.40" in caplog_server.text  # the details are in the server log


def test_unhandled_database_error(client, caplog_server, monkeypatch):
    def broken(*a, **k):
        raise sqlite3.OperationalError("no such table: questions_internal_v2")

    monkeypatch.setattr(store, "list_question_rows", broken)
    r = client.get("/api/lecturer/questions")
    assert r.status_code == 500
    body = r.json()
    assert "questions_internal_v2" not in r.text and "Traceback" not in r.text and "sqlite" not in r.text.lower()
    assert body["error_id"] in body["detail"]
    assert body["error_id"] in caplog_server.text
    assert "questions_internal_v2" in caplog_server.text and "Traceback" in caplog_server.text


def test_invalid_request_names_fields_without_echoing_input(client):
    code = "print('my whole submission') " * 50
    r = client.post("/api/lecturer/run", json={"source_code": code})  # no question_id
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert isinstance(detail, str) and "question_id" in detail and "my whole submission" not in detail


def test_hint_draft_failure_hides_the_model_error(client, caplog_server, monkeypatch):
    def fails(*a):
        raise RuntimeError("Couldn't draft hints: 401 Client Error for url: https://llm.internal.example/v1")

    monkeypatch.setattr(main, "draft_hint_ladder", fails)
    r = client.post("/api/lecturer/hints/draft",
                    json={"prompt": "p", "language": "python", "reference_solution": "print(1)"})
    assert r.status_code == 502 and "llm.internal" not in r.text and "401" not in r.text
    assert "llm.internal.example" in caplog_server.text


def test_intentional_lecture_messages_still_reach_the_lecturer(client):
    active = store.get_active_lecture()
    if not active:
        store.create_lecture("Error handling")
    r = client.post("/api/lecturer/lectures", json={})
    assert r.status_code == 409 and r.json()["detail"] == "A lecture is already in progress."


def test_internal_error_helper_logs_traceback_and_hides_it(caplog_server):
    try:
        raise KeyError("internal_state_key")
    except KeyError:
        e = main._internal_error("grading feedback failed")
    assert e.status_code == 500 and "internal_state_key" not in e.detail
    assert "internal_state_key" in caplog_server.text and "Traceback" in caplog_server.text


class _Resp:
    def __init__(self, data=None, text=""):
        self._data, self.text = data, text

    def raise_for_status(self):
        pass

    def json(self):
        if self._data is None:
            raise ValueError("Expecting value")
        return self._data


def test_judge0_internal_error_message_is_replaced(caplog_server, monkeypatch):
    import base64
    sandbox = "Cannot open /var/local/lib/isolate/7/box: Permission denied"
    data = {"status": {"id": 13, "description": "Internal Error"},
            "message": base64.b64encode(sandbox.encode()).decode()}
    monkeypatch.setattr(judge0_client.requests, "post", lambda *a, **k: _Resp(data))
    result = judge0_client.run_submission("print(1)", "", language="python")
    assert "isolate" not in result["message"]
    assert "isolate" in caplog_server.text


def test_judge0_ordinary_message_is_kept(monkeypatch):
    import base64
    data = {"status": {"id": 11, "description": "Runtime Error (NZEC)"},
            "message": base64.b64encode(b"Exited with error status 1").decode()}
    monkeypatch.setattr(judge0_client.requests, "post", lambda *a, **k: _Resp(data))
    assert judge0_client.run_submission("x", "", language="python")["message"] == "Exited with error status 1"


def test_judge0_non_json_becomes_judge0_error(monkeypatch):
    monkeypatch.setattr(judge0_client.requests, "post", lambda *a, **k: _Resp(None, "<html>502 Bad Gateway</html>"))
    with pytest.raises(Judge0Error):
        judge0_client.run_submission("print(1)", "", language="python")
    monkeypatch.setattr(judge0_client.requests, "post",
                        lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError("refused")))
    with pytest.raises(Judge0Error):
        judge0_client.run_submission("print(1)", "", language="python")
