"""Every approved intent is checked against an independent pandas calculation."""
import re

import pandas as pd
import pytest

from securebank.config import DEMO_TODAY
from securebank.db.connection import get_readonly_connection
from securebank.intents.catalog import (INTENTS, InvalidParams, UnknownIntent,
                                        run_intent)
from securebank.intents.dates import parse_period


@pytest.fixture(scope="module")
def conn(bank_db):
    return get_readonly_connection(bank_db)


@pytest.fixture(scope="module")
def df(conn):
    tables = {}
    for t in ["customers", "accounts", "transactions", "loans"]:
        tables[t] = pd.read_sql(f"SELECT * FROM {t}", conn)
    return tables


def in_period(series, phrase):
    r = parse_period(phrase, today=DEMO_TODAY)
    return (series >= r.start.isoformat()) & (series <= r.end.isoformat())


def one(result):
    assert len(result.rows) == 1
    return result.rows[0]


PERIODS = ["all time", "today", "this week", "this month", "last month", "October", "last 30 days"]


# ---- Ground truth: SQL result == pandas result -------------------------------------

@pytest.mark.parametrize("period", PERIODS)
@pytest.mark.parametrize("account_type", [None, "savings", "checking"])
def test_count_new_accounts(conn, df, period, account_type):
    a = df["accounts"]
    mask = in_period(a.opening_date, period)
    if account_type:
        mask &= a.account_type == account_type
    got = one(run_intent(conn, "count_new_accounts", {"period": period, "account_type": account_type}))
    assert got["new_accounts"] == mask.sum()


@pytest.mark.parametrize("period", PERIODS)
@pytest.mark.parametrize("intent, ttype", [("total_deposits", "deposit"),
                                           ("total_withdrawals", "withdrawal")])
def test_total_deposits_and_withdrawals(conn, df, period, intent, ttype):
    t = df["transactions"]
    sel = t[(t.transaction_type == ttype) & in_period(t.transaction_date, period)]
    got = one(run_intent(conn, intent, {"period": period}))
    assert got[f"{ttype}_count"] == len(sel)
    assert got[f"total_{ttype}s"] == pytest.approx(round(sel.amount.sum(), 2))


@pytest.mark.parametrize("period", PERIODS)
@pytest.mark.parametrize("ttype", [None, "deposit", "withdrawal"])
def test_transaction_count(conn, df, period, ttype):
    t = df["transactions"]
    sel = t[in_period(t.transaction_date, period)]
    if ttype:
        sel = sel[sel.transaction_type == ttype]
    got = one(run_intent(conn, "transaction_count", {"period": period, "transaction_type": ttype}))
    assert got["transaction_count"] == len(sel)
    assert got["total_amount"] == pytest.approx(round(sel.amount.sum(), 2))


def test_count_active_loans(conn, df):
    active = df["loans"][df["loans"].loan_status == "active"]
    got = one(run_intent(conn, "count_active_loans"))
    assert got["active_loans"] == len(active)
    assert got["customers_with_active_loans"] == active.customer_id.nunique()


def test_count_customers(conn, df):
    assert one(run_intent(conn, "count_customers"))["customers"] == len(df["customers"])


@pytest.mark.parametrize("status", [None, "active", "closed"])
def test_avg_loan_amount(conn, df, status):
    loans = df["loans"] if status is None else df["loans"][df["loans"].loan_status == status]
    got = one(run_intent(conn, "avg_loan_amount", {"loan_status": status}))
    assert got["avg_loan_amount"] == pytest.approx(round(loans.loan_amount.mean(), 2))
    assert got["loan_count"] == len(loans)


def test_total_loan_portfolio(conn, df):
    active = df["loans"][df["loans"].loan_status == "active"]
    got = one(run_intent(conn, "total_loan_portfolio"))
    assert got["total_active_loan_amount"] == pytest.approx(round(active.loan_amount.sum(), 2))


@pytest.mark.parametrize("intent, column, agg", [("total_balance_by_type", "total_balance", "sum"),
                                                 ("avg_account_balance", "avg_balance", "mean")])
def test_balances_by_type(conn, df, intent, column, agg):
    expected = df["accounts"].groupby("account_type").balance.agg(agg).round(2).to_dict()
    got = {r["account_type"]: r[column] for r in run_intent(conn, intent).rows}
    assert got == pytest.approx(expected)


@pytest.mark.parametrize("months", [1, 3, 6, 12])
def test_new_accounts_trend(conn, df, months):
    a = df["accounts"]
    sel = a[in_period(a.opening_date, f"last {months} months")]
    expected = sel.opening_date.str[:7].value_counts().sort_index().to_dict()
    got = {r["month"]: r["new_accounts"] for r in run_intent(conn, "new_accounts_trend", {"months": months}).rows}
    assert got == expected
    assert len(got) <= months


