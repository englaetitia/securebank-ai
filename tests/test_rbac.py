"""The full role x intent permission matrix, plus the spec's security scenarios."""
import pytest

from securebank.auth.auth import Session
from securebank.intents.catalog import INTENTS
from securebank.security.rbac import allowed_intents, authorize, help_text

MANAGER = Session(1, "manager1", "manager", None)
EMPLOYEE = Session(2, "employee1", "employee", None)
CUSTOMER = Session(4, "customer1", "customer", 1)

# The expected matrix, written out by hand so a change in the catalog is noticed
EXPECTED = {
    #                         manager employee customer
    "count_new_accounts":     (True,  True,  False),
    "total_deposits":         (True,  True,  False),
    "total_withdrawals":      (True,  True,  False),
    "transaction_count":      (True,  True,  False),
    "count_active_loans":     (True,  True,  False),
    "count_customers":        (True,  True,  False),
    "avg_loan_amount":        (True,  False, False),
    "total_loan_portfolio":   (True,  False, False),
    "total_balance_by_type":  (True,  False, False),
    "avg_account_balance":    (True,  False, False),
    "new_accounts_trend":     (True,  False, False),
    "largest_transactions":   (True,  False, False),
    "spending_by_category":   (True,  False, False),
    "loan_repayment_schedule": (True, False, False),
    "balance_trend":          (True,  False, False),
    "my_balance":             (False, False, True),
    "my_recent_transactions": (False, False, True),
    "help":                   (True,  True,  True),
    "restricted_request":     (False, False, False),
    "out_of_scope":           (False, False, False),
}


def test_matrix_covers_every_intent():
    assert set(EXPECTED) == set(INTENTS)


@pytest.mark.parametrize("intent_name", EXPECTED)
@pytest.mark.parametrize("col, session", [(0, MANAGER), (1, EMPLOYEE), (2, CUSTOMER)])
def test_permission_matrix(intent_name, col, session):
    assert authorize(session, INTENTS[intent_name]).allowed == EXPECTED[intent_name][col]


@pytest.mark.parametrize("intent_name", EXPECTED)
def test_not_logged_in_is_always_denied(intent_name):
    d = authorize(None, INTENTS[intent_name])
    assert not d.allowed and d.code == "not_authenticated"


def test_scenario_2_employee_cannot_see_customer_balances():
    d = authorize(EMPLOYEE, INTENTS["restricted_request"])
    assert not d.allowed
    assert d.message.startswith("Access denied")


def test_denied_message_names_the_role():
    d = authorize(EMPLOYEE, INTENTS["avg_loan_amount"])
    assert d.code == "role_not_permitted" and "employee" in d.message


def test_customer_without_linked_account_is_denied():
    broken = Session(9, "ghost", "customer", None)
    assert authorize(broken, INTENTS["my_balance"]).code == "no_linked_customer"


def test_help_only_lists_allowed_intents():
    employee_help = help_text("employee")
    assert "Average loan amount" not in employee_help
    assert "Total value and number of deposits" in employee_help
    assert {i.name for i in allowed_intents("customer")} == {"my_balance", "my_recent_transactions"}
