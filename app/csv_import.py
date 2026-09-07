import csv
import io
import sqlite3

from app.models import ValidationError, normalize_expense

REQUIRED_COLUMNS = {"date", "description", "categorie", "montant"}


def import_csv(conn: sqlite3.Connection, file_content: bytes) -> dict:
    try:
        text = file_content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValidationError("fichier CSV illisible (encodage invalide)") from exc

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or not REQUIRED_COLUMNS.issubset(
        set(reader.fieldnames)
    ):
        raise ValidationError(
            f"colonnes CSV invalides, attendu au minimum : {sorted(REQUIRED_COLUMNS)}"
        )

    imported = []
    rejected = []

    for line_number, row in enumerate(reader, start=2):
        try:
            expense = normalize_expense(
                date=row.get("date", ""),
                description=row.get("description", ""),
                category=row.get("categorie", ""),
                amount=row.get("montant", ""),
                source_type="csv",
            )
        except ValidationError as exc:
            rejected.append({"line": line_number, "reason": exc.message, "row": row})
            continue

        cursor = conn.execute(
            "INSERT INTO expenses (date, description, category, amount_cents, source_type) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                expense.date,
                expense.description,
                expense.category,
                expense.amount_cents,
                expense.source_type,
            ),
        )
        imported.append(
            {
                "id": cursor.lastrowid,
                "date": expense.date,
                "description": expense.description,
                "category": expense.category,
                "amount_cents": expense.amount_cents,
                "source_type": expense.source_type,
            }
        )

    conn.commit()
    return {"imported": imported, "rejected": rejected}
