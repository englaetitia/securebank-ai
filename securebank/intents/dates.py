"""Turn a period phrase ("this month", "October", "last 7 days") into exact dates.

This is plain Python on purpose: dates are the most common source of wrong
numbers, so they are never left to the LLM. The LLM (day 5) only copies the
period phrase from the question; this module decides what it means.
"""
import re
from dataclasses import dataclass
from datetime import date, timedelta

from securebank.config import DEMO_TODAY

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}
MONTH_ABBREVIATIONS = {name[:3]: number for name, number in MONTHS.items()}
ALL_TIME_START = date(1900, 1, 1)


class DateParseError(ValueError):
    """The period phrase is not one we support."""


@dataclass(frozen=True)
class DateRange:
    start: date   # inclusive
    end: date     # inclusive
    label: str    # human-readable, used in answers: "October 2026"

    def as_sql_params(self) -> dict:
        return {"start": self.start.isoformat(), "end": self.end.isoformat()}


def _first_of_month(d: date) -> date:
    return d.replace(day=1)


def _last_of_month(year: int, month: int) -> date:
    next_month = date(year + month // 12, month % 12 + 1, 1)
    return next_month - timedelta(days=1)


def _months_back(d: date, n: int) -> date:
    """First day of the month n months before d's month."""
    index = d.year * 12 + (d.month - 1) - n
    return date(index // 12, index % 12 + 1, 1)


def parse_period(phrase: str | None, today: date = DEMO_TODAY) -> DateRange:
    """Parse a period phrase. Raises DateParseError if it is not supported."""
    text = (phrase or "").strip().lower()
    text = re.sub(r"^(in|during|for|of|over|from)\s+(the\s+)?", "", text)
    text = re.sub(r"\s+", " ", text).rstrip("?.!")

    if text in ("", "all time", "ever", "overall", "total", "in total"):
        return DateRange(ALL_TIME_START, today, "all time")
    if text == "today":
        return DateRange(today, today, f"today ({today.isoformat()})")
    if text == "yesterday":
        d = today - timedelta(days=1)
        return DateRange(d, d, f"yesterday ({d.isoformat()})")
    if text == "this week":
        monday = today - timedelta(days=today.weekday())
        return DateRange(monday, today, f"this week ({monday.isoformat()} to {today.isoformat()})")
    if text in ("last week", "previous week"):
        monday = today - timedelta(days=today.weekday() + 7)
        sunday = monday + timedelta(days=6)
        return DateRange(monday, sunday, f"last week ({monday.isoformat()} to {sunday.isoformat()})")
    if text == "this month":
        start = _first_of_month(today)
        return DateRange(start, today, f"this month ({start:%B %Y}, up to {today.isoformat()})")
    if text in ("last month", "previous month"):
        start = _months_back(today, 1)
        return DateRange(start, _last_of_month(start.year, start.month), f"{start:%B %Y}")
    if text == "this year":
        start = date(today.year, 1, 1)
        return DateRange(start, today, f"{today.year} so far")
    if text in ("last year", "previous year"):
        y = today.year - 1
        return DateRange(date(y, 1, 1), date(y, 12, 31), str(y))

    m = re.fullmatch(r"(?:the )?(?:last|past) (\d{1,3}) days?", text)
    if m:
        n = int(m.group(1))
        if n < 1:
            raise DateParseError(f"Unsupported period: {phrase!r}")
        start = today - timedelta(days=n - 1)
        return DateRange(start, today, f"the last {n} days ({start.isoformat()} to {today.isoformat()})")

    m = re.fullmatch(r"(?:the )?(?:last|past) (\d{1,2}) months?", text)
    if m:
        n = int(m.group(1))
        if not 1 <= n <= 24:
            raise DateParseError(f"Unsupported period: {phrase!r}")
        start = _months_back(today, n - 1)
        return DateRange(start, today, f"the last {n} months ({start.isoformat()} to {today.isoformat()})")

    m = re.fullmatch(r"([a-z]+)(?:,? (\d{4}))?", text)
    if m and (m.group(1) in MONTHS or m.group(1) in MONTH_ABBREVIATIONS):
        month = MONTHS.get(m.group(1)) or MONTH_ABBREVIATIONS[m.group(1)]
        if m.group(2):
            year = int(m.group(2))
        else:  # no year given: the most recent such month, never the future
            year = today.year if month <= today.month else today.year - 1
        start = date(year, month, 1)
        if start > today:
            raise DateParseError(f"{phrase!r} is in the future")
        end = min(_last_of_month(year, month), today)
        return DateRange(start, end, f"{start:%B %Y}")

    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})(?: (?:to|-|until) (\d{4}-\d{2}-\d{2}))?", text)
    if m:
        try:
            start = date.fromisoformat(m.group(1))
            end = date.fromisoformat(m.group(2)) if m.group(2) else start
        except ValueError as exc:
            raise DateParseError(f"Invalid date in {phrase!r}") from exc
        if end < start:
            raise DateParseError(f"End date before start date in {phrase!r}")
        end = min(end, today)
        label = start.isoformat() if start == end else f"{start.isoformat()} to {end.isoformat()}"
        return DateRange(start, end, label)

    raise DateParseError(f"Unsupported period: {phrase!r}")
