"""Rule-based parameter extraction, used by the embedding fallback parser.

The embedding classifier only picks the intent; these rules pull the
parameters (period, account type, limit...) out of the question text.
"""
import re

from securebank.config import DEMO_TODAY
from securebank.intents.catalog import INTENTS
from securebank.intents.dates import MONTH_ABBREVIATIONS, MONTHS

_MONTH = "|".join(sorted(list(MONTHS) + list(MONTH_ABBREVIATIONS), key=len, reverse=True))
PERIOD_PATTERNS = [
    r"\d{4}-\d{2}-\d{2}(?:\s+(?:to|until|-)\s+\d{4}-\d{2}-\d{2})?",
    r"(?:last|past)\s+\d{1,3}\s+(?:days?|months?)",
    r"today|yesterday|this week|last week|previous week|this month|last month|previous month"
    r"|this year|last year|previous year",
    rf"\b(?:{_MONTH})\b(?:,?\s+\d{{4}})?",
]
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                "eight": 8, "nine": 9, "ten": 10, "twelve": 12, "twenty": 20}


def find_period(question: str) -> str | None:
    text = question.lower()
    for pattern in PERIOD_PATTERNS:
        m = re.search(pattern, text)
        if m:
            return m.group(0)
    return None


def find_number(question: str, near: str) -> int | None:
    """A small number next to a keyword: 'top 5', '3 largest', 'last six months'."""
    text = question.lower()
    words = "|".join(NUMBER_WORDS)
    m = re.search(rf"(?:{near})\s+(\d{{1,2}}|{words})\b|\b(\d{{1,2}}|{words})\s+(?:{near})", text)
    if not m:
        return None
    token = m.group(1) or m.group(2)
    return int(token) if token.isdigit() else NUMBER_WORDS[token]


def extract_params(question: str, intent_name: str) -> dict:
    spec = INTENTS[intent_name].params
    text = question.lower()
    params = {}
    if "months" in spec:
        m = re.search(r"(?:last|past|previous)\s+(\d{1,2}|\w+)\s+months?", text)
        if m and (m.group(1).isdigit() or m.group(1) in NUMBER_WORDS):
            token = m.group(1)
            params["months"] = int(token) if token.isdigit() else NUMBER_WORDS[token]
        elif "this year" in text:
            params["months"] = DEMO_TODAY.month
        elif re.search(r"(?:last|past) year|12 months|twelve months", text):
            params["months"] = 12
    if "period" in spec:
        period = find_period(question)
        if period:
            params["period"] = period
    if "account_type" in spec:
        if "saving" in text:
            params["account_type"] = "savings"
        elif "checking" in text or "current account" in text:
            params["account_type"] = "checking"
    if "transaction_type" in spec:
        if "deposit" in text:
            params["transaction_type"] = "deposit"
        elif "withdraw" in text:
            params["transaction_type"] = "withdrawal"
    if "loan_status" in spec:
        if "active" in text or "open loan" in text or "current" in text:
            params["loan_status"] = "active"
        elif "closed" in text or "repaid" in text or "paid off" in text:
            params["loan_status"] = "closed"
    if "limit" in spec:
        n = find_number(question, r"top|largest|biggest|last|latest|recent|highest")
        if n:
            params["limit"] = n
    return params
