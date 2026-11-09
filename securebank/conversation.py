"""Follow-up questions: "and last month?", "only savings", "et en octobre ?", "فقط التوفير".

A follow-up reuses the previous intent and changes only the parameters the
user just mentioned. It is treated as a follow-up only when the question has
nothing in it except those parameters, so "deposits last month" (a question of
its own) goes to the parser as usual.

Security: the context only remembers an intent name and its parameters, and
only after an answer that was allowed. The new request goes through every check
in handle_request() again, with the role from the login session.
"""
import re
from dataclasses import dataclass, field

from securebank.intents.catalog import INTENTS
from securebank.intents.dates import english_period
from securebank.intents.slots import LIMIT_WORDS, NUMBER_WORDS, PERIOD_PATTERNS, extract_params

SLOT_WORDS = re.compile(
    r"\b(?:savings?|checking|current|deposits?|withdrawals?|active|closed|repaid|accounts?|loans?|transactions?"
    r"|epargne|courants?|depots?|retraits?|actifs?|clotures?|fermes?|rembourses?|comptes?|prets?"
    rf"|{LIMIT_WORDS}|\d{{1,2}}|{'|'.join(NUMBER_WORDS)})\b"
    r"|(?<![ء-ي])[وبل]?(?:ال)?(?:توفير|جاري|جاريه|ايداعات?|سحوبات|سحب|نشطه?|مغلقه?|حسابات?|قروض|قرض|معاملات)(?![ء-ي])")
FILLER_WORDS = frozenset("""
    and what about how for in the of only just please same but then with by over during on
    et pour en le la les de du des seulement uniquement au sur mais alors pareil quoi a l aux
    و في عن ماذا فقط ل خلال لكن نفس الشيء الشي من ثم بالنسبه
""".split())
# "and deposits?" after a withdrawals question moves to the matching intent
SWITCH_INTENT = {("total_withdrawals", "deposit"): "total_deposits",
                 ("total_deposits", "withdrawal"): "total_withdrawals"}


@dataclass
class ConversationContext:
    """What the assistant remembers between two questions of one logged-in session."""
    last_intent: str | None = None
    last_params: dict = field(default_factory=dict)
    last_lang: str = "en"

    def remember(self, intent: str, params: dict, lang: str) -> None:
        self.last_intent, self.last_params, self.last_lang = intent, dict(params), lang

    def clear(self) -> None:
        self.__init__()


def _only_slots(question: str) -> bool:
    """True when nothing is left once period phrases, slot words and fillers are removed."""
    text = english_period(question)
    for pattern in PERIOD_PATTERNS:
        text = re.sub(pattern, " ", text)
    text = SLOT_WORDS.sub(" ", text)
    return not [w for w in re.findall(r"[^\W\d_]+", text) if w not in FILLER_WORDS]


def _transaction_switch(question: str, intent: str) -> str | None:
    text = english_period(question)
    wanted = "deposit" if re.search(r"deposit|depot|ايداع", text) else (
        "withdrawal" if re.search(r"withdraw|retrait|سحب", text) else None)
    return SWITCH_INTENT.get((intent, wanted))


def resolve_followup(question: str, context: ConversationContext | None) -> tuple[str, dict] | None:
    """(intent, parameters) if this question continues the previous one, else None."""
    if context is None or context.last_intent is None or not _only_slots(question):
        return None
    intent = context.last_intent
    switched = _transaction_switch(question, intent)
    if switched:
        kept = {k: v for k, v in context.last_params.items() if k in INTENTS[switched].params}
        return switched, {**kept, **extract_params(question, switched)}
    changes = extract_params(question, intent)
    if not changes:
        return None
    return intent, {**context.last_params, **changes}
