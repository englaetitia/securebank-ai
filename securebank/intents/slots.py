"""Rule-based parameter extraction, used by the embedding fallback parser.

The embedding classifier only picks the intent; these rules pull the
parameters (period, account type, limit...) out of the question text.
The question is normalised first, so one set of rules covers English, French
and Arabic: french and Arabic periods are rewritten to English by english_period().
"""
import re

from securebank.config import DEMO_TODAY
from securebank.intents.catalog import INTENTS
from securebank.intents.dates import MONTH_ABBREVIATIONS, MONTHS, english_period

_MONTH = "|".join(sorted(list(MONTHS) + list(MONTH_ABBREVIATIONS), key=len, reverse=True))
PERIOD_PATTERNS = [
    r"\d{4}-\d{2}-\d{2}(?:\s+(?:to|until|-)\s+\d{4}-\d{2}-\d{2})?",
    r"(?:last|past)\s+\d{1,3}\s+(?:days?|months?)",
    r"today|yesterday|this week|last week|previous week|this month|last month|previous month"
    r"|this year|last year|previous year",
    rf"\b(?:{_MONTH})\b(?:,?\s+\d{{4}})?",
]
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                "eight": 8, "nine": 9, "ten": 10, "twelve": 12, "twenty": 20,
                # French
                "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "sept": 7, "huit": 8, "neuf": 9,
                "dix": 10, "douze": 12, "vingt": 20,
                # Arabic (after normalisation)
                "ثلاثه": 3, "ثلاث": 3, "اربعه": 4, "اربع": 4, "خمسه": 5, "خمس": 5, "سته": 6, "ست": 6,
                "سبعه": 7, "سبع": 7, "ثمانيه": 8, "ثماني": 8, "تسعه": 9, "تسع": 9, "عشره": 10, "عشر": 10}
LIMIT_WORDS = (r"top|largest|biggest|last|latest|recent|highest|plus grande?s?|plus gros(?:ses?)?|plus importante?s?|plus eleve(?:e?s?)?"
               r"|derniers?|dernieres?|recente?s?|اكبر|اعلي|اخر|احدث")

_SAVINGS = re.compile(r"saving|epargne|livret|توفير|ادخار")
_CHECKING = re.compile(r"checking|current account|compte courant|comptes courants|compte cheque|جاري|جاريه")
_DEPOSIT = re.compile(r"deposit|depot|versement|ايداع")
_WITHDRAWAL = re.compile(r"withdraw|retrait|سحب|سحوبات")
_ACTIVE = re.compile(r"active|open loan|current|actif|en cours|نشط|ساري|قائم|جاري")
_CLOSED = re.compile(r"closed|repaid|paid off|cloture|clos\b|ferme|rembourse|مغلق|مسدد|منته")


def find_period(question: str) -> str | None:
    text = english_period(question)
    for pattern in PERIOD_PATTERNS:
        m = re.search(pattern, text)
        if m:
            return m.group(0)
    return None


def find_number(question: str, near: str) -> int | None:
    """A small number next to a keyword: 'top 5', '3 largest', 'last six months', 'اكبر 5'."""
    text = english_period(question)
    words = "|".join(NUMBER_WORDS)
    m = re.search(rf"(?:{near})\s+(\d{{1,2}}|{words})\b|\b(\d{{1,2}}|{words})\s+(?:{near})", text)
    if not m:
        return None
    token = m.group(1) or m.group(2)
    return int(token) if token.isdigit() else NUMBER_WORDS[token]


def extract_params(question: str, intent_name: str) -> dict:
    spec = INTENTS[intent_name].params
    text = english_period(question)
    params = {}
    if "months" in spec:
        m = (re.search(r"(?:last|past|previous|next)\s+(\d{1,2}|\w+)\s+months?", text)
             or re.search(r"(\d{1,2}|\w+)\s+prochains\s+mois", text)
             or re.search(r"(?:الاشهر|الشهور|اشهر|شهور)\s+(?:ال)?(\S+)\s+(?:القادمه|المقبله)", text)
             or re.search(r"(?:ال)?(\d{1,2})\s+(?:اشهر|شهور|شهرا)\s+(?:القادمه|المقبله)", text))
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
        if _SAVINGS.search(text):
            params["account_type"] = "savings"
        elif _CHECKING.search(text):
            params["account_type"] = "checking"
    if "transaction_type" in spec:
        if _DEPOSIT.search(text):
            params["transaction_type"] = "deposit"
        elif _WITHDRAWAL.search(text):
            params["transaction_type"] = "withdrawal"
    if "loan_status" in spec:
        if _ACTIVE.search(text):
            params["loan_status"] = "active"
        elif _CLOSED.search(text):
            params["loan_status"] = "closed"
    if "limit" in spec:
        n = find_number(question, LIMIT_WORDS)
        if n:
            params["limit"] = n
    return params
