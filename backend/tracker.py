from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "applications.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT,
    role TEXT,
    url TEXT,
    match_score INTEGER,
    status TEXT DEFAULT 'Generated',
    date_generated TEXT,
    cv_path TEXT,
    cl_path TEXT,
    notes TEXT
);
"""


def _get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _get_connection() as conn:
        conn.execute(SCHEMA)
        conn.commit()


def save_application(data: dict[str, Any]) -> int:
    with _get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO applications
            (company, role, url, match_score, status, date_generated, cv_path, cl_path, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("company"),
                data.get("role"),
                data.get("url"),
                data.get("match_score"),
                data.get("status", "Generated"),
                data.get("date_generated"),
                data.get("cv_path"),
                data.get("cl_path"),
                data.get("notes"),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def get_all_applications() -> list[dict[str, Any]]:
    with _get_connection() as conn:
        rows = conn.execute("SELECT * FROM applications ORDER BY id DESC").fetchall()
        return [dict(row) for row in rows]


def update_status(application_id: int, status: str) -> None:
    with _get_connection() as conn:
        conn.execute("UPDATE applications SET status = ? WHERE id = ?", (status, application_id))
        conn.commit()


def update_notes(application_id: int, notes: str) -> None:
    with _get_connection() as conn:
        conn.execute("UPDATE applications SET notes = ? WHERE id = ?", (notes, application_id))
        conn.commit()


def delete_application(application_id: int) -> None:
    with _get_connection() as conn:
        conn.execute("DELETE FROM applications WHERE id = ?", (application_id,))
        conn.commit()
