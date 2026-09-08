import re
import signal
from pathlib import Path

import pytest

import app as app_package
from app.execution_log import configure_execution_log, log_event

TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z INFO")


def test_log_event_writes_a_timestamped_line(tmp_path):
    log_path = tmp_path / "exec.log"
    configure_execution_log(str(log_path))
    log_event("test_event", foo="bar")
    content = log_path.read_text()
    assert "test_event foo='bar'" in content
    assert TIMESTAMP_RE.match(content)


def test_configure_execution_log_creates_parent_directory(tmp_path):
    log_path = tmp_path / "nested" / "exec.log"
    configure_execution_log(str(log_path))
    log_event("ping")
    assert log_path.exists()


def _read_log(application) -> str:
    return Path(application.config["EXECUTION_LOG_PATH"]).read_text()


def test_full_chat_flow_is_logged(client, claude, application):
    client.post("/chat", json={"question": "Combien au total ?"})
    content = _read_log(application)
    for event in ("chat_request", "tool_call", "tool_result", "chat_response"):
        assert event in content


def test_missing_api_key_logs_resource_failure(client, application, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client.post("/chat", json={"question": "Combien au total ?"})
    content = _read_log(application)
    assert "resource_failure" in content
    assert "anthropic_api_key" in content


def test_stop_and_refusal_are_logged(client, claude, application):
    import app.agent_state as agent_state

    agent_state.stop_agent("coupure test")
    content = _read_log(application)
    assert "agent_stopped" in content
    assert "coupure test" in content

    client.post("/chat", json={"question": "Combien au total ?"})
    content = _read_log(application)
    assert "chat_refused" in content


def test_database_failure_is_logged(client, application, monkeypatch):
    import sqlite3

    def broken(_path):
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr("app.db.get_connection", broken)
    response = client.get("/expenses")
    assert response.status_code == 503
    content = _read_log(application)
    assert "resource_failure" in content
    assert "resource='database'" in content


def test_signal_handlers_are_installed_once(monkeypatch):
    # On ne declenche pas de vrai signal (ca tuerait le process pytest) :
    # on verifie juste que SIGTERM/SIGINT sont bien enregistres, une seule fois.
    registered = []
    monkeypatch.setattr(signal, "signal", lambda sig, handler: registered.append(sig))
    monkeypatch.setattr("atexit.register", lambda fn: None)
    monkeypatch.setattr(app_package, "_signal_handlers_installed", False)

    app_package._install_signal_handlers()
    assert set(registered) == {signal.SIGTERM, signal.SIGINT}

    registered.clear()
    app_package._install_signal_handlers()
    assert registered == []
