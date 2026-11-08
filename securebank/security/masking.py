"""Second privacy layer: clean every query result before anyone sees it.

The approved SQL already avoids personal columns and masks account numbers
(layer 1). This module is the backup in case a future query, or a bug,
returns more than it should (layer 2). It runs on EVERY result.
"""
import re
from dataclasses import replace

from securebank.intents.catalog import QueryResult

# Columns that must never be shown to anyone, whatever the query returned
FORBIDDEN_COLUMNS = {
    "full_name", "email", "phone", "national_id", "address", "password_hash",
    "account_number", "customer_id", "username", "user_id",
}

# Patterns that look like personal data inside any text value
PII_PATTERNS = {
    "account_number": re.compile(r"\b[A-Z]{2}\d{2}\d{10,30}\b"),          # IBAN-like, e.g. FR76...
    "national_id": re.compile(r"\b(?:NID-\d{9}-\d{4}|CANARY-ID-\d{4})\b"),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "phone": re.compile(r"\+?\d{1,3}[-\s]\d{3}[-\s]\d{3}[-\s]\d{4}\b"),
}


def mask_account_number(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    return "****" + digits[-4:]


def mask_text(text: str) -> str:
    """Replace anything that looks like personal data in a string."""
    text = PII_PATTERNS["account_number"].sub(lambda m: mask_account_number(m.group()), text)
    text = PII_PATTERNS["national_id"].sub("[ID hidden]", text)
    text = PII_PATTERNS["email"].sub("[email hidden]", text)
    text = PII_PATTERNS["phone"].sub("[phone hidden]", text)
    return text


def sanitize_result(result: QueryResult) -> QueryResult:
    """Drop forbidden columns and mask personal data in every remaining value."""
    columns = [c for c in result.columns if c not in FORBIDDEN_COLUMNS]
    rows = []
    for row in result.rows:
        clean = {}
        for column in columns:
            value = row.get(column)
            clean[column] = mask_text(value) if isinstance(value, str) else value
        rows.append(clean)
    return replace(result, columns=columns, rows=rows)
