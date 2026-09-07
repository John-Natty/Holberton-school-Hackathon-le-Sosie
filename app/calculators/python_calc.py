import time

from app.db import get_connection
from app.calculation_request import build_calculation_request


def calculate_python(database_path: str, request: dict) -> dict:
    """Independent Python-side calculator.

    Opens its own SQLite connection, fetches every expense itself, filters,
    groups and sums with plain Python. Never receives the SQL calculator's
    result or row selection.
    """
    start = time.perf_counter()

    try:
        request = build_calculation_request(request)
        conn = get_connection(database_path)
        try:
            rows = conn.execute(
                "SELECT id, date, category, amount_cents FROM expenses"
            ).fetchall()
        finally:
            conn.close()

        operation = request["operation"]
        category = request.get("category")
        start_date = request.get("start_date")
        end_date = request.get("end_date")

        selected = []
        for row in rows:
            if operation == "total":
                selected.append(row)
            elif operation == "total_by_category":
                if row["category"].casefold() == category.casefold():
                    selected.append(row)
            elif operation == "total_by_period":
                if start_date <= row["date"] <= end_date:
                    selected.append(row)
            else:
                return {
                    "ok": False,
                    "error": {
                        "code": "unknown_operation",
                        "message": f"operation inconnue : {operation!r}",
                    },
                }

        result_cents = sum(row["amount_cents"] for row in selected)
        expense_ids = sorted(row["id"] for row in selected)
        duration_ms = (time.perf_counter() - start) * 1000

        return {
            "ok": True,
            "value": {
                "result_cents": result_cents,
                "expense_ids": expense_ids,
                "duration_ms": duration_ms,
            },
        }
    except Exception as exc:  # noqa: BLE001 - tool boundary must never crash the request
        return {
            "ok": False,
            "error": {"code": "python_calculator_error", "message": str(exc)},
        }
