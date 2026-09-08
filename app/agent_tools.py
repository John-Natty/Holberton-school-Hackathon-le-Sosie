from app.test_controls import get_operation_states

ALL_OPERATIONS = ["total", "total_by_category", "total_by_period"]


def verify_expenses_tool() -> dict:
    """Build the tool definition Claude sees for this turn.

    The enum always lists all three operations: the backend, not the model,
    is the single source of truth for whether one is actually usable (see
    app.verification). Truncating the enum instead makes a model that still
    needs a disabled operation improvise a workaround with wrong arguments
    (e.g. cramming a category into "total"), which hides the real reason and
    never yields a clean operation_disabled trace. Naming disabled operations
    in the description lets Claude either avoid them on its own or call one
    anyway and get the same structured refusal either way.
    """
    states = get_operation_states()
    disabled = [op for op in ALL_OPERATIONS if not states.get(op, True)]
    description = (
        "Calcule et verifie un montant de depenses enregistrees par l'utilisateur. "
        "Execute obligatoirement deux methodes de calcul independantes (Python et SQL) "
        "puis les compare. C'est le seul moyen d'obtenir un montant verifie : "
        "n'annonce jamais de montant sans avoir appele cet outil, et ne modifie "
        "jamais le montant ou le verdict qu'il retourne."
    )
    if disabled:
        description += (
            " Attention, ces operations sont desactivees pour ce test et seront "
            f"refusees si tu les appelles : {', '.join(disabled)}."
        )
    return {
        "name": "verify_expenses",
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ALL_OPERATIONS,
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
