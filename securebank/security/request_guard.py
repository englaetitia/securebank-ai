"""Personal-data pre-check (added after the day 10 evaluation).

The parsers pick the NEAREST intent, so "What is Thessaly Vornhagen's
balance?" could be read as my_balance and answer with the logged-in
customer's own balance. Nothing leaks (self-scoping still applies), but the
answer is misleading. This check runs BEFORE any parser and sends questions
about specific people straight to restricted_request:

1. a real customer value from the database (name, email, phone...) appears
2. "customer 55", "client #12", "العميل رقم 55"...
3. a person's name: "John Smith's", "le solde de Jean Dupont", "رصيد محمد"
4. a request for people's names / emails / phones / addresses
5. "who ..." / "qui ..." / "من هو ..." and "which customers ..." questions
   (every approved intent is about numbers, never about naming people)

Like rules.py, it can only refuse, never unlock a query. Attacks in another
language are a classic way around English-only guards, so the patterns cover
English, French and Arabic. They run on normalize_for_rules() text, except for
names, which need the original capital letters.
"""
import re

from securebank.intents.lang import normalize_for_rules
from securebank.security.output_guard import KnownPII

PERSON_ID = re.compile(
    r"\b(?:customer|client|user|account holder|utilisateur|titulaire)s?\s*(?:number|numero|no\.?|n°|#|id)?\s*#?\d+\b"
    r"|(?:عميل|زبون|مستخدم)\s*(?:رقم|#)?\s*\d+",
    re.IGNORECASE)
# These need capital letters, so they run on the original text
_FRENCH_NAME_PART = r"[A-Z][a-zà-ÿ]+"
POSSESSIVE_NAME = re.compile(r"\b[A-Z][a-z]+ [A-Z][a-z]+'s\b")
FRENCH_OF_NAME = re.compile(rf"\b(?:de|du|d['’]|pour)\s*{_FRENCH_NAME_PART}\s+{_FRENCH_NAME_PART}\b")
_COMMON_ARABIC_NAMES = ("محمد|احمد|علي|حسن|حسين|عمر|يوسف|ابراهيم|خالد|سعيد|عبد|فاطمه|مريم|عائشه|خديجه"
                        "|سميره|ليلي|نور|هند|ساره|زينب|مصطفي|طارق|كريم|جان")
ARABIC_NAMED = re.compile(
    rf"(?:رصيد|حساب|حسابات|هاتف|بريد|عنوان|معاملات|قرض|قروض)\s+(?:{_COMMON_ARABIC_NAMES})(?![ء-ي])"
    r"|(?:السيد|السيده|الانسه)\s")
PEOPLE_DATA = re.compile(
    r"\b(?:names?|e-?mails?|phones?|addresses|address|national ids?)\b.{0,40}\b(?:customers?|clients?|users?|borrowers?|people)\b"
    r"|\b(?:customers?|clients?|users?|borrowers?)(?:'s?)?\s+(?:names?|e-?mails?|phones?|address(?:es)?)\b"
    r"|\b(?:their|his|her)\s+(?:names?|e-?mails?|phones?|address(?:es)?)\b"
    r"|\bbalances? of (?:the |all |every |each )*(?:customers?|clients?)\b"
    # French
    r"|\b(?:noms?|e-?mails?|telephones?|adresses?)\b.{0,40}\b(?:clients?|utilisateurs?|emprunteurs?|titulaires?)\b"
    r"|\b(?:leurs?|ses)\s+(?:noms?|e-?mails?|telephones?|adresses?)\b"
    r"|\b(?:soldes?|comptes?|prets?|transactions?)\s+(?:d'un|du|de|des|de tous les|de chaque)\s+(?:client|clients|titulaires?)\b"
    # Arabic
    r"|(?:اسم|اسماء|هاتف|هواتف|بريد|ايميل|عنوان|عناوين).{0,40}(?:عميل|عملاء|زبون|زبائن|مستخدم|مقترض)"
    r"|(?:اسماؤهم|اسماءهم|عناوينهم|هواتفهم)"
    r"|(?:رصيد|ارصده|حساب|حسابات)\s+(?:كل\s+|جميع\s+)?(?:ال)?(?:عميل|عملاء|زبون|زبائن)",
    re.IGNORECASE)
WHO = re.compile(
    r"^\W*who\b|^\W*which\s+(?:of\s+(?:our|the)\s+)?(?:customers?|clients?|borrowers?)\b"
    r"|^\W*qui\b|^\W*(?:quels?|quelles?)\s+(?:sont\s+les\s+)?(?:clients?|emprunteurs?)\b"
    r"|^\W*من\s+(?:هو|هي|هم|لديه|لديهم|يملك|عنده|الذي|الذين)"
    r"|^\W*(?:اي|ما هم|من هم)\s+(?:ال)?(?:عملاء|زبائن)",
    re.IGNORECASE)


def asks_about_a_person(question: str, known_pii: KnownPII | None = None) -> str | None:
    """The reason the question must be refused, or None."""
    text = normalize_for_rules(question)
    if known_pii and (known_pii.find_in(question) or known_pii.find_in(text)):
        return "known_personal_value"
    if PERSON_ID.search(text):
        return "specific_customer"
    if POSSESSIVE_NAME.search(question) or FRENCH_OF_NAME.search(question) or ARABIC_NAMED.search(text):
        return "named_person"
    if PEOPLE_DATA.search(text):
        return "people_data"
    if WHO.search(text):
        return "who_question"
    return None
