import sqlite3


def get_expenses(conn: sqlite3.Connection, expense_ids: list[int]) -> dict:
    if not expense_ids:
        return {"ok": True, "value": []}

    try:
        placeholders = ",".join("?" for _ in expense_ids)
        rows = conn.execute(
            f"SELECT id, date, description, category, amount_cents, source_type "
            f"FROM expenses WHERE id IN ({placeholders}) ORDER BY id ASC",
            tuple(expense_ids),
        ).fetchall()
        return {"ok": True, "value": [dict(row) for row in rows]}
    except Exception as exc:  # noqa: BLE001 - tool boundary must never crash the request
        return {"ok": False, "error": {"code": "lookup_error", "message": str(exc)}}
