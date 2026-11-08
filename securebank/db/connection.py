"""Database connections.

The bank database is ALWAYS opened read-only. This is enforced twice:
1. SQLite URI mode=ro: the file is opened without write permission.
2. PRAGMA query_only: SQLite refuses any statement that would change data.
"""
import sqlite3
from pathlib import Path

from securebank.config import AUDIT_DB_PATH, BANK_DB_PATH


def get_readonly_connection(db_path: Path = BANK_DB_PATH, check_same_thread: bool = True) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(
            f"{db_path} not found. Run: python -m securebank.db.seed"
        )
    uri = db_path.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, check_same_thread=check_same_thread)
    conn.execute("PRAGMA query_only = ON")
    conn.row_factory = sqlite3.Row
    return conn


def get_audit_connection(db_path: Path = AUDIT_DB_PATH, check_same_thread: bool = True) -> sqlite3.Connection:
    """Writable connection, used ONLY for the audit log (from day 3)."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path, check_same_thread=check_same_thread)
