"""Last check before an answer is shown: does it leak data or invent numbers?

1. Leak check: the answer must not contain personal data, either by pattern
   (emails, account numbers, IDs, phones) or by exact match with a real value
   from the database (customer names, emails, IDs, phones, account numbers).
2. Grounding check: every number in the answer must come from the query
   result, its parameters or its date range. This catches an LLM that
   invents or changes a figure (day 7). If either check fails, the pipeline
   shows a safe fallback answer instead.
"""
import re
import sqlite3
from dataclasses import dataclass, field

from securebank.intents.catalog import QueryResult
from securebank.security.masking import PII_PATTERNS

NUMBER = re.compile(r"(?<![\w*])-?\d[\d,]*(?:\.\d+)?")


@dataclass
class GuardResult:
    ok: bool
    problems: list = field(default_factory=list)


class KnownPII:
    """Every real personal value in the bank database, for exact-match checks."""

    def __init__(self, conn: sqlite3.Connection):
        values = set()
        for sql in ["SELECT full_name, email, phone, national_id, address FROM customers",
                    "SELECT account_number FROM accounts"]:
            for row in conn.execute(sql):
                values.update(str(v).lower() for v in row if v)
        self.values = values

    def find_in(self, text: str) -> list[str]:
        lowered = text.lower()
        return [v for v in self.values if v in lowered]


def _to_number(token: str) -> float | None:
    try:
        return float(token.replace(",", ""))
    except ValueError:
        return None


def allowed_numbers(result: QueryResult | None) -> set[float]:
    """Numbers the answer is allowed to mention."""
    allowed: set[float] = set()
    if result is None:
        return allowed
    texts = [str(v) for row in result.rows for v in row.values()]
    texts += [str(v) for v in result.params.values() if v is not None]
    if result.period:
        texts += [result.period.label, result.period.start.isoformat(), result.period.end.isoformat()]
    for text in texts:
        for token in NUMBER.findall(text):
            n = _to_number(token)
            if n is not None:
                allowed.add(abs(n))
    allowed.add(float(len(result.rows)))  # "3 accounts", "5 transactions"
    return allowed


def ungrounded_numbers(answer: str, result: QueryResult | None) -> list[str]:
    allowed = allowed_numbers(result)
    bad = []
    for token in NUMBER.findall(answer):
        n = _to_number(token)
        if n is None:
            continue
        n = abs(n)
        # exact, or the same value rounded to a whole number (14626.17 -> 14,626)
        if any(abs(n - a) < 0.005 or (n == int(n) and abs(n - round(a)) < 0.5 and a >= 100)
               for a in allowed):
            continue
        bad.append(token)
    return bad


def check_answer(answer: str, result: QueryResult | None, known_pii: KnownPII | None = None) -> GuardResult:
    problems = []
    for name, pattern in PII_PATTERNS.items():
        if pattern.search(answer):
            problems.append(f"contains a {name.replace('_', ' ')}")
    if known_pii:
        for _ in known_pii.find_in(answer):
            problems.append("contains personal data from the database")
            break
    bad = ungrounded_numbers(answer, result)
    if bad:
        problems.append(f"numbers not found in the database result: {', '.join(bad)}")
    return GuardResult(not problems, problems)
