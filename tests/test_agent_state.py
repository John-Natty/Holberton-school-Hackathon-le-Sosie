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
