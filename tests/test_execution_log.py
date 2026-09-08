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


def test_application_log_is_created_beside_database(application):
    database_path = Path(application.config["DATABASE_PATH"])
    log_path = Path(application.config["EXECUTION_LOG_PATH"])
    assert log_path == database_path.parent / "execution.log"
    assert log_path.is_file()


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


def test_agent_logs_endpoint_returns_only_latest_structured_lines(
    client, application
):
    for index in range(60):
        log_event("numbered_event", index=index)

    response = client.get("/agent/logs")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["count"] == 50
    assert len(payload["logs"]) == 50
    assert "index=10" in payload["logs"][0]["message"]
    assert "index=59" in payload["logs"][-1]["message"]
    assert all(set(entry) == {"timestamp", "level", "message"} for entry in payload["logs"])

    limited = client.get("/agent/logs?limit=2").get_json()
    assert limited["count"] == 2
    assert "index=58" in limited["logs"][0]["message"]


@pytest.mark.parametrize("limit", ["0", "51", "abc"])
def test_agent_logs_endpoint_rejects_invalid_limit(client, limit):
    assert client.get(f"/agent/logs?limit={limit}").status_code == 400


def test_agent_logs_endpoint_returns_empty_list_when_file_is_absent(
    client, application
):
    log_path = Path(application.config["EXECUTION_LOG_PATH"])
    log_path.unlink()
    response = client.get("/agent/logs")
    assert response.status_code == 200
    assert response.get_json() == {"logs": [], "count": 0}


def test_agent_logs_endpoint_handles_inaccessible_path(client, application, tmp_path):
    directory = tmp_path / "not-a-log-file"
    directory.mkdir()
    application.config["EXECUTION_LOG_PATH"] = str(directory)
    response = client.get("/agent/logs")
    assert response.status_code == 503
    assert "inaccessible" in response.get_json()["error"]["message"]


def test_agent_logs_endpoint_redacts_secrets(client, application, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-super-secret-value")
    log_event(
        "credentials_seen",
        api_key="test-super-secret-value",
        authorization="Bearer dangerous-token",
        message="ANTHROPIC_API_KEY=test-super-secret-value",
    )
    payload = client.get("/agent/logs?limit=1").get_json()
    serialized = str(payload)
    assert "test-super-secret-value" not in serialized
    assert "dangerous-token" not in serialized
    assert "[REDACTED]" in serialized


def test_compose_persists_default_log_under_app_data():
    compose = Path("compose.yaml").read_text()
    env_example = Path(".env.example").read_text()
    assert "sqlite_data:/app/data" in compose
    assert "DATABASE_PATH=data/data.db" in env_example
    assert "EXECUTION_LOG_PATH=data/execution.log" in env_example


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
