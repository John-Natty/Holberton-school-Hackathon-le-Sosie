import json
import logging
import sqlite3
import time

from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context

from app.agent import run_agent
from app.agent_state import (
    ExecutionCancelled,
    begin_agent_execution,
    get_agent_state,
    run_if_execution_active,
    start_agent,
    stop_agent,
)
from app.comparator import compare_results, valid_result
from app.csv_import import import_csv
from app.execution_log import log_event, read_execution_log
from app.expenses_lookup import get_expenses
from app.models import ValidationError
from app.test_controls import (
    is_test_mode_enabled,
    get_operation_states,
    set_operation_enabled,
)

bp = Blueprint("api", __name__)

INTERRUPTED_CODE = "agent_execution_interrupted"


def _conn():
    # Ouvre une connexion SQLite vers la base configuree pour cette app.
    from app.db import get_connection
    return get_connection(current_app.config["DATABASE_PATH"])


def error(message, status):
    # Construit une reponse d'erreur JSON uniforme pour toute l'API.
    return jsonify({"ok": False, "error": {"message": message}}), status


@bp.app_errorhandler(sqlite3.Error)
def database_error(exc):
    # La base SQLite est inaccessible (fichier supprime, verrouille...) :
    # on journalise la panne au lieu de laisser le processus planter.
    log_event("resource_failure", level=logging.ERROR, resource="database", message=str(exc))
    return error("La base de données est indisponible. Réessayez plus tard.", 503)


@bp.app_errorhandler(413)
def upload_too_large(_exc):
    # Le fichier envoye depasse la limite autorisee.
    return error("Fichier trop volumineux : limite de 2 Mio.", 413)


@bp.get("/health")
def health():
    # Verifie que le serveur repond et que la base est lisible.
    conn = _conn()
    try:
        conn.execute("SELECT 1 FROM expenses LIMIT 1")
        return jsonify({"status": "ok"})
    finally:
        conn.close()


@bp.get("/agent/state")
def get_agent_state_route():
    # Renvoie l'etat courant de l'agent : "running" ou "stopped".
    return jsonify(get_agent_state())


@bp.post("/agent/state")
def update_agent_state_route():
    # Arrete ou relance proprement l'agent (interrupteur du palier 4).
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or payload.get("status") not in ("running", "stopped"):
        return error("Champ 'status' obligatoire : 'running' ou 'stopped'.", 400)
    if payload["status"] == "stopped":
        stop_agent(payload.get("reason") if isinstance(payload.get("reason"), str) else "arret manuel")
    else:
        start_agent()
    return jsonify(get_agent_state())


@bp.get("/agent/logs")
def get_agent_logs_route():
    # Lecture seule du fichier configure, sans chemin fourni par le client.
    raw_limit = request.args.get("limit", "50")
    try:
        limit = int(raw_limit)
        logs = read_execution_log(current_app.config["EXECUTION_LOG_PATH"], limit)
    except ValueError as exc:
        return error(str(exc), 400)
    except OSError as exc:
        log_event(
            "resource_failure",
            level=logging.ERROR,
            resource="execution_log",
            error_type=type(exc).__name__,
        )
        return error("Le journal d'exécution est temporairement inaccessible.", 503)
    return jsonify({"logs": logs, "count": len(logs)})


@bp.get("/test/operations")
def get_test_operations():
    # Liste l'etat (active/desactive) de chaque operation de verify_expenses.
    if not is_test_mode_enabled():
        return error("Fonctionnalité de test désactivée.", 404)
    return jsonify(get_operation_states())


@bp.post("/test/operations")
def update_test_operations():
    # Active ou desactive une operation, uniquement en mode test/demo.
    if not is_test_mode_enabled():
        return error("Fonctionnalité de test désactivée.", 404)
    payload = request.get_json(silent=True)
    if (not isinstance(payload, dict) or not isinstance(payload.get("operation"), str)
            or not isinstance(payload.get("enabled"), bool)):
        return error("Champs 'operation' (texte) et 'enabled' (booléen) obligatoires.", 400)
    try:
        set_operation_enabled(payload["operation"], payload["enabled"])
    except ValueError as exc:
        return error(str(exc), 422)
    return jsonify(get_operation_states())


