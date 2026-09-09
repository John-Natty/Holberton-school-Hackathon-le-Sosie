import json

import anthropic
import httpx2
import pytest

import app.agent_state as agent_state
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


@pytest.fixture(autouse=True)
def _reset_agent_state():
    # L'etat running/stopped est un module global : on repart de "running"
    # avant et apres chaque test, pour ne pas polluer les tests suivants.
    agent_state.start_agent()
    yield
    agent_state.start_agent()


def _has_tool_result(body: dict) -> bool:
    return any(
        isinstance(message.get("content"), list)
        and any(block.get("type") == "tool_result" for block in message["content"])
        for message in body["messages"]
    )


@pytest.fixture
def claude(monkeypatch):
    """Only the external HTTP service is substituted; the real Anthropic SDK
    and the real agent tool-calling loop run against it.

    - `tool_call=True` (default): the first turn returns a verify_expenses
      tool_use block built from `arguments`; the following turn (after the
      backend sends back the tool_result) returns `final_text`.
    - `tool_call=False`: Claude never calls the tool; every turn returns
      `final_text` directly (used for clarification or refusal scenarios).
    """
    state = {
        "calls": [],
        "status": 200,
        "stop_reason": "end_turn",
        "tool_call": True,
        "usage": {"input_tokens": 10, "output_tokens": 20},
        "usages": [],
        "arguments": {
            "operation": "total_by_category", "category": "Alimentation",
            "start_date": None, "end_date": None,
        },
        "final_text": "Vous avez dépensé 72,50 € dans la catégorie Alimentation.",
    }
    original = anthropic.Anthropic
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-only-not-a-real-key")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-5")

    def respond(request):
        body = json.loads(request.content)
        state["calls"].append(body)
        status = state["status"](len(state["calls"])) if callable(state["status"]) else state["status"]
        if status != 200:
            return httpx2.Response(status, json={"type": "error", "error": {
                "type": "authentication_error", "message": "external private details",
            }})

        if state["tool_call"] and not _has_tool_result(body):
            content = [{
                "type": "tool_use", "id": f"toolu_{len(state['calls'])}",
                "name": "verify_expenses", "input": state["arguments"],
            }]
            stop_reason = "tool_use"
        else:
            content = [{"type": "text", "text": state["final_text"]}]
            stop_reason = state["stop_reason"]

        return httpx2.Response(200, json={
            "id": f"msg_test_{len(state['calls'])}", "type": "message", "role": "assistant",
            "model": "claude-sonnet-5", "content": content,
            "stop_reason": stop_reason, "stop_sequence": None,
            "usage": state["usages"].pop(0) if state["usages"] else state["usage"],
        })

    def factory(**kwargs):
        return original(**kwargs, http_client=httpx2.Client(transport=httpx2.MockTransport(respond)))

    monkeypatch.setattr("app.agent.anthropic.Anthropic", factory)
    return state
