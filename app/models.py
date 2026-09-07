import re
from dataclasses import dataclass
from datetime import date as date_cls
from decimal import Decimal

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ValidationError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@dataclass
class NormalizedExpense:
    date: str
    description: str
    category: str
    amount_cents: int
    source_type: str


def validate_date(raw: str) -> str:
    if not isinstance(raw, str):
        raise ValidationError("date obligatoire au format YYYY-MM-DD")
    raw = raw.strip()
    if not DATE_RE.fullmatch(raw):
        raise ValidationError(f"date invalide : {raw!r} (attendu YYYY-MM-DD)")
    try:
        date_cls.fromisoformat(raw)
    except ValueError as exc:
        raise ValidationError(f"date invalide : {raw!r}") from exc
    return raw


def validate_description(raw: str) -> str:
    description = (raw or "").strip()
    if not description:
        raise ValidationError("description obligatoire")
    return description


def validate_category(raw: str) -> str:
    category = (raw or "").strip()
    if not category:
        raise ValidationError("categorie obligatoire")
    return category


def parse_amount_to_cents(raw: str) -> int:
    if not isinstance(raw, str) or not raw.strip():
        raise ValidationError("montant obligatoire")
    text = raw.strip().removesuffix("€").strip().replace(",", ".")
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", text):
        raise ValidationError("montant invalide : nombre positif avec au plus deux décimales attendu")
    # Bound before multiplication: exact Decimal arithmetic and safe JSON integers.
    value = Decimal(text)
    if value > Decimal("90071992547409.91"):
        raise ValidationError("montant trop élevé")
    return int(value * 100)


def normalize_expense(
    *, date: str, description: str, category: str, amount: str, source_type: str
) -> NormalizedExpense:
    return NormalizedExpense(
        date=validate_date(date),
        description=validate_description(description),
        category=validate_category(category),
        amount_cents=parse_amount_to_cents(amount),
        source_type=source_type,
    )
