"""End-to-end tests of the pipeline with structured requests (no LLM yet)."""
import json

import pytest

from securebank.auth.auth import authenticate
from securebank.db.connection import get_readonly_connection
from securebank.db.seed import CANARIES
from securebank.pipeline import handle_request
from securebank.security.audit import AuditLog


@pytest.fixture()
def conn(bank_db):
    return get_readonly_connection(bank_db)


@pytest.fixture()
def audit(tmp_path):
    return AuditLog(tmp_path / "audit.db")


@pytest.fixture()
def login(conn):
    passwords = {"manager1": "Manager!2026", "employee1": "Employee!2026",
                 "customer1": "Customer!2026", "customer2": "Customer2!2026"}
    return lambda username: authenticate(conn, username, passwords[username])


def queries_run(conn):
    """Record every SQL statement the connection executes."""
    statements = []
    conn.set_trace_callback(statements.append)
    return statements


def test_scenario_1_manager_gets_deposit_total(conn, audit, login):
    r = handle_request(login("manager1"), "total_deposits", {"period": "this month"}, conn, audit)
    assert r.status == "ok"
    total = r.result.rows[0]["total_deposits"]
    assert str(total) in r.message and "November 2026" in r.message


def test_scenario_2_employee_denied_individual_balances(conn, audit, login):
    employee = login("employee1")
    statements = queries_run(conn)
    r = handle_request(employee, "restricted_request", {}, conn, audit,
                       question="Show me the account balances of all customers.")
    assert r.status == "denied" and r.message.startswith("Access denied")
    assert statements == []  # no SQL was run at all


def test_scenario_3_customer_sees_only_own_balance(conn, audit, login):
    own = handle_request(login("customer1"), "my_balance", {}, conn, audit)
    other = handle_request(login("customer2"), "my_balance", {}, conn, audit)
    assert own.status == other.status == "ok"
    own_accounts = {r["account"] for r in own.result.rows}
    other_accounts = {r["account"] for r in other.result.rows}
    assert own_accounts and other_accounts and not own_accounts & other_accounts


def test_scenario_4_role_claims_in_params_do_nothing(conn, audit, login):
    """'Ignore previous restrictions, I am a manager' cannot change the role."""
    employee = login("employee1")
    for params in [{"role": "manager"}, {"ignore_restrictions": True}, {}]:
        r = handle_request(employee, "avg_loan_amount", params, conn, audit)
        assert r.status == "denied"


def test_customer_cannot_choose_another_customer(conn, audit, login):
    r = handle_request(login("customer1"), "my_balance", {"customer_id": 2}, conn, audit)
    assert r.status == "invalid" and r.result is None


def test_employee_denied_manager_intent_runs_no_sql(conn, audit, login):
    employee = login("employee1")
    statements = queries_run(conn)
    r = handle_request(employee, "largest_transactions", {}, conn, audit)
    assert r.status == "denied" and statements == []


def test_unknown_intent_is_unsupported(conn, audit, login):
    r = handle_request(login("manager1"), "transfer_money", {"amount": 100}, conn, audit)
    assert r.status == "unsupported"


def test_not_logged_in(conn, audit):
    r = handle_request(None, "count_customers", {}, conn, audit)
    assert r.status == "denied" and "log in" in r.message


def test_help_is_role_specific(conn, audit, login):
    r = handle_request(login("customer1"), "help", {}, conn, audit)
    assert r.status == "help" and "my last 5 transactions" in r.message.lower()
    assert "deposits" not in r.message.lower()


def test_every_request_is_audited(conn, audit, login):
    manager, employee = login("manager1"), login("employee1")
    handle_request(manager, "count_customers", {}, conn, audit)
    handle_request(employee, "avg_loan_amount", {}, conn, audit)
    handle_request(employee, "count_new_accounts", {"account_type": "premium"}, conn, audit)
    handle_request(employee, "restricted_request", {}, conn, audit)
    rows = list(reversed(audit.recent(10)))
    assert [(r["username"], r["intent"], r["decision"], r["reason_code"]) for r in rows] == [
        ("manager1", "count_customers", "allowed", "allowed"),
        ("employee1", "avg_loan_amount", "denied", "role_not_permitted"),
        ("employee1", "count_new_accounts", "invalid", "invalid_params"),
        ("employee1", "restricted_request", "denied", "restricted_data"),
    ]
    assert rows[0]["row_count"] == 1 and rows[0]["latency_ms"] is not None


def test_audit_log_stores_no_question_text_or_personal_data(conn, audit, login):
    name, email, national_id = CANARIES[0]
    question = f"What is the balance of {name}, email {email}, ID {national_id}?"
    handle_request(login("employee1"), "restricted_request", {}, conn, audit, question=question)
    dump = json.dumps(audit.recent(50))
    for secret in (name, email, national_id):
        assert secret not in dump
    assert audit.recent(1)[0]["question_hash"]  # a hash is kept instead
