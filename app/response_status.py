"""Statut applicatif et confiance, sans interprétation de texte libre."""

CONFIDENCE_BY_STATUS = {
    "verified": "high",
    "unverified": "low",
    "needs_clarification": "uncertain",
    "security_refusal": "refused",
    "refused": "refused",
    "error": "error",
}


def with_response_status(request_info, status):
    return {**request_info, "status": status, "confidence": CONFIDENCE_BY_STATUS[status]}


def calculation_status(verdict):
    return "verified" if verdict == "concordance" else "unverified"
