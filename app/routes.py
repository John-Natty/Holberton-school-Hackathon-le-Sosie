import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor

from flask import Blueprint, current_app, jsonify, request

from app.calculation_request import build_calculation_request
from app.calculators.python_calc import calculate_python
from app.calculators.sql_calc import calculate_sql
from app.comparator import compare_results, valid_result
from app.csv_import import import_csv
from app.expenses_lookup import get_expenses
from app.llm import LLMError, parse_question
from app.models import ValidationError

bp = Blueprint("api", __name__)


def _conn():
    from app.db import get_connection
    return get_connection(current_app.config["DATABASE_PATH"])


def error(message, status):
    return jsonify({"ok": False, "error": {"message": message}}), status


@bp.app_errorhandler(sqlite3.Error)
def database_error(_exc):
    return error("La base de données est indisponible. Réessayez plus tard.", 503)


@bp.app_errorhandler(413)
def upload_too_large(_exc):
    return error("Fichier trop volumineux : limite de 2 Mio.", 413)


@bp.get("/health")
def health():
    conn = _conn()
    try:
        conn.execute("SELECT 1 FROM expenses LIMIT 1")
        return jsonify({"status": "ok"})
    finally:
        conn.close()


@bp.post("/imports")
def imports():
    if "file" not in request.files:
        return error("Champ 'file' manquant.", 400)
    file = request.files["file"]
    if not (file.filename or "").lower().endswith(".csv"):
        return error("Seul le format CSV est pris en charge.", 415)
    conn = _conn()
    try:
        return jsonify(import_csv(conn, file.read())), 201
    except ValidationError as exc:
        return error(exc.message, 422)
    finally:
        conn.close()


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
    start = time.perf_counter()
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("question"), str):
        return error("Champ 'question' obligatoire (texte).", 400)
    question = payload["question"].strip()
    if not question:
        return error("Champ 'question' obligatoire.", 400)
    try:
        parsed = parse_question(question)
    except LLMError as exc:
        return error(str(exc), 502)
    if parsed["status"] == "needs_clarification":
        return jsonify({"status": "needs_clarification", "message": parsed["message"]})
    try:
        calc_request = build_calculation_request({
            key: parsed[key] for key in ("operation", "category", "start_date", "end_date")
        })
    except ValidationError as exc:
        return error(exc.message, 422)

    conn = _conn()
    try:
        # Block imports while both independent readers inspect the same dataset.
        conn.execute("BEGIN IMMEDIATE")
        python_result, sql_result = _run_calculators(calc_request)
        comparison = compare_results(python_result, sql_result)
        total_duration_ms = (time.perf_counter() - start) * 1000
        calc_id = conn.execute(
            "INSERT INTO calculations "
            "(question, request_json, python_result_json, sql_result_json, status, total_duration_ms) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (question, json.dumps(calc_request), json.dumps(python_result),
             json.dumps(sql_result), comparison["status"], total_duration_ms),
        ).lastrowid
        conn.commit()
    finally:
        conn.close()
    return jsonify({"calculation_id": calc_id})


def _run_calculators(calc_request):
    database_path = current_app.config["DATABASE_PATH"]

    def run(calculator):
        try:
            result = calculator(database_path, dict(calc_request))
            if valid_result(result):
                return result
        except Exception:
            pass  # A failed tool must not hide the other calculator's evidence.
        return {"ok": False, "error": {"code": "calculator_error", "message": "Le calculateur a échoué ou retourné un résultat invalide."}}

    with ThreadPoolExecutor(max_workers=2) as executor:
        python_future = executor.submit(run, calculate_python)
        sql_future = executor.submit(run, calculate_sql)
        return python_future.result(), sql_future.result()


def _answer(comparison, calc_request):
    if comparison["status"] != "concordance":
        return comparison["message"]
    euros, cents = divmod(comparison["result_cents"], 100)
    amount = f"{euros},{cents:02d} €"
    if calc_request["operation"] == "total_by_category":
        scope = f"dans la catégorie {calc_request['category']}"
    elif calc_request["operation"] == "total_by_period":
        scope = f"du {calc_request['start_date']} au {calc_request['end_date']} inclus"
    else:
        scope = "au total"
    return f"Vous avez dépensé {amount} {scope}."


@bp.get("/calculations/<int:calculation_id>")
def get_calculation(calculation_id):
    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM calculations WHERE id = ?", (calculation_id,)).fetchone()
        if row is None:
            return error("Calcul introuvable.", 404)
        python_result = json.loads(row["python_result_json"])
        sql_result = json.loads(row["sql_result_json"])
        calc_request = json.loads(row["request_json"])
        comparison = compare_results(python_result, sql_result)
        expense_ids = sorted({
            expense_id for result in (python_result, sql_result) if valid_result(result)
            for expense_id in result["value"]["expense_ids"]
        })
        expenses = get_expenses(conn, expense_ids)
        if not expenses["ok"]:
            return error("Impossible de consulter les preuves du calcul.", 503)
        if {expense["id"] for expense in expenses["value"]} != set(expense_ids):
            comparison = {"status": "divergence", "message": "Les preuves sont incomplètes. Le résultat ne peut pas être validé."}
        return jsonify({
            "id": row["id"], "question": row["question"], "request": calc_request,
            "answer": _answer(comparison, calc_request), "verdict": comparison["status"],
            "python": python_result, "sql": sql_result,
            "total_duration_ms": row["total_duration_ms"], "expenses": expenses["value"],
            "created_at": row["created_at"],
        })
    finally:
        conn.close()
