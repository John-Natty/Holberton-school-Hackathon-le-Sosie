import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import app.agent_state as agent_state


def test_default_state_is_running():
    assert agent_state.is_agent_running() is True
    assert agent_state.get_agent_state() == {"status": "running", "reason": None}


def test_stop_and_start_round_trip():
    agent_state.stop_agent("coupure test")
    assert agent_state.is_agent_running() is False
    assert agent_state.get_agent_state() == {"status": "stopped", "reason": "coupure test"}
    agent_state.start_agent()
    assert agent_state.is_agent_running() is True
    assert agent_state.get_agent_state()["reason"] is None


def test_stop_then_start_never_reactivates_an_old_execution():
    old_execution = agent_state.begin_agent_execution()
    assert old_execution is not None

    agent_state.stop_agent("invalidation")
    agent_state.start_agent()

    assert agent_state.is_execution_active(old_execution) is False
    with pytest.raises(agent_state.ExecutionCancelled):
        agent_state.ensure_execution_active(old_execution)
    assert agent_state.begin_agent_execution() is not None


def test_state_endpoints_round_trip(client):
    assert client.get("/agent/state").get_json() == {"status": "running", "reason": None}
    response = client.post("/agent/state", json={"status": "stopped", "reason": "maintenance"})
    assert response.get_json() == {"status": "stopped", "reason": "maintenance"}
    assert client.get("/agent/state").get_json()["status"] == "stopped"
    client.post("/agent/state", json={"status": "running"})
    assert client.get("/agent/state").get_json() == {"status": "running", "reason": None}


@pytest.mark.parametrize("body", [None, {}, {"status": "paused"}, {"status": 1}, []])
def test_state_endpoint_rejects_invalid_payload(client, body):
    assert client.post("/agent/state", json=body).status_code == 400


def test_chat_refused_cleanly_when_stopped(client, claude):
    agent_state.stop_agent("coupure test")
    response = client.post("/chat", json={"question": "Combien au total ?"})
    assert response.status_code == 503
    assert "arrêté" in response.get_json()["error"]["message"]
    assert claude["calls"] == []  # l'agent n'est jamais sollicite


def test_chat_stream_refused_cleanly_when_stopped(client, claude):
    agent_state.stop_agent("coupure test")
    response = client.post("/chat/stream", json={"question": "Combien au total ?"})
    assert response.status_code == 503
    assert claude["calls"] == []


def _calculation_count(application) -> int:
    connection = sqlite3.connect(application.config["DATABASE_PATH"])
    try:
        return connection.execute("SELECT COUNT(*) FROM calculations").fetchone()[0]
    finally:
        connection.close()


def test_stop_start_cancels_request_blocked_in_claude(
    application, client, monkeypatch
):
    claude_started = threading.Event()
    release_claude = threading.Event()
    verify_mock = Mock()

    class BlockingMessages:
        def create(self, **_kwargs):
            claude_started.set()
            assert release_claude.wait(timeout=5)
            return SimpleNamespace(
                stop_reason="tool_use",
                usage=SimpleNamespace(input_tokens=0, output_tokens=0),
                content=[SimpleNamespace(
                    type="tool_use",
                    id="toolu_blocked",
                    name="verify_expenses",
                    input={
                        "operation": "total_net",
                        "category": None,
                        "start_date": None,
                        "end_date": None,
                    },
                )],
            )

    fake_client = SimpleNamespace(messages=BlockingMessages(), close=Mock())
    monkeypatch.setattr("app.agent._client", lambda: fake_client)
    monkeypatch.setattr("app.agent.verify_expenses", verify_mock)

    def send_chat():
        with application.test_client() as thread_client:
            response = thread_client.post(
                "/chat", json={"question": "Combien au total ?"}
            )
            return response.status_code, response.get_json()

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(send_chat)
        assert claude_started.wait(timeout=5)
        client.post("/agent/state", json={"status": "stopped"})
        client.post("/agent/state", json={"status": "running"})
        release_claude.set()
        status_code, payload = future.result(timeout=5)

    assert status_code == 503
    assert "interrompue" in payload["error"]["message"]
    verify_mock.assert_not_called()
    assert _calculation_count(application) == 0

    log_content = Path(application.config["EXECUTION_LOG_PATH"]).read_text()
    cancellation_line = next(
        line for line in log_content.splitlines()
        if "agent_execution_cancelled" in line
    )
    assert "checkpoint='after_claude'" in cancellation_line
    assert cancellation_line[:24].endswith("Z")


def test_stop_start_during_verification_emits_no_result_and_persists_nothing(
    application, client, claude, monkeypatch
):
    verification_started = threading.Event()
    release_verification = threading.Event()

    verified_outcome = {
        "request": {
            "operation": "total_by_category",
            "category": "Alimentation",
            "start_date": None,
            "end_date": None,
        },
        "python": {"ok": True, "value": {"result_cents": 7250, "expense_ids": []}},
        "sql": {"ok": True, "value": {"result_cents": 7250, "expense_ids": []}},
        "comparison": {"status": "concordance", "result_cents": 7250},
        "tool_ok": True,
        "tool_error": None,
    }

    def blocking_verify(_database_path, _arguments):
        verification_started.set()
        assert release_verification.wait(timeout=5)
        return verified_outcome

    monkeypatch.setattr("app.agent.verify_expenses", blocking_verify)

    def send_stream():
        with application.test_client() as thread_client:
            response = thread_client.post(
                "/chat/stream",
                json={"question": "Combien en alimentation ?"},
                buffered=True,
            )
            return response.status_code, response.get_data(as_text=True)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(send_stream)
        assert verification_started.wait(timeout=5)
        client.post("/agent/state", json={"status": "stopped"})
        client.post("/agent/state", json={"status": "running"})
        release_verification.set()
        status_code, stream_body = future.result(timeout=5)

    assert status_code == 200
    assert "event: error" in stream_body
    assert "interrompue" in stream_body
    assert "event: tool_result" not in stream_body
    assert "7250" not in stream_body
    assert "72,50" not in stream_body
    assert "event: final" not in stream_body
    assert _calculation_count(application) == 0

    log_content = Path(application.config["EXECUTION_LOG_PATH"]).read_text()
    assert "checkpoint='after_verify_expenses'" in log_content
