"""Palier 5 : entrees vides/absurdes/hostiles, confiance, cout et tokens."""
from decimal import Decimal

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
    prefix = "Combien ai-je dépensé ? "
    question = prefix + "a" * (MAX_QUESTION_LENGTH - len(prefix))
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
    assert detail["request_info"]["confidence"] == "high"


def test_confidence_is_none_on_divergence(client, claude, monkeypatch):
    monkeypatch.setattr("app.verification.calculate_sql", lambda *_a, **_k: {
        "ok": True, "value": {"result_cents": 999, "expense_ids": [1], "duration_ms": 1},
    })
    response = ask(client, "Combien ai-je dépensé au total ?")
    calc_id = response.get_json()["calculation_id"]
    detail = client.get(f"/calculations/{calc_id}").get_json()
    assert detail["verdict"] == "divergence"
    assert detail["confidence"] == "aucune"
    assert detail["request_info"]["confidence"] is None


def test_usage_and_cost_are_exposed_on_success(client, claude):
    response = ask(client, "Combien ai-je dépensé au total ?")
    calc_id = response.get_json()["calculation_id"]
    detail = client.get(f"/calculations/{calc_id}").get_json()
    info = detail["request_info"]
    usage = info["metrics"]
    assert usage["model_calls"] >= 1
    assert usage["input_tokens"] > 0
    assert usage["output_tokens"] > 0
    assert isinstance(info["cost"]["amount"], str)
    assert Decimal(info["cost"]["amount"]) > 0
    assert info["cost"]["currency"] == "USD"


def test_usage_is_exposed_even_on_clarification(client, claude):
    claude["tool_call"] = False
    claude["final_text"] = "Veuillez préciser la période."
    response = ask(client, "Combien ai-je dépensé récemment ?")
    body = response.get_json()
    assert body["request_info"]["metrics"]["model_calls"] == 1


def test_usage_is_exposed_even_when_claude_refuses(client, application, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    response = ask(client, "Combien au total ?")
    assert response.status_code == 502
    body = response.get_json()
    info = body["request_info"]
    assert info["metrics"]["model_calls"] == 0
    assert info["metrics"]["input_tokens"] == 0
    assert info["metrics"]["output_tokens"] == 0
    assert info["cost"] == {"amount": "0.00000000", "currency": "USD"}
