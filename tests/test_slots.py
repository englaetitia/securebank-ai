import pytest

from securebank.intents.slots import extract_params, find_period


@pytest.mark.parametrize("question, period", [
    ("How many accounts were opened in October?", "october"),
    ("Deposits this week", "this week"),
    ("withdrawals in the last 30 days", "last 30 days"),
    ("transactions from 2026-10-01 to 2026-10-15", "2026-10-01 to 2026-10-15"),
    ("accounts opened in Oct 2025", "oct 2025"),
    ("How many customers?", None),
])
def test_find_period(question, period):
    assert find_period(question) == period


@pytest.mark.parametrize("question, intent, expected", [
    ("How many savings accounts in October?", "count_new_accounts",
     {"period": "october", "account_type": "savings"}),
    ("Top five transactions last week", "largest_transactions", {"period": "last week", "limit": 5}),
    ("openings over the past six months", "new_accounts_trend", {"months": 6}),
    ("average of closed loans", "avg_loan_amount", {"loan_status": "closed"}),
    ("show my last 3 transactions", "my_recent_transactions", {"limit": 3}),
    ("how many deposits today", "transaction_count", {"period": "today", "transaction_type": "deposit"}),
    ("How many customers do we have?", "count_customers", {}),
])
def test_extract_params(question, intent, expected):
    assert extract_params(question, intent) == expected


def test_only_params_of_the_intent_are_returned():
    # count_customers takes no params, even if the question mentions a period
    assert extract_params("How many customers joined in October?", "count_customers") == {}
