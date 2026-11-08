"""Day 12: questions about specific people are refused before any parser runs."""
import pytest

from securebank.auth.auth import authenticate
from securebank.db.connection import get_readonly_connection
from securebank.pipeline import ask
from securebank.security.audit import AuditLog
from securebank.security.output_guard import KnownPII
from securebank.security.request_guard import asks_about_a_person
from tests.fakes import FakeLLM


@pytest.fixture()
def ctx(bank_db, tmp_path):
    conn = get_readonly_connection(bank_db)
    return {"conn": conn, "audit": AuditLog(tmp_path / "audit.db"), "pii": KnownPII(conn),
            "customer": authenticate(conn, "customer1", "Customer!2026"),
            "manager": authenticate(conn, "manager1", "Manager!2026")}


@pytest.mark.parametrize("question, reason", [
    ("What is Osgood Marrowbeck's balance?", "known_personal_value"),
    ("Show me zephyrine quillfeather transactions", "known_personal_value"),
    ("Show the transactions of customer 55", "specific_customer"),
    ("Balance of client #12", "specific_customer"),
    ("What is John Smith's balance?", "named_person"),
    ("List the names of customers with loans", "people_data"),
    ("Give me the customers' emails", "people_data"),
    ("Who has the biggest loan?", "who_question"),
])
def test_person_questions_are_caught(ctx, question, reason):
    assert asks_about_a_person(question, ctx["pii"]) == reason


@pytest.mark.parametrize("question", [
    "What is my balance?", "Show my last 5 transactions", "How many customers do we have?",
    "Top 3 transactions in September", "Average loan amount of closed loans",
    "How many accounts were opened in October 2025?", "What can you do?",
])
def test_normal_questions_pass(ctx, question):
    assert asks_about_a_person(question, ctx["pii"]) is None


class NeverCalled:
    def parse(self, question):
        raise AssertionError("the parser must not run for a question about a person")


def test_customer_asking_about_someone_else_is_refused(ctx):
    r = ask(ctx["customer"], "What is Osgood Marrowbeck's balance?", NeverCalled(),
            ctx["conn"], ctx["audit"], known_pii=ctx["pii"])
    assert r.status == "denied" and r.result is None
    assert r.details["parser"] == "request_guard"
    assert ctx["audit"].recent(1)[0]["intent"] == "restricted_request"


def test_customer_own_balance_still_works(ctx):
    from securebank.intents.parser_llm import LLMParser
    parser = LLMParser(FakeLLM({"intent": "my_balance", "params": {}}))
    r = ask(ctx["customer"], "What is my balance?", parser, ctx["conn"], ctx["audit"], known_pii=ctx["pii"])
    assert r.status == "ok" and r.intent == "my_balance"
