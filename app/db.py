import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    source_type TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS calculations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT NOT NULL,
    request_json TEXT NOT NULL,
    python_result_json TEXT NOT NULL,
    sql_result_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def get_connection(database_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(database_path: str) -> None:
    conn = get_connection(database_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
