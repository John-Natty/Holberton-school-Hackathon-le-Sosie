from app.models import DATE_RE, ValidationError

OPERATIONS = {"total", "total_by_category", "total_by_period"}


def build_calculation_request(payload: dict) -> dict:
    """Validate a raw dict into a well-formed CalculationRequest.

    This is the single point where the backend enforces the contract from
    OUTILS.md, regardless of where the request came from (LLM or a direct
    API call). Neither calculator trusts this validation blindly: each one
    still checks its own inputs before running.
    """
    operation = payload.get("operation")
    if operation not in OPERATIONS:
        raise ValidationError(f"operation inconnue : {operation!r}")

    category = payload.get("category")
    start_date = payload.get("start_date")
    end_date = payload.get("end_date")

    if operation == "total":
        if category is not None or start_date is not None or end_date is not None:
            raise ValidationError("l'operation 'total' ne prend aucun parametre")
        return {
            "operation": "total",
            "category": None,
            "start_date": None,
            "end_date": None,
        }

    if operation == "total_by_category":
        if not category or not isinstance(category, str):
            raise ValidationError("categorie obligatoire pour total_by_category")
        if start_date is not None or end_date is not None:
            raise ValidationError(
                "total_by_category ne prend pas de parametre de periode"
            )
        return {
            "operation": "total_by_category",
            "category": category.strip(),
            "start_date": None,
            "end_date": None,
        }

    # total_by_period
    if category is not None:
        raise ValidationError("total_by_period ne prend pas de categorie")
    if not start_date or not end_date:
        raise ValidationError("start_date et end_date obligatoires pour total_by_period")
    if not DATE_RE.match(start_date) or not DATE_RE.match(end_date):
        raise ValidationError("start_date/end_date doivent etre au format YYYY-MM-DD")
    if start_date > end_date:
        raise ValidationError("start_date doit etre <= end_date")
    return {
        "operation": "total_by_period",
        "category": None,
        "start_date": start_date,
        "end_date": end_date,
    }
