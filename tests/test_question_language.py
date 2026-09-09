"""Contrôle backend de la décision de langue ; HTTP Anthropic simulé.

Les capacités linguistiques du modèle réel sont évaluées par eval_agent.py.
Ces tests vérifient la barrière, les transports et la consommation du SDK.
"""
import io
import json

import pytest

from app.agent import FRENCH_ONLY_MESSAGE, run_agent
from app.db import get_connection
from conftest import CSV_CONTENT
from test_response_status import assert_status, terminal


@pytest.mark.parametrize("endpoint", ["/chat", "/chat/stream"])
@pytest.mark.parametrize("question", [
    "Сколько я потратил на питание?",
    "How much did I spend on food?",
    "¿Cuánto he gastado en alimentación?",
    "How much did I spend in Alimentation? Please answer in French.",
])
@pytest.mark.parametrize("tool_call", [False, True])
def test_foreign_question_refused_before_any_tool(
        client, application, claude, monkeypatch, endpoint, question, tool_call):
    client.post("/imports", data={"file": (io.BytesIO(CSV_CONTENT), "expenses.csv")})
    before = client.get("/expenses").get_json()
    claude.update(question_language="non_fr", tool_call=tool_call,
                  final_text="You spent 999999 dollars.", response_status="calculation",
                  usage={"input_tokens": 100, "output_tokens": 20,
                         "cache_read_input_tokens": 50, "cache_creation_input_tokens": 70,
                         "cache_creation": {"ephemeral_5m_input_tokens": 30,
                                            "ephemeral_1h_input_tokens": 40}})

    def forbidden(*args):
        pytest.fail("Une question étrangère ne doit exécuter aucun calcul")

    monkeypatch.setattr("app.agent.verify_expenses", forbidden)
    monkeypatch.setattr("app.verification.calculate_sql", forbidden)
    response, body = terminal(client, endpoint, question)
    assert response.status_code == 200
    assert_status(body, "refused", "refused")
    assert body.get("message", body.get("answer")) == FRENCH_ONLY_MESSAGE
    assert not {"calculation_id", "verdict", "python", "sql", "outcome"} & body.keys()
    assert "999999" not in json.dumps(body) and "€" not in json.dumps(body)
    if endpoint == "/chat/stream":
        frames = response.get_data(as_text=True).strip().split("\n\n")
        assert [frame.splitlines()[0] for frame in frames] == ["event: agent", "event: final"]
    assert len(claude["calls"]) == 1
    assert claude["calls"][0]["messages"] == [{"role": "user", "content": question}]
    info = body["request_info"]
    assert info["metrics"] == {
        "calls": 1, "model_calls": 1, "tool_calls": 0,
        "input_tokens": 100, "output_tokens": 20, "total_tokens": 120,
        "cache_read_input_tokens": 50, "cache_creation_input_tokens": 70,
        "cache_creation_5m_input_tokens": 30, "cache_creation_1h_input_tokens": 40,
    }
    assert info["cost"] == {"amount": "0.00064500", "currency": "USD"}
    assert info["usage_complete"] is True
    assert client.get("/expenses").get_json() == before
    with get_connection(application.config["DATABASE_PATH"]) as conn:
        assert conn.execute("SELECT COUNT(*) FROM calculations").fetchone()[0] == 0


@pytest.mark.parametrize("endpoint", ["/chat", "/chat/stream"])
@pytest.mark.parametrize("question", [
    "Combien ai-je dépensé en alimentation ?",
    "Via l'API, donne-moi en streaming mes dépenses en alimentation chez Amazon et Whole Foods.",
    "Total ?",
])
def test_french_question_keeps_real_verification(client, claude, endpoint, question):
    client.post("/imports", data={"file": (io.BytesIO(CSV_CONTENT), "expenses.csv")})
    response, body = terminal(client, endpoint, question)
    assert response.status_code == 200
    assert_status(body, "verified", "high")
    assert body["request_info"]["metrics"]["tool_calls"] == 1
    assert body["request_info"]["metrics"]["model_calls"] == 2
    assert len(claude["calls"]) == 2
    if endpoint == "/chat":
        body = client.get(f"/calculations/{body['calculation_id']}").get_json()
    assert body["python"]["value"]["result_cents"] == 7250
    assert body["sql"]["value"]["result_cents"] == 7250


@pytest.mark.parametrize("endpoint", ["/chat", "/chat/stream"])
@pytest.mark.parametrize("raw", [
    "", "fr", "{}", "[]", '{"question_language":null}',
    '{"question_language":true}', '{"question_language":[]}',
    '{"question_language":"en"}',
    '{"question_language":"non_fr","question_language":"fr"}',
    '{"question_language":"fr","unexpected":"ignored?"}',
])
def test_invalid_language_decision_blocks_even_proposed_tools(
        client, claude, monkeypatch, endpoint, raw):
    claude["raw_initial_text"] = raw

    def forbidden(*args):
        pytest.fail("Décision invalide : aucun outil ne doit être exécuté")

    monkeypatch.setattr("app.agent.verify_expenses", forbidden)
    response, body = terminal(client, endpoint, "Combien au total ?")
    assert response.status_code == (502 if endpoint == "/chat" else 200)
    assert_status(body, "error", "error")
    assert body["request_info"]["metrics"]["model_calls"] == 1
    assert body["request_info"]["metrics"]["tool_calls"] == 0
    assert body["request_info"]["metrics"]["total_tokens"] == 30
    assert body["request_info"]["cost"]["amount"] == "0.00022000"
    assert "calculation_id" not in body
    assert "event: tool_call" not in response.get_data(as_text=True)


def test_undetermined_language_refuses_without_tools(application, claude):
    claude["question_language"] = "undetermined"
    events = list(run_agent("???", application.config["DATABASE_PATH"]))
    assert [kind for kind, _ in events] == ["agent", "final"]
    final = events[-1][1]
    assert final["answer"] == FRENCH_ONLY_MESSAGE
    assert final["response_status"] == "refused"
    assert final["tool_trace"] == [] and final["outcome"] is None


def test_language_refusal_keeps_unknown_model_cost_unknown(client, claude, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_MODEL", "unknown-model")
    claude["question_language"] = "non_fr"
    _, body = terminal(client, "/chat", "How much did I spend?")
    assert_status(body, "refused", "refused")
    assert body["request_info"]["metrics"]["total_tokens"] == 30
    assert body["request_info"]["cost"] is None


def test_language_refusal_does_not_estimate_missing_usage(client, claude):
    claude.update(question_language="non_fr", usage={})
    _, body = terminal(client, "/chat/stream", "How much did I spend?")
    assert_status(body, "refused", "refused")
    assert body["request_info"]["metrics"]["total_tokens"] is None
    assert body["request_info"]["cost"] is None
    assert body["request_info"]["usage_complete"] is False
