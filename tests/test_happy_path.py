import io
import json
from unittest.mock import Mock

import pytest

from app import create_app
from app.db import get_connection, init_db
from conftest import CSV_CONTENT


def upload(client, content=CSV_CONTENT):
    return client.post("/imports", data={"file": (io.BytesIO(content), "expenses.csv")})


def ask(client):
    return client.post("/chat", json={"question": "Combien ai-je dépensé en alimentation ?"})


def test_full_http_happy_path(client, application, claude):
    assert client.get("/").status_code == 200
    assert upload(client).get_json() == {"imported_count": 4}
    expenses = client.get("/expenses").get_json()
    assert [e["amount_cents"] for e in expenses] == [4250, 6500, 1200, 1800]
    response = ask(client)
    assert response.status_code == 200
    calculation_id = response.get_json()["calculation_id"]
    detail = client.get(f"/calculations/{calculation_id}").get_json()
    assert {"answer", "verdict", "python", "sql", "total_duration_ms", "expenses"} <= detail.keys()
    assert detail["answer"] == "Vous avez dépensé 72,50 € dans la catégorie Alimentation."
    assert detail["verdict"] == "concordance"
    for tool in ("python", "sql"):
        assert detail[tool]["ok"] is True
        assert detail[tool]["value"]["result_cents"] == 7250
        assert detail[tool]["value"]["expense_ids"] == [1, 3, 4]
        assert detail[tool]["value"]["duration_ms"] >= 0
    assert [e["id"] for e in detail["expenses"]] == [1, 3, 4]
    assert detail["total_duration_ms"] >= max(detail[t]["value"]["duration_ms"] for t in ("python", "sql"))
    # Verify persistence after constructing a new application.
    other = create_app(application.config["DATABASE_PATH"]).test_client()
    assert other.get(f"/calculations/{calculation_id}").get_json() == detail
    body = claude["calls"][0]
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert body["messages"][0]["content"] == "Combien ai-je dépensé en alimentation ?"
    assert "Carrefour" not in json.dumps(body)


@pytest.mark.parametrize("amount", [7250, 6500])
def test_divergence_preserves_both_selections(client, claude, monkeypatch, amount):
    upload(client)
    monkeypatch.setattr("app.routes.calculate_sql", lambda *_: {
        "ok": True, "value": {"result_cents": amount, "expense_ids": [2], "duration_ms": 1},
    })
    calc_id = ask(client).get_json()["calculation_id"]
    detail = client.get(f"/calculations/{calc_id}").get_json()
    assert detail["verdict"] == "divergence"
    assert "ne peut pas être validé" in detail["answer"]
    assert "Vous avez dépensé" not in detail["answer"]
    assert [e["id"] for e in detail["expenses"]] == [1, 2, 3, 4]


@pytest.mark.parametrize("failed", ["calculate_python", "calculate_sql"])
def test_calculator_failure_keeps_other_evidence(client, claude, monkeypatch, failed):
    upload(client)
    monkeypatch.setattr(f"app.routes.{failed}", Mock(side_effect=RuntimeError("failure")))
    calc_id = ask(client).get_json()["calculation_id"]
    detail = client.get(f"/calculations/{calc_id}").get_json()
    assert detail["verdict"] == "divergence"
    assert "ne peut pas être validé" in detail["answer"]
    assert [e["id"] for e in detail["expenses"]] == [1, 3, 4]


def test_ambiguous_question_never_calculates(client, claude, monkeypatch, application):
    claude["parsed"].update(status="needs_clarification", operation=None, category=None, message="Veuillez préciser la période.")
    calculators = [Mock() for _ in range(2)]
    for name, mock in zip(("calculate_python", "calculate_sql"), calculators):
        monkeypatch.setattr(f"app.routes.{name}", mock)
    response = client.post("/chat", json={"question": "Combien ai-je dépensé récemment ?"})
    assert response.get_json() == {"status": "needs_clarification", "message": "Veuillez préciser la période."}
    for mock in calculators:
        mock.assert_not_called()
    conn = get_connection(application.config["DATABASE_PATH"])
    assert conn.execute("SELECT COUNT(*) FROM calculations").fetchone()[0] == 0
    conn.close()


@pytest.mark.parametrize("bad_row", [
    b"2026-09-05,invalide,,abc\n", b"2026-99-99,invalide,Alimentation,1\n",
    b"2026-09-05,invalide,Alimentation,42,50\n", b"2026-09-05,invalide\n",
])
def test_invalid_csv_is_atomic(client, bad_row):
    assert upload(client).status_code == 201
    before = client.get("/expenses").get_json()
    response = upload(client, CSV_CONTENT + bad_row)
    assert response.status_code == 422
    assert response.get_json()["ok"] is False
    assert client.get("/expenses").get_json() == before


@pytest.mark.parametrize("content", [b"", b"a,b\n", b"\xff", b'date,description,categorie,montant\n', b'date,description,categorie,montant\n"unterminated'])
def test_unreadable_or_empty_csv(client, content):
    assert upload(client, content).status_code == 422
    assert client.get("/expenses").get_json() == []


def test_upload_limit(client):
    assert upload(client, b"x" * (2 * 1024 * 1024)).status_code == 413


@pytest.mark.parametrize("body", [None, [], 12, {"question": 12}, {"question": "  "}])
def test_invalid_question(client, body):
    assert client.post("/chat", json=body).status_code == 400


def test_missing_key_is_clear(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    response = ask(client)
    assert response.status_code == 502
    assert "ANTHROPIC_API_KEY" in response.get_json()["error"]["message"]


def test_legacy_database_migration(tmp_path):
    path = str(tmp_path / "legacy.db")
    conn = get_connection(path)
    conn.execute("CREATE TABLE calculations (id INTEGER PRIMARY KEY, question TEXT, request_json TEXT, python_result_json TEXT, sql_result_json TEXT, status TEXT, created_at TEXT)")
    value = json.dumps({"ok": True, "value": {"result_cents": 0, "expense_ids": [], "duration_ms": 1}})
    conn.execute("INSERT INTO calculations VALUES (1, 'total', ?, ?, ?, 'match', '2026-09-01')", (json.dumps({"operation": "total"}), value, value))
    conn.commit()
    conn.close()
    init_db(path)
    init_db(path)
    detail = create_app(path).test_client().get("/calculations/1").get_json()
    assert detail["verdict"] == "concordance"
    assert detail["total_duration_ms"] is None
    assert '"match"' not in json.dumps(detail)


@pytest.mark.parametrize("operation,start,end,amount,ids", [
    ("total", None, None, 13750, [1, 2, 3, 4]),
    ("total_by_period", "2026-09-02", "2026-09-03", 7700, [2, 3]),
])
def test_other_supported_operations(client, claude, operation, start, end, amount, ids):
    upload(client)
    claude["parsed"].update(operation=operation, category=None, start_date=start, end_date=end)
    calculation_id = ask(client).get_json()["calculation_id"]
    detail = client.get(f"/calculations/{calculation_id}").get_json()
    assert detail["verdict"] == "concordance"
    for tool in ("python", "sql"):
        assert detail[tool]["value"]["result_cents"] == amount
        assert detail[tool]["value"]["expense_ids"] == ids


def test_invalid_llm_dates_never_calculate(client, claude, monkeypatch):
    claude["parsed"].update(operation="total_by_period", category=None, start_date="2026-99-99", end_date="2026-12-31")
    run = Mock()
    monkeypatch.setattr("app.routes._run_calculators", run)
    assert ask(client).status_code == 422
    run.assert_not_called()
