import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor

from flask import Blueprint, current_app, jsonify, request

from app.calculation_request import build_calculation_request
from app.calculators.python_calc import calculate_python
from app.calculators.sql_calc import calculate_sql
from app.comparator import compare_results
from app.csv_import import import_csv
from app.expenses_lookup import get_expenses
from app.llm import LLMError, parse_question
from app.models import ValidationError

bp = Blueprint("api", __name__)


def _conn() -> sqlite3.Connection:
    from app.db import get_connection

    return get_connection(current_app.config["DATABASE_PATH"])


@bp.get("/health")
def health():
    return jsonify({"status": "ok"})


@bp.post("/imports")
def imports():
    if "file" not in request.files:
        return jsonify({"error": "champ 'file' manquant"}), 400

    file = request.files["file"]
    filename = file.filename or ""
    if not filename.lower().endswith(".csv"):
        return jsonify({"error": "seul le format CSV est supporte"}), 400

    conn = _conn()
    try:
        result = import_csv(conn, file.read())
    except ValidationError as exc:
        return jsonify({"error": exc.message}), 400
    finally:
        conn.close()

    return jsonify(result), 201


@bp.get("/expenses")
def list_expenses():
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT id, date, description, category, amount_cents, source_type "
            "FROM expenses ORDER BY id ASC"
        ).fetchall()
        return jsonify([dict(row) for row in rows])
    finally:
        conn.close()


@bp.post("/chat")
def chat():
    payload = request.get_json(silent=True) or {}
    question = (payload.get("question") or "").strip()
    if not question:
        return jsonify({"error": "champ 'question' obligatoire"}), 400

    try:
        parsed = parse_question(question)
    except LLMError as exc:
        return jsonify({"error": str(exc)}), 502

    if parsed.get("status") == "needs_clarification":
        return jsonify(
            {
                "status": "needs_clarification",
                "clarification_question": parsed.get("clarification_question"),
            }
        )

    try:
        calc_request = build_calculation_request(parsed)
    except ValidationError as exc:
        return jsonify({"error": exc.message}), 422

    conn = _conn()
    try:
        start = time.perf_counter()
        python_result, sql_result = _run_calculators(calc_request)
        total_duration_ms = (time.perf_counter() - start) * 1000

        comparison = compare_results(python_result, sql_result)

        calc_id = conn.execute(
            "INSERT INTO calculations "
            "(question, request_json, python_result_json, sql_result_json, status) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                question,
                json.dumps(calc_request),
                json.dumps(python_result),
                json.dumps(sql_result),
                comparison["status"],
            ),
        ).lastrowid
        conn.commit()
    finally:
        conn.close()

    return jsonify(
        {
            "calculation_id": calc_id,
            "request": calc_request,
            "python": python_result,
            "sql": sql_result,
            "comparison": comparison,
            "duration_ms": total_duration_ms,
        }
    )


def _run_calculators(calc_request: dict) -> tuple[dict, dict]:
    # Each calculator opens its own SQLite connection in its own thread to
    # stay isolated; they only share already-normalized data on disk.
    database_path = current_app.config["DATABASE_PATH"]
    with ThreadPoolExecutor(max_workers=2) as executor:
        python_future = executor.submit(calculate_python, database_path, calc_request)
        sql_future = executor.submit(calculate_sql, database_path, calc_request)
        return python_future.result(), sql_future.result()


@bp.get("/calculations/<int:calculation_id>")
def get_calculation(calculation_id: int):
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT * FROM calculations WHERE id = ?", (calculation_id,)
        ).fetchone()
        if row is None:
            return jsonify({"error": "calcul introuvable"}), 404

        python_result = json.loads(row["python_result_json"])
        sql_result = json.loads(row["sql_result_json"])

        expense_ids = []
        if python_result.get("ok"):
            expense_ids = python_result["value"]["expense_ids"]

        expenses = get_expenses(conn, expense_ids)

        return jsonify(
            {
                "id": row["id"],
                "question": row["question"],
                "request": json.loads(row["request_json"]),
                "python": python_result,
                "sql": sql_result,
                "status": row["status"],
                "expenses": expenses,
                "created_at": row["created_at"],
            }
        )
    finally:
        conn.close()
