"""Keyword safety rules that run after the embedding classifier (day 7).

The embedding classifier only measures how similar a question is to the
examples, so "Delete all closed loans" looks a lot like "How many closed
loans...". These rules catch the cases where a wrong guess would matter:

1. Questions about secrets or individual people's data -> restricted_request
2. Requests to change data -> out_of_scope (the app is read-only)
3. Questions about the future (forecasts) -> out_of_scope (we only have past data)

The rules can only move a question to a refusal label, never to a real
query, so a false match makes the app more careful, never less.
"""
import re

RESTRICTED = re.compile(
    r"password|\bhash(es)?\b|users? table|admin mode|system override|\bdump\b|\bsql\b"
    r"|national id|\bssn\b|phone number|e-?mail address|home address|\baddress of\b",
    re.IGNORECASE)
CHANGE_DATA = re.compile(
    r"\b(delete|drop|remove|erase|insert|update|modify|alter|truncate|transfer|wire"
    r"|approve|reject|cancel|refund|send money|pay)\b", re.IGNORECASE)
FUTURE = re.compile(
    r"\b(next (?:year|month|week|quarter)|tomorrow|forecast|predict\w*|will .* be)\b", re.IGNORECASE)

def forced_intent(question: str) -> str | None:
    """The refusal label a question must get, or None to keep the classifier's choice."""
    if RESTRICTED.search(question):
        return "restricted_request"
    if CHANGE_DATA.search(question):
        return "out_of_scope"
    if FUTURE.search(question):
        return "out_of_scope"
    return None
