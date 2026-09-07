import time

from app.db import get_connection
from app.calculation_request import build_calculation_request


def calculate_sql(database_path: str, request: dict) -> dict:
    """Independent SQL-side calculator.

    Opens its own SQLite connection and uses its own predefined,
    parameterized queries. The sum is computed by SQLite's SUM() aggregate,
    not by re-implementing Python's summation. Never receives the Python
    calculator's result or row selection.
    """
    start = time.perf_counter()

    try:
        request = build_calculation_request(request)
        operation = request["operation"]

        if operation == "total":
            where_sql = "1 = 1"
            params: tuple = ()
        elif operation == "total_by_category":
            where_sql = "category = ?"
            params = (request["category"],)
        elif operation == "total_by_period":
            where_sql = "date >= ? AND date <= ?"
            params = (request["start_date"], request["end_date"])
        else:
            return {
                "ok": False,
                "error": {
                    "code": "unknown_operation",
                    "message": f"operation inconnue : {operation!r}",
                },
            }

        conn = get_connection(database_path)
        try:
            conn.execute("BEGIN")
            sum_row = conn.execute(
                f"SELECT COALESCE(SUM(amount_cents), 0) AS total FROM expenses WHERE {where_sql}",
                params,
            ).fetchone()
            id_rows = conn.execute(
                f"SELECT id FROM expenses WHERE {where_sql} ORDER BY id ASC",
                params,
            ).fetchall()
        finally:
            conn.close()

        duration_ms = (time.perf_counter() - start) * 1000

        return {
            "ok": True,
            "value": {
                "result_cents": sum_row["total"],
                "expense_ids": [row["id"] for row in id_rows],
                "duration_ms": duration_ms,
            },
        }
    except Exception as exc:  # noqa: BLE001 - tool boundary must never crash the request
        return {
            "ok": False,
            "error": {"code": "sql_calculator_error", "message": str(exc)},
        }
