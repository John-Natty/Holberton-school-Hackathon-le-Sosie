import csv
import io
import re
import sqlite3

from app.models import ValidationError, normalize_expense
from app.content_moderation import ContentBlocked, moderate_texts
from app.execution_log import log_event

REQUIRED_COLUMNS = {"date", "description", "categorie", "montant"}
DATE_SYNTAX = re.compile(r"\s*[0-9]{4}-[0-9]{2}-[0-9]{2}\s*")
AMOUNT_SYNTAX = re.compile(r"\s*[0-9]+(?:[.,][0-9]{1,2})?\s*€?\s*")


def import_csv(conn: sqlite3.Connection, file_content: bytes) -> dict:
    """Validate the whole CSV before atomically recording any expense."""
    try:
        text = file_content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValidationError("fichier CSV illisible (encodage invalide)") from exc

    reader = csv.DictReader(io.StringIO(text), strict=True)
    rows = []
    try:
        columns = reader.fieldnames
        if (not columns or len(columns) != len(set(columns))
                or not REQUIRED_COLUMNS.issubset(columns)):
            raise ValidationError("colonnes CSV invalides : date, description, categorie, montant attendues")
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValidationError(f"ligne {reader.line_num} : nombre de colonnes invalide")
            rows.append((reader.line_num, row))
    except csv.Error as exc:
        raise ValidationError("structure CSV invalide") from exc
    if not rows:
        raise ValidationError("le fichier CSV ne contient aucune dépense")

    # Structure entière validée d'abord. Tous les champs (même supplémentaires)
    # et les en-têtes sont contrôlés avant la normalisation et ses erreurs.
    def texts():
        # Les quatre noms obligatoires sont des constantes de schéma ; seuls
        # les en-têtes supplémentaires peuvent porter du texte utilisateur.
        extra_columns = [column for column in columns if column not in REQUIRED_COLUMNS]
        if extra_columns:
            yield " ".join(extra_columns)
        for _, row in rows:
            values = [row["description"], row["categorie"], *(row[key] for key in extra_columns)]
            # Seules les syntaxes purement numériques sont exclues de la modération textuelle.
            # Une date/un montant malformé passe dans la modération avant que
            # la normalisation puisse produire une erreur contenant sa valeur.
            if not DATE_SYNTAX.fullmatch(row["date"]):
                values.append(row["date"])
            if not AMOUNT_SYNTAX.fullmatch(row["montant"]):
                values.append(row["montant"])
            yield " ".join(values)

    if moderate_texts(texts(), budget_seconds=20).blocked:
        log_event("content_moderation_blocked", source="file")
        raise ContentBlocked()

    expenses = []
    for line_number, row in rows:
        try:
            expenses.append(normalize_expense(
                date=row["date"], description=row["description"],
                category=row["categorie"], amount=row["montant"], source_type="csv",
            ))
        except ValidationError as exc:
            raise ValidationError(f"ligne {line_number} : {exc.message}") from exc

    with conn:
        conn.executemany(
            "INSERT INTO expenses (date, description, category, amount_cents, source_type) "
            "VALUES (?, ?, ?, ?, ?)",
            [(e.date, e.description, e.category, e.amount_cents, e.source_type) for e in expenses],
        )
    return {"imported_count": len(expenses)}
