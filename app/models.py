import re
from dataclasses import dataclass
from datetime import date as date_cls

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
    raw = (raw or "").strip()
    if not DATE_RE.match(raw):
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
    text = (raw or "").strip()
    if not text:
        raise ValidationError("montant obligatoire")
    text = text.replace("€", "").strip()
    text = text.replace(",", ".")
    try:
        value = float(text)
    except ValueError as exc:
        raise ValidationError(f"montant invalide : {raw!r}") from exc
    if value < 0:
        raise ValidationError(f"montant negatif refuse : {raw!r}")
    cents = round(value * 100)
    return cents


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
