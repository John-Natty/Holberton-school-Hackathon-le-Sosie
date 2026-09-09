"""Palier 5 : entrees vides/absurdes/hostiles, confiance, cout et tokens."""
import pytest

from app.routes import MAX_QUESTION_LENGTH


def ask(client, question):
    return client.post("/chat", json={"question": question})


@pytest.mark.parametrize("body", [
    {"question": ""}, {"question": "   "}, {"question": None},
    {"question": 42}, {}, {"question": []}, {"question": {"a": 1}},
])
def test_empty_or_malformed_question_is_rejected(client, body):
    response = client.post("/chat", json=body)
    assert response.status_code == 400
    assert response.get_json()["ok"] is False


def test_question_over_the_limit_is_rejected(client):
    response = ask(client, "a" * (MAX_QUESTION_LENGTH + 1))
    assert response.status_code == 400
    assert str(MAX_QUESTION_LENGTH) in response.get_json()["error"]["message"]


def test_question_at_the_limit_is_accepted(client, claude):
    # Une question pile a la limite doit passer normalement, pas etre bloquee.
    claude["tool_call"] = False
    claude["final_text"] = "Veuillez préciser votre question."
    question = "Combien ai-je dépensé ? " + "a" * (MAX_QUESTION_LENGTH - 24)
    response = ask(client, question)
    assert response.status_code == 200


@pytest.mark.parametrize("bad_char", ["\x00", "\x01", "\x7f", "\x0b"])
def test_control_characters_are_rejected(client, bad_char):
    response = ask(client, f"Combien au total{bad_char} ?")
    assert response.status_code == 400
    assert "contrôle" in response.get_json()["error"]["message"]


def test_newlines_and_tabs_are_allowed(client, claude):
    # Ce ne sont pas des caracteres de controle "absurdes" : un vrai
    # utilisateur peut coller une question sur plusieurs lignes.
    response = ask(client, "Combien ai-je\ndépensé\tau total ?")
    assert response.status_code == 200


def test_chat_stream_also_enforces_the_limit(client):
    response = client.post("/chat/stream", json={"question": "a" * (MAX_QUESTION_LENGTH + 1)})
    assert response.status_code == 400


def test_confidence_is_high_only_on_concordance(client, claude):
    response = ask(client, "Combien ai-je dépensé au total ?")
    calc_id = response.get_json()["calculation_id"]
    detail = client.get(f"/calculations/{calc_id}").get_json()
    assert detail["verdict"] == "concordance"
    assert detail["confidence"] == "haute"


def test_confidence_is_none_on_divergence(client, claude, monkeypatch):
    monkeypatch.setattr("app.verification.calculate_sql", lambda *_a, **_k: {
        "ok": True, "value": {"result_cents": 999, "expense_ids": [1], "duration_ms": 1},
    })
    response = ask(client, "Combien ai-je dépensé au total ?")
    calc_id = response.get_json()["calculation_id"]
    detail = client.get(f"/calculations/{calc_id}").get_json()
    assert detail["verdict"] == "divergence"
    assert detail["confidence"] == "aucune"


def test_usage_and_cost_are_exposed_on_success(client, claude):
    response = ask(client, "Combien ai-je dépensé au total ?")
    calc_id = response.get_json()["calculation_id"]
    detail = client.get(f"/calculations/{calc_id}").get_json()
    usage = detail["usage"]
    assert usage["api_calls"] >= 1
    assert usage["input_tokens"] > 0
    assert usage["output_tokens"] > 0
    assert usage["cost_estimate_usd"] > 0
    assert usage["model"] == "claude-sonnet-5"


def test_usage_is_exposed_even_on_clarification(client, claude):
    claude["tool_call"] = False
    claude["final_text"] = "Veuillez préciser la période."
    response = ask(client, "Combien ai-je dépensé récemment ?")
    body = response.get_json()
    assert body["usage"]["api_calls"] == 1


def test_usage_is_exposed_even_when_claude_refuses(client, application, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    response = ask(client, "Combien au total ?")
    assert response.status_code == 502
    body = response.get_json()
    assert body["usage"] == {"model": "claude-sonnet-5", "api_calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_estimate_usd": 0.0}
