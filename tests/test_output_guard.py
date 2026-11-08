from datetime import date

import pytest

from securebank.db.connection import get_readonly_connection
from securebank.intents.catalog import INTENTS, QueryResult, run_intent
from securebank.intents.dates import DateRange
from securebank.pipeline import format_result
from securebank.security.masking import sanitize_result
from securebank.security.output_guard import KnownPII, check_answer


@pytest.fixture(scope="module")
def conn(bank_db):
    return get_readonly_connection(bank_db)


@pytest.fixture(scope="module")
def pii(conn):
    return KnownPII(conn)


def deposits_result():
    return QueryResult("total_deposits", {"period": "October"},
                       DateRange(date(2026, 10, 1), date(2026, 10, 31), "October 2026"),
                       ["deposit_count", "total_deposits"],
                       [{"deposit_count": 452, "total_deposits": 151234.56}])


@pytest.mark.parametrize("answer", [
    "According to the banking database, 452 deposits totalling 151234.56 were made in October 2026.",
    "In October 2026 there were 452 deposits worth 151,234.56 in total.",
    "Deposits from 2026-10-01 to 2026-10-31: 452, total 151,235.",   # rounded to a whole number
])
def test_grounded_answers_pass(answer):
    assert check_answer(answer, deposits_result()).ok


@pytest.mark.parametrize("answer", [
    "There were 460 deposits worth 151234.56 in October 2026.",       # changed count
    "Deposits totalled 151234.56, about 12% more than September.",    # invented comparison
    "452 deposits worth 150000 in October 2026.",                     # invented round figure
])
def test_invented_numbers_are_caught(answer):
    guard = check_answer(answer, deposits_result())
    assert not guard.ok and "numbers not found" in guard.problems[0]


@pytest.mark.parametrize("answer", [
    "The customer's email is someone@example.com.",
    "Account FR7688031911408569030874 has the largest balance.",
    "The ID is NID-786579303-0001.",
])
def test_pattern_leaks_are_caught(answer):
    assert not check_answer(answer, None).ok


def test_real_customer_names_are_caught(conn, pii):
    name = conn.execute("SELECT full_name FROM customers WHERE customer_id = 10").fetchone()[0]
    guard = check_answer(f"The biggest depositor is {name}.", None, pii)
    assert not guard.ok
    assert "contains personal data from the database" in guard.problems


def test_canary_names_are_caught(pii):
    assert not check_answer("Zephyrine Quillfeather has 3 accounts.", None, pii).ok


@pytest.mark.parametrize("name", [n for n, i in INTENTS.items() if i.sql])
def test_template_answers_never_trigger_the_guard(conn, pii, name):
    """No false alarms: the plain template answer for every intent passes."""
    cid = 1 if INTENTS[name].self_scoped else None
    result = sanitize_result(run_intent(conn, name, customer_id=cid))
    guard = check_answer(format_result(result), result, pii)
    assert guard.ok, guard.problems
