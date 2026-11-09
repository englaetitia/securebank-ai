"""Clarifying questions, follow-ups and typo tolerance."""
import pytest

from securebank.auth.auth import authenticate
from securebank.conversation import ConversationContext, resolve_followup
from securebank.db.connection import get_readonly_connection
from securebank.intents.parser_embed import EmbeddingParser
from securebank.intents.parser_llm import LLMParser, ParseOutcome
from securebank.intents.schemas import ParsedRequest
from securebank.intents.typos import correct_typos, edit_distance
from securebank.pipeline import ask
from securebank.security.audit import AuditLog
from securebank.security.output_guard import KnownPII
from tests.fakes import BagOfWordsEncoder, FakeLLM


@pytest.fixture()
def ctx(bank_db, tmp_path):
    conn = get_readonly_connection(bank_db)
    return {"conn": conn, "audit": AuditLog(tmp_path / "audit.db"), "pii": KnownPII(conn),
            "manager": authenticate(conn, "manager1", "Manager!2026"),
            "employee": authenticate(conn, "employee1", "Employee!2026"),
            "customer": authenticate(conn, "customer1", "Customer!2026")}


def context_after(intent, params=None, lang="en"):
    context = ConversationContext()
    context.remember(intent, params or {}, lang)
    return context


# ---- Typos ---------------------------------------------------------------------------

@pytest.mark.parametrize("wrong, right", [
    ("octber", "october"), ("savngs", "savings"), ("depsits", "deposits"), ("withdrawls", "withdrawals"),
    ("acounts", "accounts"), ("custmers", "customers"), ("balence", "balance"), ("averge", "average"),
    ("octobr", "october"), ("retrais", "retrait"), ("epargn", "epargne"), ("اكتوبرر", "اكتوبر"),
])
def test_typos_are_fixed(wrong, right):
    text, fixes = correct_typos(f"show {wrong} now")
    assert right in text and fixes == [(wrong, right)]


@pytest.mark.parametrize("question", [
    "How many customers do we have?", "Quel est le solde moyen des comptes ?", "كم عدد العملاء؟",
    "What is the total amount of deposits this month?", "Show my last 5 transactions",
])
def test_correct_words_are_left_alone(question):
    assert correct_typos(question) == (question, [])


def test_names_are_not_corrected():
    assert correct_typos("balance of Jean Balence")[1] == []


@pytest.mark.parametrize("wrong, right", [("pasword", "password"), ("delte", "delete"), ("ignor", "ignore")])
def test_typos_cannot_hide_refusal_words(wrong, right):
    assert correct_typos(wrong)[0] == right


def test_edit_distance_counts_a_swap_as_one():
    assert edit_distance("laon", "loan") == 1 and edit_distance("abc", "abc") == 0


def test_typo_in_a_month_reaches_the_query(ctx):
    parser = EmbeddingParser(encoder=BagOfWordsEncoder(), threshold=0.3)
    out = parser.parse("How many savngs accounts were opened in septembr?")
    assert out.request.params.get("account_type") == "savings"
    assert out.request.params.get("period") in ("september", "septembre")


# ---- Clarifying questions ------------------------------------------------------------

class FixedParser:
    def __init__(self, intent="out_of_scope", candidates=("count_new_accounts",)):
        self.outcome = ParseOutcome(ParsedRequest(intent=intent, params={}), "embedding",
                                    candidates=list(candidates))

    def parse(self, question):
        return self.outcome


def statements_run(conn):
    statements = []
    conn.set_trace_callback(statements.append)
    return statements


def test_borderline_match_asks_instead_of_refusing(ctx):
    statements = statements_run(ctx["conn"])
    r = ask(ctx["manager"], "accounts newness?", FixedParser(), ctx["conn"], ctx["audit"], known_pii=ctx["pii"])
    assert r.status == "clarify" and r.suggestions and "Did you mean" in r.message
    assert r.result is None and statements == []
    assert ctx["audit"].recent(1)[0]["decision"] == "clarify"


def test_suggestions_only_offer_what_the_role_may_ask(ctx):
    parser = FixedParser(candidates=("avg_loan_amount", "count_customers"))
    r = ask(ctx["employee"], "loan average maybe", parser, ctx["conn"], ctx["audit"], known_pii=ctx["pii"])
    assert r.status == "clarify" and r.details["candidates"] == ["count_customers"]


def test_no_allowed_suggestion_means_a_plain_refusal(ctx):
    parser = FixedParser(candidates=("avg_loan_amount",))
    r = ask(ctx["customer"], "loan average maybe", parser, ctx["conn"], ctx["audit"], known_pii=ctx["pii"])
    assert r.status == "unsupported"


@pytest.mark.parametrize("question, lang, word", [("comptes peut-être ouverts", "fr", "Vouliez-vous"),
                                                  ("ربما حسابات", "ar", "هل تقصد")])
def test_clarifying_question_in_the_user_language(ctx, question, lang, word):
    r = ask(ctx["manager"], question, FixedParser(), ctx["conn"], ctx["audit"], known_pii=ctx["pii"])
    assert r.status == "clarify" and r.lang == lang and word in r.message


