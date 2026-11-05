import pytest

from securebank.auth.auth import AccountLocked, LoginLimiter, authenticate
from securebank.db.connection import get_readonly_connection
from securebank.db.seed import DEMO_USERS


@pytest.fixture(scope="module")
def conn(bank_db):
    return get_readonly_connection(bank_db)


@pytest.mark.parametrize("username, password, role, customer_id", DEMO_USERS)
def test_demo_users_can_log_in(conn, username, password, role, customer_id):
    session = authenticate(conn, username, password)
    assert session is not None
    assert (session.role, session.customer_id) == (role, customer_id)


@pytest.mark.parametrize("username, password", [
    ("manager1", "wrong"),
    ("manager1", ""),
    ("manager1", "manager!2026"),          # case matters
    ("nobody", "Manager!2026"),
    ("", ""),
    ("manager1' OR '1'='1", "x' OR '1'='1"),  # SQL injection attempt
])
def test_bad_logins_fail(conn, username, password):
    assert authenticate(conn, username, password) is None


def test_lockout_after_repeated_failures(conn):
    limiter = LoginLimiter(max_attempts=3)
    for _ in range(3):
        assert authenticate(conn, "employee1", "wrong", limiter) is None
    with pytest.raises(AccountLocked):
        authenticate(conn, "employee1", "Employee!2026", limiter)  # even the right password
    assert authenticate(conn, "manager1", "Manager!2026", limiter) is not None  # others unaffected


def test_success_resets_failure_count(conn):
    limiter = LoginLimiter(max_attempts=3)
    authenticate(conn, "employee2", "wrong", limiter)
    authenticate(conn, "employee2", "wrong", limiter)
    assert authenticate(conn, "employee2", "Employee2!2026", limiter) is not None
    authenticate(conn, "employee2", "wrong", limiter)
    authenticate(conn, "employee2", "wrong", limiter)
    assert authenticate(conn, "employee2", "Employee2!2026", limiter) is not None


def test_session_cannot_be_modified(conn):
    session = authenticate(conn, "employee1", "Employee!2026")
    with pytest.raises(AttributeError):
        session.role = "manager"
