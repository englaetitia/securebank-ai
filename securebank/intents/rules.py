"""Keyword safety rules that run after the embedding classifier (day 7).

The embedding classifier only measures how similar a question is to the
examples, so "Delete all closed loans" looks a lot like "How many closed
loans...". These rules catch the cases where a wrong guess would matter:

1. Questions about secrets or individual people's data -> restricted_request
2. Attempts to override the assistant's rules (injection) -> restricted_request
3. Requests to change data or do something -> out_of_scope (the app is read-only)
4. Questions about the future (forecasts) -> out_of_scope (we only have past data)

The rules can only move a question to a refusal label, never to a real
query, so a false match makes the app more careful, never less.

All rules run on normalize_for_rules() text, in English, French and Arabic:
no accents, أ/إ/آ -> ا, ة -> ه, ى -> ي. Keep that in mind when adding patterns.
"""
import re

from securebank.intents.lang import ARABIC_LETTERS, normalize_for_rules

# Arabic has no \b for words with a glued "و" (and) or "ف" (so): use this instead.
AR = f"(?<![{ARABIC_LETTERS}])[وف]?"

RESTRICTED = re.compile(
    r"password|\bhash(es)?\b|users? table|admin mode|system override|\bdump\b|\bsql\b"
    r"|national id|\bssn\b|phone number|e-?mail address|home address|\baddress of\b"
    # French
    r"|mots? de passe|\bmdp\b|table (?:des )?utilisateurs|mode admin|vider la base"
    r"|carte d'identite|numero d'identite|numero de telephone|adresse e-?mail|adresse electronique"
    r"|adresse (?:personnelle|postale|du client|des clients)"
    # Arabic
    r"|كلم(?:ه|ات) (?:ال)?(?:مرور|سر)|الرمز السري|جدول المستخدمين|وضع (?:المدير|المسؤول)"
    r"|رقم (?:ال)?هويه|بطاقه (?:ال)?هويه|الرقم الوطني|رقم (?:ال)?(?:هاتف|جوال|موبايل)"
    r"|بريد الكتروني|البريد الالكتروني|ايميل|عنوان (?:ال)?(?:منزل|سكن|عميل|زبون)",
    re.IGNORECASE)
INJECTION = re.compile(
    r"\bignore\w* (?:\w+ ){0,4}(?:instructions?|rules?|restrictions?|prompts?)\b"
    r"|\bforget (?:\w+ ){0,4}(?:instructions?|rules?)\b|\byou are now\b|\bpretend\b|\bjailbreak\b"
    r"|\bdeveloper mode\b|\bact as (?:an? )?(?:admin|manager|root)\b|\breveal (?:\w+ ){0,2}prompt\b"
    # French
    r"|\b(?:ignore|oublie)[zs]? (?:\w+ ){0,4}(?:instructions?|regles?|consignes?|restrictions?)\b"
    r"|\b(?:tu es|vous etes) (?:maintenant|desormais)\b|\bfais (?:comme si|semblant)\b"
    r"|\bmode developpeur\b|\bagis comme\b|\bje suis (?:l'|le )?(?:admin\w*|directeur)\b"
    # Arabic
    rf"|{AR}تجاهل|{AR}تناس|{AR}انس (?:كل )?(?:ال)?(?:تعليمات|قواعد)|{AR}اهمل (?:كل )?(?:ال)?(?:تعليمات|قواعد)"
    r"|انت الان|تظاهر|وضع المطور|انا المدير",
    re.IGNORECASE)
CHANGE_DATA = re.compile(
    r"\b(delete|drop|remove|erase|insert|update|modify|alter|truncate|transfer|wire"
    r"|approve|reject|cancel|refund|send money|pay|close|book|reserve)\b"
    r"|\bopen (?:a|an|me|my|new)\b|\bmeeting\b|\bappointment\b"
    # French: verbs only, so "prêts clôturés" (a status) is not caught
    r"|\bsupprim\w*|\beffac\w*|\bmodifi\w*|\bmet(?:s|tre|tez) a jour\b|\bvirement\b|\bvire[rz]?\b|\btransfer\w*"
    r"|\bapprouv\w*|\brejet\w*|\bannul\w*|\bpay(?:er|ez)\b"
    r"|\bfermer|\bfermez|\bferme (?:mon|ma|le|la|ce|cette)\b|\bcloturer|\bcloturez|\bcloture (?:mon|ma|le|la|ce|cette)\b"
    r"|\bouvr(?:ir|ez|e)(?:-moi)? (?:un|une|mon|ma)\b|\brendez-?vous\b|\breserve[rz]?\b"
    # Arabic
    rf"|{AR}احذف|{AR}حذف|{AR}امسح|{AR}مسح|{AR}عدل|{AR}تعديل|{AR}حول (?:مبلغ|المال|\d|الي)|{AR}تحويل"
    rf"|{AR}وافق|{AR}ارفض|{AR}الغ(?:ي|اء)|{AR}اغلق|{AR}اغلاق|{AR}سدد|{AR}ادفع|{AR}ارسل"
    rf"|{AR}افتح|{AR}فتح حساب|{AR}موعد|{AR}احجز",
    re.IGNORECASE)
FUTURE = re.compile(
    r"\b(next (?:year|month|week|quarter)|tomorrow|forecast|predict\w*|will .* be)\b"
    r"|\b(?:mois|annee|semaine|trimestre) prochaine?\b|\bdemain\b|\bprevision\w*|\bprevoi\w*|\bpredi\w*"
    r"|\bsera\b|\bseront\b"
    rf"|(?:الشهر|السنه|العام|الاسبوع) (?:القادمه?|المقبله?)|{AR}غدا|{AR}توقع|{AR}سيكون|{AR}ستكون",
    re.IGNORECASE)


def forced_intent(question: str) -> str | None:
    """The refusal label a question must get, or None to keep the classifier's choice."""
    text = normalize_for_rules(question)
    if RESTRICTED.search(text) or INJECTION.search(text):
        return "restricted_request"
    if CHANGE_DATA.search(text):
        return "out_of_scope"
    if FUTURE.search(text):
        return "out_of_scope"
    return None
