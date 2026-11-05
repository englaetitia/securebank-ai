"""Login for the demo accounts.

Passwords are checked with bcrypt against the hashes in the users table.
The returned Session is the ONLY source of the user's role and customer_id:
nothing the user types in a question can change it.
"""
import sqlite3
import time
from dataclasses import dataclass

import bcrypt

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 300

# Used when the username does not exist, so a wrong username takes as long
# to check as a wrong password (attackers cannot tell which one was wrong).
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt())


@dataclass(frozen=True)
class Session:
    user_id: int
    username: str
    role: str                 # "manager", "employee" or "customer"
    customer_id: int | None   # set only for customers


class AccountLocked(Exception):
    """Too many failed attempts for this username."""


class LoginLimiter:
    """Counts failed logins per username and locks after too many."""

    def __init__(self, max_attempts: int = MAX_FAILED_ATTEMPTS, lockout_seconds: int = LOCKOUT_SECONDS):
        self.max_attempts = max_attempts
        self.lockout_seconds = lockout_seconds
        self._failures: dict[str, list[float]] = {}

    def check(self, username: str) -> None:
        now = time.monotonic()
        recent = [t for t in self._failures.get(username, []) if now - t < self.lockout_seconds]
        self._failures[username] = recent
        if len(recent) >= self.max_attempts:
            raise AccountLocked(f"Too many failed attempts. Try again in {self.lockout_seconds // 60} minutes.")

    def record_failure(self, username: str) -> None:
        self._failures.setdefault(username, []).append(time.monotonic())

    def reset(self, username: str) -> None:
        self._failures.pop(username, None)


def authenticate(conn: sqlite3.Connection, username: str, password: str,
                 limiter: LoginLimiter | None = None) -> Session | None:
    """Return a Session if the username and password match, else None."""
    username = (username or "").strip()
    if limiter:
        limiter.check(username)

    row = conn.execute(
        "SELECT user_id, username, password_hash, role, customer_id FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    stored_hash = row[2].encode() if row else _DUMMY_HASH
    password_ok = bcrypt.checkpw((password or "").encode(), stored_hash)

    if row is None or not password_ok:
        if limiter:
            limiter.record_failure(username)
        return None
    if limiter:
        limiter.reset(username)
    return Session(user_id=row[0], username=row[1], role=row[3], customer_id=row[4])
