import json

import anthropic
import httpx2
import pytest

from app import create_app

CSV_CONTENT = b'''date,description,categorie,montant
2026-09-01,Carrefour,Alimentation,"42,50"
2026-09-02,Essence,Transport,65.00
2026-09-03,Boulangerie,Alimentation,12
2026-09-04,Restaurant,Alimentation,18.00
'''


@pytest.fixture
def application(tmp_path):
    app = create_app(str(tmp_path / "data" / "test.db"))
    app.testing = True
    return app


@pytest.fixture
def client(application):
    return application.test_client()


@pytest.fixture
def claude(monkeypatch):
    """Only the external HTTP service is substituted; run the installed SDK."""
    state = {"calls": [], "status": 200, "stop_reason": "end_turn", "parsed": {
        "status": "ok", "operation": "total_by_category", "category": "Alimentation",
        "start_date": None, "end_date": None, "message": None,
    }}
    original = anthropic.Anthropic
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-only-not-a-real-key")

    def respond(request):
        state["calls"].append(json.loads(request.content))
        if state["status"] != 200:
            return httpx2.Response(state["status"], json={"type": "error", "error": {
                "type": "authentication_error", "message": "external private details",
            }})
        return httpx2.Response(200, json={
            "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-sonnet-5",
            "content": [{"type": "text", "text": state.get("text", json.dumps(state["parsed"]))}],
            "stop_reason": state["stop_reason"], "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 20},
        })

    def factory(**kwargs):
        return original(**kwargs, http_client=httpx2.Client(transport=httpx2.MockTransport(respond)))

    monkeypatch.setattr("app.llm.anthropic.Anthropic", factory)
    return state
