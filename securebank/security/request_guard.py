"""Personal-data pre-check (added after the day 10 evaluation).

The parsers pick the NEAREST intent, so "What is Thessaly Vornhagen's
balance?" could be read as my_balance and answer with the logged-in
customer's own balance. Nothing leaks (self-scoping still applies), but the
answer is misleading. This check runs BEFORE any parser and sends questions
about specific people straight to restricted_request:

1. a real customer value from the database (name, email, phone...) appears
2. "customer 55", "client #12", "user id 3"...
3. a possessive full name: "John Smith's"
4. a request for people's names / emails / phones / addresses
5. "who ..." questions (every approved intent is about numbers, never people)

Like rules.py, it can only refuse, never unlock a query.
"""
import re

from securebank.security.output_guard import KnownPII

PERSON_ID = re.compile(r"\b(?:customer|client|user|account holder)s?\s*(?:number|no\.?|#|id)?\s*#?\d+\b",
                       re.IGNORECASE)
POSSESSIVE_NAME = re.compile(r"\b[A-Z][a-z]+ [A-Z][a-z]+'s\b")
PEOPLE_DATA = re.compile(
    r"\b(?:names?|e-?mails?|phones?|addresses|address|national ids?)\b.{0,40}\b(?:customers?|clients?|users?|borrowers?|people)\b"
    r"|\b(?:customers?|clients?|users?|borrowers?)(?:'s?)?\s+(?:names?|e-?mails?|phones?|address(?:es)?)\b",
    re.IGNORECASE)
WHO = re.compile(r"^\W*who\b", re.IGNORECASE)


def asks_about_a_person(question: str, known_pii: KnownPII | None = None) -> str | None:
    """The reason the question must be refused, or None."""
    if known_pii and known_pii.find_in(question):
        return "known_personal_value"
    if PERSON_ID.search(question):
        return "specific_customer"
    if POSSESSIVE_NAME.search(question):
        return "named_person"
    if PEOPLE_DATA.search(question):
        return "people_data"
    if WHO.search(question):
        return "who_question"
    return None
