VERIFY_EXPENSES_TOOL = {
    "name": "verify_expenses",
    "description": (
        "Calcule et verifie un montant de depenses enregistrees par l'utilisateur. "
        "Execute obligatoirement deux methodes de calcul independantes (Python et SQL) "
        "puis les compare. C'est le seul moyen d'obtenir un montant verifie : "
        "n'annonce jamais de montant sans avoir appele cet outil, et ne modifie "
        "jamais le montant ou le verdict qu'il retourne."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["total", "total_by_category", "total_by_period"],
                "description": "total (aucun parametre), total_by_category (avec category) ou total_by_period (avec start_date et end_date).",
            },
            "category": {"type": ["string", "null"]},
            "start_date": {"type": ["string", "null"], "description": "Format YYYY-MM-DD."},
            "end_date": {"type": ["string", "null"], "description": "Format YYYY-MM-DD."},
        },
        "required": ["operation", "category", "start_date", "end_date"],
        "additionalProperties": False,
    },
}


def tool_result_content(outcome: dict) -> dict:
    """What Claude sees as the tool_result content for a verify_expenses call."""
    if outcome["tool_ok"]:
        return {
            "ok": True,
            "value": {
                "verdict": "concordance",
                "result_cents": outcome["comparison"]["result_cents"],
                "expense_ids": outcome["python"]["value"]["expense_ids"],
            },
        }
    return {"ok": False, "error": outcome["tool_error"]}


def trace_entry(arguments: dict, outcome: dict) -> dict:
    """One entry of the visible agent trace, shown to the user regardless of
    whether Claude's final text acknowledges the failure."""
    if outcome["tool_ok"]:
        return {
            "tool": "verify_expenses",
            "arguments": arguments,
            "status": "success",
            "result": {
                "verdict": "concordance",
                "result_cents": outcome["comparison"]["result_cents"],
            },
        }
    return {
        "tool": "verify_expenses",
        "arguments": arguments,
        "status": "error",
        "error": outcome["tool_error"],
    }