@bp.post("/imports")
def imports():
    # Importe un fichier CSV de depenses, valide en entier avant d'ecrire.
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
    # Renvoie toutes les depenses enregistrees, triees par identifiant.
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT id, date, description, category, amount_cents, source_type "
            "FROM expenses ORDER BY id ASC"
        ).fetchall()
        return jsonify([dict(row) for row in rows])
    finally:
        conn.close()


def _question_from_payload(payload):
    # Extrait et nettoie le champ "question" d'une requete JSON, ou None si absent/invalide.
    if not isinstance(payload, dict) or not isinstance(payload.get("question"), str):
        return None
    question = payload["question"].strip()
    return question or None


def _store_calculation(question, outcome, tool_trace, total_duration_ms):
    # Enregistre un calcul termine (requete, resultats, trace) pour consultation ulterieure.
    conn = _conn()
    try:
        # Block imports while both independent readers inspect the same dataset.
        conn.execute("BEGIN IMMEDIATE")
        calc_id = conn.execute(
            "INSERT INTO calculations "
            "(question, request_json, python_result_json, sql_result_json, status, "
            "total_duration_ms, tool_trace_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                question, json.dumps(outcome["request"]), json.dumps(outcome["python"]),
                json.dumps(outcome["sql"]), outcome["comparison"]["status"],
                total_duration_ms, json.dumps(tool_trace),
            ),
        ).lastrowid
        conn.commit()
        return calc_id
    finally:
        conn.close()


@bp.post("/chat")
def chat():
    # Point d'entree question -> agent -> calcul stocke. Refuse proprement si
    # l'agent est a l'arret, journalise la reception et le resultat.
    start = time.perf_counter()
    question = _question_from_payload(request.get_json(silent=True))
    if question is None:
        return error("Champ 'question' obligatoire (texte).", 400)

    execution = begin_agent_execution()
    if execution is None:
        log_event("chat_refused", level=logging.WARNING, reason="agent_stopped")
        return error("L'agent est actuellement arrêté.", 503)

    log_event("chat_request", question_len=len(question), execution_id=execution.execution_id)
    database_path = current_app.config["DATABASE_PATH"]
    final = None
    for event_type, data in run_agent(question, database_path, execution=execution):
        if event_type == "error":
            log_event("chat_response", level=logging.ERROR, status="error", message=data["message"])
            status = 503 if data.get("code") == INTERRUPTED_CODE else 502
            return error(data["message"], status)
        if event_type == "final":
            final = data
    # run_agent always yields exactly one terminal event (error or final).
    outcome = final["outcome"]
    if outcome is None:
        try:
            response = run_if_execution_active(
                execution,
                lambda: jsonify({
                    "status": "needs_clarification",
                    "message": final["answer"],
                }),
            )
        except ExecutionCancelled:
            log_event(
                "agent_execution_cancelled",
                level=logging.WARNING,
                execution_id=execution.execution_id,
                generation=execution.generation,
                checkpoint="before_final_response",
            )
            return error("L'exécution de l'agent a été interrompue par son arrêt.", 503)
        log_event("chat_response", status="needs_clarification")
        return response

    total_duration_ms = (time.perf_counter() - start) * 1000
    try:
        calc_id = run_if_execution_active(
            execution,
            lambda: _store_calculation(
                question, outcome, final["tool_trace"], total_duration_ms
            ),
        )
    except ExecutionCancelled:
        log_event(
            "agent_execution_cancelled",
            level=logging.WARNING,
            execution_id=execution.execution_id,
            generation=execution.generation,
            checkpoint="before_persistence",
        )
        return error("L'exécution de l'agent a été interrompue par son arrêt.", 503)
    log_event("chat_response", status="ok", calculation_id=calc_id, verdict=outcome["comparison"]["status"])
    return jsonify({"calculation_id": calc_id})


