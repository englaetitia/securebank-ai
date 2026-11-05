from datetime import date

import pytest

from securebank.intents.dates import DateParseError, parse_period

TODAY = date(2026, 11, 3)  # a Tuesday


@pytest.mark.parametrize("phrase, start, end", [
    ("today", "2026-11-03", "2026-11-03"),
    ("yesterday", "2026-11-02", "2026-11-02"),
    ("this week", "2026-11-02", "2026-11-03"),
    ("last week", "2026-10-26", "2026-11-01"),
    ("this month", "2026-11-01", "2026-11-03"),
    ("last month", "2026-10-01", "2026-10-31"),
    ("this year", "2026-01-01", "2026-11-03"),
    ("last year", "2025-01-01", "2025-12-31"),
    ("October", "2026-10-01", "2026-10-31"),
    ("in october", "2026-10-01", "2026-10-31"),
    ("Oct 2025", "2025-10-01", "2025-10-31"),
    ("December", "2025-12-01", "2025-12-31"),   # no year: most recent December
    ("November", "2026-11-01", "2026-11-03"),   # current month: capped at today
    ("February", "2026-02-01", "2026-02-28"),
    ("last 7 days", "2026-10-28", "2026-11-03"),
    ("the past 30 days", "2026-10-05", "2026-11-03"),
    ("last 3 months", "2026-09-01", "2026-11-03"),
    ("2026-10-15", "2026-10-15", "2026-10-15"),
    ("2026-10-01 to 2026-10-15", "2026-10-01", "2026-10-15"),
    ("This Month?", "2026-11-01", "2026-11-03"),
])
def test_supported_phrases(phrase, start, end):
    r = parse_period(phrase, today=TODAY)
    assert (r.start.isoformat(), r.end.isoformat()) == (start, end)


@pytest.mark.parametrize("phrase", [None, "", "all time", "ever"])
def test_all_time(phrase):
    r = parse_period(phrase, today=TODAY)
    assert r.label == "all time" and r.end == TODAY


@pytest.mark.parametrize("phrase", [
    "next month", "the day after tomorrow", "Smarch", "2026-13-01",
    "2026-10-15 to 2026-10-01", "last 0 days", "December 2026",
    "'; DROP TABLE accounts; --",
])
def test_unsupported_phrases_are_rejected(phrase):
    with pytest.raises(DateParseError):
        parse_period(phrase, today=TODAY)


def test_end_never_after_today():
    assert parse_period("2026-10-01 to 2027-01-01", today=TODAY).end == TODAY