@pytest.mark.parametrize("period, limit", [("this month", 5), ("October", 10), ("all time", 3)])
def test_largest_transactions(conn, df, period, limit):
    t = df["transactions"]
    expected = (t[in_period(t.transaction_date, period)]
                .sort_values(["amount", "transaction_id"], ascending=[False, True])
                .head(limit).transaction_id.tolist())
    result = run_intent(conn, "largest_transactions", {"period": period, "limit": limit})
    assert [r["transaction_id"] for r in result.rows] == expected


@pytest.mark.parametrize("customer_id", [1, 2, 250])
def test_my_balance_only_own_accounts(conn, df, customer_id):
    own = df["accounts"][df["accounts"].customer_id == customer_id]
    rows = run_intent(conn, "my_balance", customer_id=customer_id).rows
    assert sorted(r["balance"] for r in rows) == pytest.approx(sorted(own.balance.round(2)))


@pytest.mark.parametrize("customer_id", [1, 2])
def test_my_recent_transactions_only_own(conn, df, customer_id):
    own_ids = set(df["accounts"][df["accounts"].customer_id == customer_id].account_id)
    t = df["transactions"]
    own = t[t.account_id.isin(own_ids)]
    rows = run_intent(conn, "my_recent_transactions", {"limit": 20}, customer_id=customer_id).rows
    assert len(rows) == min(20, len(own))
    dates = [r["transaction_date"] for r in rows]
    assert dates == sorted(dates, reverse=True)
    assert dates[0] == own.transaction_date.max()


# ---- Privacy: what results never contain --------------------------------------------

SENSITIVE_COLUMNS = {"national_id", "address", "email", "phone", "full_name",
                     "account_number", "password_hash"}


@pytest.mark.parametrize("name", [n for n, i in INTENTS.items() if i.sql])
def test_no_sensitive_columns_returned(conn, name):
    result = run_intent(conn, name, customer_id=1 if INTENTS[name].self_scoped else None)
    assert not SENSITIVE_COLUMNS & set(result.columns)


def test_account_numbers_are_masked(conn):
    for name, params in [("largest_transactions", {"period": "all time", "limit": 10}),
                         ("my_balance", {}), ("my_recent_transactions", {})]:
        cid = 1 if INTENTS[name].self_scoped else None
        for row in run_intent(conn, name, params, customer_id=cid).rows:
            assert re.fullmatch(r"\*{4}\d{4}", row["account"])


# ---- Validation: bad input is rejected before any SQL runs --------------------------

@pytest.mark.parametrize("name, params", [
    ("count_new_accounts", {"account_type": "premium"}),
    ("count_new_accounts", {"period": "next month"}),
    ("count_new_accounts", {"period": "'; DROP TABLE accounts; --"}),
    ("total_deposits", {"customer_id": 5}),             # unknown param
    ("my_balance", {"customer_id": 5}),                 # cannot choose another customer
    ("largest_transactions", {"limit": 1000}),
    ("largest_transactions", {"limit": "five"}),
    ("new_accounts_trend", {"months": 0}),
    ("count_customers", {"sql": "SELECT * FROM customers"}),
])
def test_invalid_params_rejected(conn, name, params):
    with pytest.raises(InvalidParams):
        run_intent(conn, name, params, customer_id=1)


def test_unknown_intent_rejected(conn):
    with pytest.raises(UnknownIntent):
        run_intent(conn, "show_all_customers")


def test_self_scoped_intents_need_a_customer(conn):
    with pytest.raises(InvalidParams):
        run_intent(conn, "my_balance")


@pytest.mark.parametrize("name", ["help", "restricted_request", "out_of_scope"])
def test_non_query_intents_cannot_run_sql(conn, name):
    with pytest.raises(InvalidParams):
        run_intent(conn, name)


# ---- Catalog rules -----------------------------------------------------------------

def test_catalog_has_15_real_intents_plus_2_labels():
    assert len(INTENTS) == 17
    assert sum(1 for i in INTENTS.values() if i.allowed_roles) == 15


@pytest.mark.parametrize("name", [n for n, i in INTENTS.items() if i.sql])
def test_sql_is_a_single_select(name):
    sql = INTENTS[name].sql.strip()
    assert sql.upper().startswith("SELECT")
    assert ";" not in sql
    assert not re.search(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|ATTACH|PRAGMA)\b", sql, re.I)
    assert "{" not in sql and "%" not in sql  # no string formatting


def test_every_intent_has_examples():
    for intent in INTENTS.values():
        assert len(intent.examples) >= 2, intent.name