def _sse(event_type: str, payload: dict) -> str:
    # Met en forme une ligne d'evenement Server-Sent Events.
    return f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"


@bp.post("/chat/stream")
def chat_stream():
    # Version en flux direct de /chat : meme verification d'etat et memes
    # evenements journalises, mais la reponse est envoyee au fil de l'eau.
    start = time.perf_counter()
    question = _question_from_payload(request.get_json(silent=True))
    if question is None:
        return error("Champ 'question' obligatoire (texte).", 400)

    execution = begin_agent_execution()
    if execution is None:
        log_event("chat_refused", level=logging.WARNING, reason="agent_stopped")
        return error("L'agent est actuellement arrêté.", 503)

    log_event(
        "chat_request",
        question_len=len(question),
        stream=True,
        execution_id=execution.execution_id,
    )
    database_path = current_app.config["DATABASE_PATH"]

    @stream_with_context
    def generate():
        # Rejoue le meme generateur d'agent que /chat, en journalisant la
        # fin (succes ou erreur) exactement comme le parcours classique.
        for event_type, data in run_agent(question, database_path, execution=execution):
            if event_type == "final":
                if data["outcome"] is None:
                    try:
                        final_event = run_if_execution_active(
                            execution,
                            lambda: _sse("final", {"answer": data["answer"]}),
                        )
                    except ExecutionCancelled:
                        log_event(
                            "agent_execution_cancelled",
                            level=logging.WARNING,
                            execution_id=execution.execution_id,
                            generation=execution.generation,
                            checkpoint="before_final_response",
                        )
                        yield _sse("error", {
                            "code": INTERRUPTED_CODE,
                            "message": "L'exécution de l'agent a été interrompue par son arrêt.",
                        })
                        return
                    log_event("chat_response", status="needs_clarification", stream=True)
                    yield final_event
                    return
                # Reuse the classic persisted detail: no second agent or calculation.
                try:
                    calc_id = run_if_execution_active(
                        execution,
                        lambda: _store_calculation(
                            question, data["outcome"], data["tool_trace"],
                            (time.perf_counter() - start) * 1000,
                        ),
                    )
                    detail = get_calculation(calc_id)
                except ExecutionCancelled:
                    log_event(
                        "agent_execution_cancelled",
                        level=logging.WARNING,
                        execution_id=execution.execution_id,
                        generation=execution.generation,
                        checkpoint="before_persistence",
                    )
                    yield _sse("error", {
                        "code": INTERRUPTED_CODE,
                        "message": "L'exécution de l'agent a été interrompue par son arrêt.",
                    })
                    return
                except sqlite3.Error as exc:
                    log_event("resource_failure", level=logging.ERROR, resource="database", message=str(exc))
                    yield _sse("error", {"message": "Impossible d'enregistrer ou de consulter le calcul."})
                    return
                if isinstance(detail, tuple):
                    message = detail[0].get_json()["error"]["message"]
                    log_event("chat_response", level=logging.ERROR, status="error", stream=True, message=message)
                    yield _sse("error", {"message": message})
                    return
                log_event("chat_response", status="ok", stream=True, calculation_id=calc_id)
                yield _sse("final", detail.get_json())
                return
            if event_type == "error":
                log_event("chat_response", level=logging.ERROR, status="error", stream=True, message=data["message"])
                yield _sse("error", data)
                return
            yield _sse(event_type, data)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _answer(comparison, calc_request):
    # Compose la phrase finale en francais a partir du verdict et de la requete.
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
    # Recalcule le verdict a partir des resultats persistes et renvoie le detail complet.
    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM calculations WHERE id = ?", (calculation_id,)).fetchone()
        if row is None:
            return error("Calcul introuvable.", 404)
        python_result = json.loads(row["python_result_json"])
        sql_result = json.loads(row["sql_result_json"])
        calc_request = json.loads(row["request_json"])
        tool_trace = json.loads(row["tool_trace_json"]) if row["tool_trace_json"] else []
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
            "tool_trace": tool_trace, "created_at": row["created_at"],
        })
    finally:
        conn.close()
