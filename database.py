"""
database.py - saves and loads plant identifications using SQLite.

SQLite is a database stored in a single file on your computer. Python includes
it (the "sqlite3" module), so there is nothing extra to install or run.

All SQL is written with "?" placeholders. That keeps data and commands
separate and protects against SQL injection.
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import config

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS identifications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    common_name     TEXT NOT NULL,
    scientific_name TEXT NOT NULL,
    confidence      TEXT NOT NULL,
    summary         TEXT NOT NULL,
    details_json    TEXT NOT NULL,  -- full validated result, including the care guide
    created_at      TEXT NOT NULL   -- UTC time, ISO format
)
"""


@contextmanager
def get_connection(db_path=None):
    """Open the database, commit on success, and always close it afterwards."""
    path = Path(db_path) if db_path else config.DATABASE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)  # create the folder if missing
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row  # lets us read columns by name
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db(db_path=None) -> None:
    """Create the table if it does not exist yet. Safe to call every start-up."""
    with get_connection(db_path) as connection:
        connection.execute(CREATE_TABLE_SQL)


def save_identification(result: dict, db_path=None) -> int:
    """Save one validated result and return its new id."""
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with get_connection(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO identifications
                (common_name, scientific_name, confidence, summary, details_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                result["common_name"],
                result["scientific_name"],
                result["confidence"],
                result["description"],
                json.dumps(result),
                created_at,
            ),
        )
        return cursor.lastrowid


def _row_to_dict(row: sqlite3.Row) -> dict:
    """Turn a database row into a normal dictionary (decoding the JSON)."""
    return {
        "id": row["id"],
        "common_name": row["common_name"],
        "scientific_name": row["scientific_name"],
        "confidence": row["confidence"],
        "summary": row["summary"],
        "created_at": row["created_at"],
        "details": json.loads(row["details_json"]),
    }


def list_identifications(db_path=None) -> list[dict]:
    """Return all saved identifications, newest first."""
    with get_connection(db_path) as connection:
        rows = connection.execute(
            "SELECT * FROM identifications ORDER BY id DESC"
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def get_identification(identification_id: int, db_path=None):
    """Return one saved identification, or None if it does not exist."""
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM identifications WHERE id = ?", (identification_id,)
        ).fetchone()
    return _row_to_dict(row) if row else None


def delete_identification(identification_id: int, db_path=None) -> bool:
    """Delete one record. Returns True if something was deleted."""
    with get_connection(db_path) as connection:
        cursor = connection.execute(
            "DELETE FROM identifications WHERE id = ?", (identification_id,)
        )
        return cursor.rowcount > 0
