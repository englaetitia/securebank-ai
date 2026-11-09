"""Language detection and text normalisation for English, French and Arabic.

Two levels of normalisation:

- light_normalize(): for the embedding model. Fixes things that only add noise
  (Eastern Arabic digits, Arabic diacritics and tatweel, alef variants) but
  keeps French accents, which the model was trained on.
- normalize_for_rules(): for keyword rules, slots and dates. Lower-cases and
  removes all accents, so a regex only needs one spelling: "dépôt" -> "depot",
  "أكتوبر" -> "اكتوبر", "الشهر الماضية" -> "الشهر الماضيه".
"""
import re
import unicodedata

ARABIC_LETTERS = "ء-ي"
ARABIC_LETTER = re.compile(f"[{ARABIC_LETTERS}]")
ARABIC_MARKS = re.compile("[ً-ٰٟـ]")   # harakat, dagger alef, tatweel
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_ALEFS = str.maketrans("أإآٱ", "اااا")

FRENCH_WORDS = frozenset("""
    le la les un une des du de et ou est sont combien quel quelle quels quelles montant solde
    soldes compte comptes pret prets depot depots retrait retraits epargne courant mois semaine
    annee aujourd hier dernier derniere derniers dernieres ce cette ces mon ma mes moyen moyenne
    nombre janvier fevrier mars avril mai juin juillet aout septembre octobre novembre decembre
    montre donne pour seulement uniquement qui ouverts ouvert ouverture banque je tu nous vous
    sur dans
""".split())
ENGLISH_WORDS = frozenset("""
    the what how many much is are was were of in on for my show total this last month week year
    today yesterday account accounts loan loans deposit deposits withdrawal withdrawals balance
    customers average and only who give me did do does have has january february march april
    june july august october november december savings checking about
""".split())


def normalize_digits(text: str) -> str:
    return text.translate(_DIGITS)


def light_normalize(text: str) -> str:
    """Remove noise but keep the words as the embedding model knows them."""
    return ARABIC_MARKS.sub("", normalize_digits(text)).translate(_ALEFS)


def normalize_for_rules(text: str) -> str:
    """Lower-case, Western digits, no accents, one spelling per Arabic letter."""
    text = normalize_digits(text).replace("’", "'").replace("ـ", "").lower().replace("œ", "oe")
    text = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    text = unicodedata.normalize("NFC", text)   # NFD also split the hamza off ا/و/ي: now plain
    return text.replace("ة", "ه").replace("ى", "ي").replace("ٱ", "ا")


def detect_language(text: str, default: str = "en") -> str:
    """Return "ar", "fr" or "en". A question with no clear signal gets `default`."""
    if ARABIC_LETTER.search(text):
        return "ar"
    words = re.findall(r"[a-z'-]+", normalize_for_rules(text))
    french = sum(w.split("'")[-1] in FRENCH_WORDS for w in words)
    english = sum(w in ENGLISH_WORDS for w in words)
    if french > english:
        return "fr"
    if english > french:
        return "en"
    return default
