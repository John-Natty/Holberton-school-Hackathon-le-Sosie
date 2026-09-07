import math


def valid_result(result: dict) -> bool:
    """Reject incomplete or unsafe tool values before comparing them."""
    if not isinstance(result, dict) or result.get("ok") is not True:
        return False
    value = result.get("value")
    if not isinstance(value, dict):
        return False
    cents, ids, duration = (value.get(key) for key in ("result_cents", "expense_ids", "duration_ms"))
    return (
        type(cents) is int and 0 <= cents <= 9007199254740991
        and isinstance(ids, list) and all(type(i) is int and i > 0 for i in ids)
        and ids == sorted(set(ids))
        and type(duration) in (int, float) and math.isfinite(duration) and duration >= 0
    )


def compare_results(python_result: dict, sql_result: dict) -> dict:
    """Never select a winner or validate a failed calculator."""
    if not valid_result(python_result) or not valid_result(sql_result):
        return {
            "status": "divergence",
            "message": "Un calculateur a échoué ou retourné des données invalides. Le résultat ne peut pas être validé.",
        }
    python_value, sql_value = python_result["value"], sql_result["value"]
    if (python_value["result_cents"] == sql_value["result_cents"]
            and python_value["expense_ids"] == sql_value["expense_ids"]):
        return {"status": "concordance", "result_cents": python_value["result_cents"]}
    return {"status": "divergence", "message": "Les calculs Python et SQL divergent. Le résultat ne peut pas être validé."}
