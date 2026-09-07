def compare_results(python_result: dict, sql_result: dict) -> dict:
    """Decide concordance or divergence. Never picks a winner between the two."""
    if not python_result.get("ok") or not sql_result.get("ok"):
        return {
            "status": "error",
            "message": "un des deux calculateurs a echoue, aucun resultat ne peut etre valide",
        }

    python_value = python_result["value"]
    sql_value = sql_result["value"]

    same_amount = python_value["result_cents"] == sql_value["result_cents"]
    same_expenses = python_value["expense_ids"] == sql_value["expense_ids"]

    if same_amount and same_expenses:
        return {
            "status": "match",
            "result_cents": python_value["result_cents"],
            "expense_ids": python_value["expense_ids"],
        }

    return {
        "status": "divergence",
        "python": python_value,
        "sql": sql_value,
        "same_amount": same_amount,
        "same_expenses": same_expenses,
    }
