"""Audit log: one row per request, in its own database (data/audit.db).

What is stored: who (user id, username, role), which intent, the VALIDATED
parameters, the decision, how many rows came back, and the time taken.
What is NOT stored: the question text (it may contain personal data; only a
short hash is kept so repeated questions can be matched) and the results.
"""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from securebank.config import AUDIT_DB_PATH
from securebank.db.connection import get_audit_connection

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    audit_id      INTEGER PRIMARY KEY,
    timestamp     TEXT NOT NULL,
    user_id       INTEGER,
    username      TEXT,
    role          TEXT,
    intent        TEXT,
    params_json   TEXT,
    decision      TEXT NOT NULL,   -- allowed / denied / invalid / unsupported / blocked / error
    reason_code   TEXT NOT NULL,
    row_count     INTEGER,
    latency_ms    INTEGER,
    question_hash TEXT
)"""


def question_hash(question: str | None) -> str | None:
    if not question:
        return None
    return hashlib.sha256(question.strip().lower().encode()).hexdigest()[:16]


class AuditLog:
    def __init__(self, db_path: Path = AUDIT_DB_PATH, check_same_thread: bool = True):
        self.conn: sqlite3.Connection = get_audit_connection(db_path, check_same_thread)
        self.conn.execute(SCHEMA)
        self.conn.commit()

    def record(self, *, session, intent: str | None, params: dict | None, decision: str,
               reason_code: str, row_count: int | None = None, latency_ms: int | None = None,
               question: str | None = None) -> None:
        self.conn.execute(
            """INSERT INTO audit_log (timestamp, user_id, username, role, intent, params_json,
                                      decision, reason_code, row_count, latency_ms, question_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"),
             getattr(session, "user_id", None), getattr(session, "username", None),
             getattr(session, "role", None), intent,
             json.dumps(params, sort_keys=True) if params is not None else None,
             decision, reason_code, row_count, latency_ms, question_hash(question)),
        )
        self.conn.commit()

    def recent(self, n: int = 20) -> list[dict]:
        self.conn.row_factory = sqlite3.Row
        rows = self.conn.execute("SELECT * FROM audit_log ORDER BY audit_id DESC LIMIT ?", (n,)).fetchall()
        self.conn.row_factory = None
        return [dict(r) for r in rows]
