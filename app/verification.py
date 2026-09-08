from concurrent.futures import ThreadPoolExecutor

from app.calculation_request import build_calculation_request
from app.calculators.python_calc import calculate_python
from app.calculators.sql_calc import calculate_sql
from app.comparator import compare_results, valid_result
from app.models import ValidationError
from app.test_controls import is_operation_enabled


def run_calculators(database_path: str, calc_request: dict) -> tuple[dict, dict]:
    """Run both independent calculators in parallel. Never lets one calculator's
    failure hide the other's evidence, and never lets an exception escape as a
    fabricated result."""

    def run(calculator):
        try:
            result = calculator(database_path, dict(calc_request))
            if valid_result(result):
                return result
        except Exception:
            pass
        return {
            "ok": False,
            "error": {
                "code": "calculator_error",
                "message": "Le calculateur a échoué ou retourné un résultat invalide.",
            },
        }

    with ThreadPoolExecutor(max_workers=2) as executor:
        python_future = executor.submit(run, calculate_python)
        sql_future = executor.submit(run, calculate_sql)
        return python_future.result(), sql_future.result()


def verify_expenses(database_path: str, arguments: dict) -> dict:
    """The real effect behind the verify_expenses agent tool.

    Always validates its arguments and always runs both independent
    calculators before comparing them. Never invents a number and never
    turns a divergence, a bad argument, or a calculator failure into a
    concordance.
    """
    request = arguments if isinstance(arguments, dict) else {}
    operation = request.get("operation") if isinstance(request, dict) else None

    if isinstance(operation, str) and not is_operation_enabled(operation):
        message = f"L'opération '{operation}' est désactivée pour ce test. Aucun calcul n'a été lancé."
        failure = {"ok": False, "error": {"code": "operation_disabled", "message": message}}
        return {
            "request": request,
            "python": failure,
            "sql": failure,
            "comparison": {"status": "divergence", "message": message},
            "tool_ok": False,
            "tool_error": {"code": "operation_disabled", "message": message},
        }

    try:
        calc_request = build_calculation_request(arguments)
    except ValidationError as exc:
        failure = {"ok": False, "error": {"code": "invalid_arguments", "message": exc.message}}
        return {
            "request": request,
            "python": failure,
            "sql": failure,
            "comparison": {"status": "divergence", "message": exc.message},
            "tool_ok": False,
            "tool_error": {"code": "invalid_arguments", "message": exc.message},
        }

    python_result, sql_result = run_calculators(database_path, calc_request)
    comparison = compare_results(python_result, sql_result)

    if comparison["status"] == "concordance":
        tool_ok, tool_error = True, None
    else:
        tool_ok = False
        tool_error = {"code": "verification_failed", "message": comparison["message"]}

    return {
        "request": calc_request,
        "python": python_result,
        "sql": sql_result,
        "comparison": comparison,
        "tool_ok": tool_ok,
        "tool_error": tool_error,
    }
