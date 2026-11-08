"""Day 7: the LLM answer writer, with a fake LLM (no model download).

The LLM may only rephrase the query result. If it invents a number or leaks
personal data, the output guard catches it and the template answer is shown.
"""
import json

import pytest

from securebank.auth.auth import authenticate
from securebank.db.connection import get_readonly_connection
from securebank.db.seed import CANARIES
from securebank.intents.catalog import run_intent
from securebank.llm.answer import (MAX_LLM_ROWS, AnswerWriter, build_answer_messages,
                                   result_payload)
from securebank.pipeline import ask, format_result, handle_request
from securebank.security.audit import AuditLog
from securebank.security.output_guard import KnownPII
from tests.fakes import FakeLLM, RuleLLM


@pytest.fixture()
def ctx(bank_db, tmp_path):
    conn = get_readonly_connection(bank_db)
    return {"conn": conn, "audit": AuditLog(tmp_path / "audit.db"), "pii": KnownPII(conn),
            "manager": authenticate(conn, "manager1", "Manager!2026"),
            "employee": authenticate(conn, "employee1", "Employee!2026")}


def run(ctx, intent, params, writer, user="manager"):
    return handle_request(ctx[user], intent, params, ctx["conn"], ctx["audit"],
                          known_pii=ctx["pii"], write_answer=writer)


def deposits_this_month(ctx):
    return run_intent(ctx["conn"], "total_deposits", {"period": "this month"})


# ---- the prompt ---------------------------------------------------------------

def test_prompt_contains_result_but_not_the_question(ctx):
    result = deposits_this_month(ctx)
    messages = build_answer_messages(result)
    last = json.loads(messages[-1]["content"])
    assert last == json.loads(json.dumps(result_payload(result), default=str))
    assert "November 2026" in last["period"] and last["rows"] == result.rows
    # the user's question is never given to the answer writer (no injection channel)
    assert all("question" not in m["content"].lower() for m in messages[1:])


def test_prompt_rows_are_already_masked(ctx):
    result = run_intent(ctx["conn"], "largest_transactions", {"limit": 3})
    from securebank.security.masking import sanitize_result
    payload = json.dumps(result_payload(sanitize_result(result)))
    assert "****" in payload
    assert not ctx["pii"].find_in(payload)


# ---- good answers pass ------------------------------------------------------

def test_good_llm_answer_is_used(ctx):
    result = deposits_this_month(ctx)
    row = result.rows[0]
    good = (f"So far in November 2026 there were {row['deposit_count']} deposits, "
            f"worth {row['total_deposits']:,} in total.")
    writer = AnswerWriter(FakeLLM(good))
    r = run(ctx, "total_deposits", {"period": "this month"}, writer)
    assert r.status == "ok" and r.message == good and r.answer_source == "llm"


def test_rounded_money_is_accepted(ctx):
    row = deposits_this_month(ctx).rows[0]
    answer = f"About {round(row['total_deposits']):,} was deposited in November 2026."
    r = run(ctx, "total_deposits", {"period": "this month"}, AnswerWriter(FakeLLM(answer)))
    assert r.answer_source == "llm"


# ---- bad answers fall back to the template -----------------------------------

def test_invented_number_falls_back_to_template(ctx):
    writer = AnswerWriter(FakeLLM("In November 2026 there were 9999 deposits worth 1,000,000."))
    r = run(ctx, "total_deposits", {"period": "this month"}, writer)
    assert r.status == "ok" and r.answer_source == "fallback_template"
    assert r.message == format_result(r.result)
    assert "9999" in " ".join(r.details["guard"])
    last = ctx["audit"].recent(1)[0]
    assert last["reason_code"] == "fallback_template"


def test_leaked_canary_falls_back_to_template(ctx):
    name = CANARIES[0][0]
    writer = AnswerWriter(RuleLLM(lambda _: f"The bank has customers such as {name}."))
    r = run(ctx, "count_customers", {}, writer)
    assert r.answer_source == "fallback_template"
    assert name.lower() not in r.message.lower()


def test_leaked_email_pattern_falls_back(ctx):
    writer = AnswerWriter(FakeLLM("Contact jane.doe@example.com for the 500 customers."))
    r = run(ctx, "count_customers", {}, writer)
    assert r.answer_source == "fallback_template" and "@" not in r.message


def test_crashing_llm_uses_template(ctx):
    class Broken:
        def generate(self, messages, max_new_tokens=128):
            raise RuntimeError("CUDA out of memory")
    writer = AnswerWriter(Broken())
    r = run(ctx, "count_customers", {}, writer)
    assert r.status == "ok" and r.answer_source == "template"


def test_empty_llm_output_uses_template(ctx):
    r = run(ctx, "count_customers", {}, AnswerWriter(FakeLLM("   ")))
    assert r.answer_source == "template" and r.message == format_result(r.result)


def test_long_results_skip_the_llm(ctx):
    llm = FakeLLM("should not be called")
    r = run(ctx, "new_accounts_trend", {"months": MAX_LLM_ROWS + 3}, AnswerWriter(llm))
    assert r.answer_source == "template" and llm.calls == []


def test_long_answer_is_cut(ctx):
    row_count = run_intent(ctx["conn"], "count_customers").rows[0]["customers"]
    text = f"The bank has {row_count} customers. " + "Very good. " * 200
    r = run(ctx, "count_customers", {}, AnswerWriter(FakeLLM(text)))
    assert len(r.message) <= 600


# ---- the writer never runs for refused requests --------------------------------

def test_denied_request_never_calls_the_writer(ctx):
    llm = FakeLLM("anything")
    r = run(ctx, "largest_transactions", {}, AnswerWriter(llm), user="employee")
    assert r.status == "denied" and llm.calls == []


def test_ask_end_to_end_with_fake_llms(ctx):
    parser_llm = FakeLLM({"intent": "count_customers", "params": {}})
    from securebank.intents.parser_llm import LLMParser
    customers = run_intent(ctx["conn"], "count_customers").rows[0]["customers"]
    writer = AnswerWriter(FakeLLM(f"SecureBank currently serves {customers} customers."))
    r = ask(ctx["manager"], "How many clients do we have?", LLMParser(parser_llm),
            ctx["conn"], ctx["audit"], known_pii=ctx["pii"], write_answer=writer)
    assert r.status == "ok" and r.answer_source == "llm"
    assert r.details["parser"] == "llm" and r.details["intent"] == "count_customers"
