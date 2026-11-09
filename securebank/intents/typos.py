"""Typo tolerance: fix misspelled banking words before parsing ("octber", "savngs").

Conservative on purpose. A word is only changed when it is unknown AND one
small edit away from a word on the banking list below. Names are left alone
(a capital letter in the middle of a sentence), and refusal words such as
"password" and "delete" are on the list so a typo cannot slip past the guards.
"""
import re

from securebank.intents.examples import all_examples
from securebank.intents.lang import normalize_for_rules

TARGETS = {
    # English
    "account", "accounts", "balance", "balances", "customer", "customers", "client", "clients",
    "deposit", "deposits", "withdrawal", "withdrawals", "withdrawn", "transaction", "transactions",
    "savings", "checking", "loan", "loans", "average", "total", "largest", "biggest", "active",
    "closed", "month", "months", "week", "year", "today", "yesterday", "recent", "latest",
    "category", "spending", "repayment", "repayments", "schedule", "trend",
    "january", "february", "march", "april", "june", "july", "august", "september", "october",
    "november", "december",
    # Refusal words: a typo must not get past the rules
    "password", "passwords", "delete", "remove", "update", "transfer", "approve", "cancel",
    "ignore", "instructions", "address", "email", "phone",
    # French
    "compte", "comptes", "solde", "soldes", "depot", "depots", "retrait", "retraits", "epargne",
    "courant", "pret", "prets", "moyenne", "montant", "nombre", "semaine", "annee", "derniers",
    "dernieres", "aujourd", "janvier", "fevrier", "avril", "juillet", "septembre", "octobre",
    "novembre", "decembre", "supprimer", "virement", "instructions",
    # Arabic (normalised spelling)
    "الرصيد", "القروض", "الحسابات", "المعاملات", "الايداعات", "السحوبات", "الشهر", "الاسبوع",
    "السنه", "يناير", "فبراير", "ابريل", "يونيو", "يوليو", "اغسطس", "سبتمبر", "اكتوبر", "نوفمبر",
    "ديسمبر", "توفير",
}
# Common words that must never be "corrected" even if close to a banking word
COMMON = set("""
    the this that these those with from what when where which many much have has had been were was
    are and for how did does our your their them they you can could would should will shall please
    show list give tell count number money amount cash bank mean sum per each all any some most more
    than over into about only just same also first second then there here want need know help
    open opened closing moan most post cost lost host roan load loads read lean mouth north
    le la les des une pour dans avec sont est quel quelle quels quelles combien moi nous vous leur
    mois jour jours mes mon ma ce cette ces qui que quoi avoir faire donne montre affiche
    الاشهر الشهور اشهر شهور شهر الايام ايام يوم اليوم السنوات السنين الاسابيع اسبوع سنه
    الحساب حساب حسابات حسابي رصيد رصيدي ارصده قرض قروض ايداع سحب عمليه عمليات معاملات
""".split())

WORD = re.compile(r"[^\W\d_]+")


def _known_words() -> set[str]:
    words = set(COMMON)
    for question, _ in all_examples():
        words.update(WORD.findall(normalize_for_rules(question)))
    return words


KNOWN = _known_words()


def edit_distance(a: str, b: str, limit: int = 2) -> int:
    """Damerau-Levenshtein distance: insert, delete, replace, swap two neighbours."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    previous2 = None
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            cost = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb))
            if previous2 is not None and i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                cost = min(cost, previous2[j - 2] + 1)
            current.append(cost)
        previous2, previous = previous, current
    return previous[-1]


def _best_target(word: str) -> str | None:
    allowed = 1 if len(word) < 7 else 2
    best, best_distance, tied = None, allowed + 1, False
    for target in sorted(TARGETS):
        distance = edit_distance(word, target, allowed)
        if distance > allowed or (distance == 2 and word[0] != target[0]):
            continue
        if distance < best_distance:
            best, best_distance, tied = target, distance, False
        elif distance == best_distance and target[:4] != best[:4]:   # "septembr": both spellings are fine
            tied = True
    return None if tied else best


def correct_typos(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Return (corrected text, [(wrong word, replacement), ...])."""
    fixes = []

    def replace(match: re.Match) -> str:
        word = match.group()
        normal = normalize_for_rules(word)
        if len(normal) < 4 or normal in KNOWN or normal in TARGETS:
            return word
        if match.start() > 0 and word[0].isupper():   # probably a name
            return word
        target = _best_target(normal)
        if target is None:
            return word
        fixes.append((word, target))
        return target

    return WORD.sub(replace, text), fixes
