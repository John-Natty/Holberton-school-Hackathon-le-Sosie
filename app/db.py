import sqlite3
from pathlib import Path

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
    total_duration_ms REAL,
    tool_trace_json TEXT,
    usage_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def get_connection(database_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(database_path: str) -> None:
    Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(database_path)
    try:
        conn.executescript(SCHEMA)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(calculations)")}
        if "total_duration_ms" not in columns:
            conn.execute("ALTER TABLE calculations ADD COLUMN total_duration_ms REAL")
        if "tool_trace_json" not in columns:
            conn.execute("ALTER TABLE calculations ADD COLUMN tool_trace_json TEXT")
        if "usage_json" not in columns:
            conn.execute("ALTER TABLE calculations ADD COLUMN usage_json TEXT")
        conn.execute("UPDATE calculations SET status = 'concordance' WHERE status = 'match'")
        conn.commit()
    finally:
        conn.close()
