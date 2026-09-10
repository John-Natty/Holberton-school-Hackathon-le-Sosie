"""Langue détectée par Lingua avant Claude, même si l'agent est arrêté."""
import json

import pytest

from app.question_language import FRENCH_ONLY_MESSAGE, foreign_language
from app.db import get_connection
from test_response_status import assert_status, terminal

FOREIGN_QUESTIONS = [
    ("ru", "Сколько я потратил на питание?"),
    ("en", "How much did I spend on food?"),
    ("es", "¿Cuánto he gastado en alimentación?"),
    ("de", "Wie viel habe ich für Lebensmittel ausgegeben?"),
    ("it", "Quanto ho speso per il cibo questo mese?"),
    ("ar", "كم أنفقت على الطعام هذا الشهر؟"),
    ("zh", "这个月我在食品上花了多少钱？"),
    ("ja", "今月は食費にいくら使いましたか？"),
    ("pt", "Quanto gastei em alimentação neste mês?"),
    ("en", "How much did I spend in Alimentation? Please answer in French."),
]
FRENCH_QUESTIONS = [
    "Combien ai-je dépensé en alimentation ?",
    "Combien ai-je dépensé pour Netflix ?",
    "Peux-tu vérifier mes dépenses avec SQL ?",
    "Quel est le coût de mes abonnements Docker, API et software ?",
    "Via l'API, donne-moi en streaming mes dépenses chez Amazon et Whole Foods.",
    "Total ?", "Netflix", "SQL", "Docker / API / software", "???",
]


def assert_zero_usage(body):
    info = body["request_info"]
    assert all(value == 0 for value in info["metrics"].values())
    assert info["cost"] == {"amount": "0.00000000", "currency": "USD"}
    assert info["usage_complete"] is True


@pytest.mark.parametrize("endpoint", ["/chat", "/chat/stream"])
@pytest.mark.parametrize("language,question", FOREIGN_QUESTIONS)
def test_foreign_question_refused_locally(client, application, monkeypatch, endpoint, language, question):
    def forbidden(*args, **kwargs):
        pytest.fail("Langue étrangère : ni modération, ni Claude, ni outil")

    monkeypatch.setattr("app.routes.moderate_texts", forbidden)
    monkeypatch.setattr("app.routes.run_agent", forbidden)
    monkeypatch.setattr("app.agent._client", forbidden)
    monkeypatch.setattr("app.agent.verify_expenses", forbidden)
    response, body = terminal(client, endpoint, question)
    assert response.status_code == 200
    assert_status(body, "refused", "refused")
    assert_zero_usage(body)
    assert body.get("message", body.get("answer")) == FRENCH_ONLY_MESSAGE
    assert not {"calculation_id", "verdict", "python", "sql"} & body.keys()
    if endpoint.endswith("stream"):
        assert response.get_data(as_text=True).count("event:") == 1
    with get_connection(application.config["DATABASE_PATH"]) as conn:
        assert conn.execute("SELECT COUNT(*) FROM calculations").fetchone()[0] == 0
    logs = json.dumps(client.get("/agent/logs").get_json(), ensure_ascii=False)
    assert f"language_rejected language='{language}'" in logs
    assert question not in logs


@pytest.mark.parametrize("question", FRENCH_QUESTIONS)
def test_french_mixed_and_ambiguous_text_is_not_rejected(question):
    assert foreign_language(question) is None


@pytest.mark.parametrize("endpoint", ["/chat", "/chat/stream"])
@pytest.mark.parametrize("question", FRENCH_QUESTIONS[:5])
def test_french_question_keeps_real_tool_calling(client, claude, endpoint, question):
    response, body = terminal(client, endpoint, question)
    assert response.status_code == 200
    assert_status(body, "verified", "high")
    assert body["request_info"]["metrics"]["tool_calls"] == 1
    assert body["request_info"]["metrics"]["model_calls"] == 2


@pytest.mark.parametrize("endpoint", ["/chat", "/chat/stream"])
def test_local_refusal_is_free_even_with_unknown_model(client, monkeypatch, endpoint):
    monkeypatch.setenv("ANTHROPIC_MODEL", "unknown-model")
    _, body = terminal(client, endpoint, "How much did I spend on food?")
    assert_zero_usage(body)


def test_language_runs_before_stopped_state(client):
    client.post("/agent/state", json={"status": "stopped"})
    response, body = terminal(client, "/chat", "How much did I spend on food?")
    assert response.status_code == 200
    assert_status(body, "refused", "refused")
    assert_zero_usage(body)


def test_invalid_input_runs_before_language(client, monkeypatch):
    def forbidden(*args):
        pytest.fail("Entrée invalide : pas de détection")
    monkeypatch.setattr("app.routes.foreign_language", forbidden)
    for endpoint in ("/chat", "/chat/stream"):
        for body in ({"question": ""}, {"question": "a" * 1501}, {"question": "abc\x00"}, {}):
            assert client.post(endpoint, json=body).status_code == 400
