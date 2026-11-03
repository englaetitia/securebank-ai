import sqlite3

import pytest

from securebank.config import DEMO_TODAY
from securebank.db.connection import get_readonly_connection
from securebank.db.seed import CANARIES, build


def test_row_counts(bank_db):
    conn = get_readonly_connection(bank_db)
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ["customers", "accounts", "transactions", "loans", "users"]}
    assert counts == {"customers": 500, "accounts": 800, "transactions": 10_000,
                      "loans": 200, "users": 5}


def test_seed_is_reproducible(bank_db, tmp_path):
    other = build(tmp_path / "bank2.db")
    query = "SELECT SUM(amount), COUNT(*) FROM transactions WHERE transaction_type='deposit'"
    a = get_readonly_connection(bank_db).execute(query).fetchone()
    b = get_readonly_connection(other).execute(query).fetchone()
    assert tuple(a) == tuple(b)


def test_no_dates_after_demo_today(bank_db):
    conn = get_readonly_connection(bank_db)
    today = DEMO_TODAY.isoformat()
    assert conn.execute("SELECT COUNT(*) FROM transactions WHERE transaction_date > ?",
                        (today,)).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM accounts WHERE opening_date > ?",
                        (today,)).fetchone()[0] == 0


def test_transactions_after_account_opening(bank_db):
    conn = get_readonly_connection(bank_db)
    bad = conn.execute("""
        SELECT COUNT(*) FROM transactions t JOIN accounts a USING (account_id)
        WHERE t.transaction_date < a.opening_date""").fetchone()[0]
    assert bad == 0


def test_canaries_present(bank_db):
    conn = get_readonly_connection(bank_db)
    for name, _, _ in CANARIES:
        assert conn.execute("SELECT COUNT(*) FROM customers WHERE full_name = ?",
                            (name,)).fetchone()[0] == 1


def test_passwords_are_hashed(bank_db):
    conn = get_readonly_connection(bank_db)
    for (pw_hash,) in conn.execute("SELECT password_hash FROM users"):
        assert pw_hash.startswith("$2")  # bcrypt format, never plain text


@pytest.mark.parametrize("statement", [
    "INSERT INTO loans VALUES (999, 1, 100, 'active', '2026-01-01')",
    "UPDATE accounts SET balance = 0",
    "DELETE FROM transactions",
    "DROP TABLE customers",
])
def test_readonly_connection_blocks_writes(bank_db, statement):
    conn = get_readonly_connection(bank_db)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute(statement)
