import csv
import io
import sqlite3

from app.models import ValidationError, normalize_expense

REQUIRED_COLUMNS = {"date", "description", "categorie", "montant"}


def import_csv(conn: sqlite3.Connection, file_content: bytes) -> dict:
    """Validate the whole CSV before atomically recording any expense."""
    try:
        text = file_content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValidationError("fichier CSV illisible (encodage invalide)") from exc

    reader = csv.DictReader(io.StringIO(text), strict=True)
    expenses = []
    try:
        columns = reader.fieldnames
        if (not columns or len(columns) != len(set(columns))
                or not REQUIRED_COLUMNS.issubset(columns)):
            raise ValidationError("colonnes CSV invalides : date, description, categorie, montant attendues")
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValidationError(f"ligne {reader.line_num} : nombre de colonnes invalide")
            try:
                expense = normalize_expense(
                    date=row["date"], description=row["description"],
                    category=row["categorie"], amount=row["montant"], source_type="csv",
                )
            except ValidationError as exc:
                raise ValidationError(f"ligne {reader.line_num} : {exc.message}") from exc
            expenses.append(expense)
    except csv.Error as exc:
        raise ValidationError("structure CSV invalide") from exc
    if not expenses:
        raise ValidationError("le fichier CSV ne contient aucune dépense")

    with conn:
        conn.executemany(
            "INSERT INTO expenses (date, description, category, amount_cents, source_type) "
            "VALUES (?, ?, ?, ?, ?)",
            [(e.date, e.description, e.category, e.amount_cents, e.source_type) for e in expenses],
        )
    return {"imported_count": len(expenses)}
