import io
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402

CSV_CONTENT = b"""date,description,categorie,montant
2026-09-01,Carrefour,Alimentation,42.50
2026-09-02,Essence,Transport,65.00
2026-09-03,Boulangerie,Alimentation,12.00
2026-09-04,Restaurant,Alimentation,18.00
2026-09-05,ligne invalide,,abc
"""


def make_client(tmp_path):
    db_path = str(tmp_path / "test.db")
    app = create_app(database_path=db_path)
    app.testing = True
    return app.test_client()


def test_health(tmp_path):
    client = make_client(tmp_path)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_csv_import_validates_and_normalizes(tmp_path):
    client = make_client(tmp_path)
    resp = client.post(
        "/imports",
        data={"file": (io.BytesIO(CSV_CONTENT), "expenses.csv")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert len(body["imported"]) == 4
    assert len(body["rejected"]) == 1
    assert body["imported"][0]["amount_cents"] == 4250

    resp = client.get("/expenses")
    assert len(resp.get_json()) == 4


def test_chat_happy_path_total_by_category(tmp_path):
    client = make_client(tmp_path)
    client.post(
        "/imports",
        data={"file": (io.BytesIO(CSV_CONTENT), "expenses.csv")},
        content_type="multipart/form-data",
    )

    fake_parsed = {
        "status": "ok",
        "operation": "total_by_category",
        "category": "Alimentation",
        "start_date": None,
        "end_date": None,
        "clarification_question": None,
    }

    with patch("app.routes.parse_question", return_value=fake_parsed):
        resp = client.post("/chat", json={"question": "Combien ai-je depense en alimentation ?"})

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["comparison"]["status"] == "match"
    assert body["comparison"]["result_cents"] == 4250 + 1200 + 1800
    assert body["python"]["value"]["expense_ids"] == body["sql"]["value"]["expense_ids"]

    calc_id = body["calculation_id"]
    detail = client.get(f"/calculations/{calc_id}")
    assert detail.status_code == 200
    detail_body = detail.get_json()
    assert len(detail_body["expenses"]["value"]) == 3


def test_chat_needs_clarification(tmp_path):
    client = make_client(tmp_path)
    fake_parsed = {
        "status": "needs_clarification",
        "operation": None,
        "category": None,
        "start_date": None,
        "end_date": None,
        "clarification_question": "Sur quelle periode ?",
    }
    with patch("app.routes.parse_question", return_value=fake_parsed):
        resp = client.post("/chat", json={"question": "Combien ai-je depense recemment ?"})

    assert resp.status_code == 200
    assert resp.get_json()["status"] == "needs_clarification"


def test_comparator_flags_divergent_expense_ids():
    from app.comparator import compare_results

    python_result = {"ok": True, "value": {"result_cents": 100, "expense_ids": [1, 2]}}
    sql_result = {"ok": True, "value": {"result_cents": 100, "expense_ids": [3, 4]}}
    comparison = compare_results(python_result, sql_result)
    assert comparison["status"] == "divergence"