class ScriptedEncoder:
    """Gives chosen similarity scores: every question is compared with one example."""

    def __init__(self, score):
        self.score = score
        self.dims = 2

    def encode(self, texts):
        import numpy as np
        if len(texts) > 1:              # the example questions
            vectors = np.zeros((len(texts), 2))
            vectors[:, 0] = 1
            return vectors
        return np.array([[self.score, (1 - self.score ** 2) ** 0.5]])


def scripted_parser(score):
    """Every answerable example scores `score`; refusal examples score 0."""
    parser = EmbeddingParser(encoder=ScriptedEncoder(score), threshold=0.45, margin=0.10)
    for index, intent in enumerate(parser.example_intents):
        if intent in ("restricted_request", "out_of_scope"):
            parser.example_vectors[index] = [0, 1e-9]
    return parser


def test_parser_marks_borderline_scores():
    out = scripted_parser(0.40).parse("something about the bank")
    assert out.request.intent == "out_of_scope" and out.candidates


def test_parser_gives_no_candidates_for_low_scores_or_refusal_rules():
    assert scripted_parser(0.10).parse("something about the bank").candidates == []
    assert scripted_parser(0.40).parse("delete the accounts").candidates == []


def test_slot_only_question_switches_between_deposits_and_withdrawals():
    context = context_after("total_withdrawals", {"period": "october"})
    assert resolve_followup("deposits last month", context) == ("total_deposits", {"period": "last month"})


# ---- Follow-ups ----------------------------------------------------------------------

@pytest.mark.parametrize("question, expected", [
    ("and last month?", {"period": "last month"}),
    ("what about October?", {"period": "october"}),
    ("et le mois dernier ?", {"period": "last month"}),
    ("et en octobre", {"period": "october"}),
    ("والشهر الماضي؟", {"period": "last month"}),
    ("ماذا عن أكتوبر؟", {"period": "october"}),
    ("last week", {"period": "last week"}),
])
def test_period_followups(question, expected):
    context = context_after("total_deposits", {"period": "this month"})
    assert resolve_followup(question, context) == ("total_deposits", expected)


@pytest.mark.parametrize("question, value", [("only savings", "savings"), ("just checking accounts", "checking"),
                                             ("seulement épargne", "savings"), ("فقط التوفير", "savings")])
def test_account_type_followups_keep_the_period(question, value):
    context = context_after("count_new_accounts", {"period": "october"})
    assert resolve_followup(question, context) == (
        "count_new_accounts", {"period": "october", "account_type": value})


def test_withdrawals_switch_to_deposits():
    context = context_after("total_withdrawals", {"period": "october"})
    assert resolve_followup("and deposits?", context) == ("total_deposits", {"period": "october"})


@pytest.mark.parametrize("question", [
    "How many customers do we have?", "Combien de clients avons-nous ?", "كم عدد العملاء؟",
    "and the weather?",
])
def test_full_questions_are_not_followups(question):
    assert resolve_followup(question, context_after("total_withdrawals", {"period": "october"})) is None


def test_slot_the_previous_intent_does_not_take_is_not_a_followup():
    assert resolve_followup("last month", context_after("count_customers")) is None


def test_no_context_means_no_followup():
    assert resolve_followup("and last month?", None) is None
    assert resolve_followup("and last month?", ConversationContext()) is None


def test_followup_end_to_end_uses_the_period_and_language(ctx):
    context = ConversationContext()
    first = ask(ctx["manager"], "Total deposits in October", LLMParser(FakeLLM(
        {"intent": "total_deposits", "params": {"period": "October"}})), ctx["conn"], ctx["audit"],
        known_pii=ctx["pii"], context=context)
    assert first.status == "ok"
    second = ask(ctx["manager"], "et le mois dernier ?", NeverCalled(), ctx["conn"], ctx["audit"],
                 known_pii=ctx["pii"], context=context)
    assert second.status == "ok" and second.intent == "total_deposits" and second.lang == "fr"
    assert second.result.period.label == "October 2026" and second.details["parser"] == "follow_up"


class NeverCalled:
    def parse(self, question):
        raise AssertionError("a follow-up must not need the parser")


def test_refused_answers_are_not_remembered(ctx):
    context = ConversationContext()
    parser = LLMParser(FakeLLM({"intent": "avg_loan_amount", "params": {}}))
    r = ask(ctx["employee"], "Average loan amount", parser, ctx["conn"], ctx["audit"],
            known_pii=ctx["pii"], context=context)
    assert r.status == "denied" and context.last_intent is None


def test_followup_is_authorized_again(ctx):
    """A context planted for a manager intent gives an employee nothing."""
    context = context_after("largest_transactions", {"period": "this month", "limit": 5})
    r = ask(ctx["employee"], "and last month?", NeverCalled(), ctx["conn"], ctx["audit"],
            known_pii=ctx["pii"], context=context)
    assert r.status == "denied" and r.result is None


def test_followup_cannot_get_around_a_refusal_rule(ctx):
    context = context_after("total_deposits", {"period": "this month"})
    parser = LLMParser(FakeLLM({"intent": "out_of_scope", "params": {}}))
    r = ask(ctx["manager"], "delete last month", parser, ctx["conn"], ctx["audit"],
            known_pii=ctx["pii"], context=context)
    assert r.status == "unsupported"
