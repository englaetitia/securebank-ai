"""Days 10-11: the test set and the full evaluation runner (fake encoder, no download)."""
import csv
import json
import re

import pytest

from eval.run_full_eval import load_test_questions, run
from eval.run_parser_eval import normalize
from securebank.db.connection import get_readonly_connection
from securebank.intents.catalog import INTENTS
from securebank.intents.examples import all_examples
from securebank.intents.parser_embed import EmbeddingParser
from securebank.llm.prompts import FEW_SHOT
from tests.fakes import BagOfWordsEncoder


def _norm(text):
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


@pytest.fixture(scope="module")
def questions():
    return load_test_questions()


def test_test_set_size_and_categories(questions):
    assert len(questions) >= 140
    assert {q["category"] for q in questions} == {"answerable", "restricted", "out_of_scope", "injection"}
    answerable = {q["intent"] for q in questions if q["category"] == "answerable"}
    # The English test set is frozen for before/after comparison: newer intents are measured
    # in eval/multilingual_test.csv
    newer = {"spending_by_category", "loan_repayment_schedule", "balance_trend"}
    assert answerable == set(INTENTS) - {"restricted_request", "out_of_scope"} - newer


def test_test_set_is_valid(questions):
    for q in questions:
        assert not isinstance(normalize(q["intent"], q["params"]), str), q["question"]


def test_test_set_is_fresh(questions):
    """No test question may appear in the examples, few-shot prompts or dev set."""
    with open("eval/dev_questions.csv", encoding="utf-8") as f:
        used = {_norm(r["question"]) for r in csv.DictReader(f)}
    used |= {_norm(q) for q, _ in all_examples()} | {_norm(q) for q, _ in FEW_SHOT}
    overlap = [q["question"] for q in questions if _norm(q["question"]) in used]
    assert overlap == []
    assert len({_norm(q["question"]) for q in questions}) == len(questions)


def test_full_run_writes_results(bank_db, tmp_path, questions):
    parser = EmbeddingParser(encoder=BagOfWordsEncoder(), threshold=0.3)
    summary = run(parser, "fake", get_readonly_connection(bank_db), tmp_path, questions[:40] + questions[-10:])
    security = summary["security"]
    assert security["requests"] == 150
    assert security["leaks"] == 0
    assert security["wrong_role_answers"] == 0
    assert set(security["by_role"]) == {"manager", "employee", "customer"}
    for name in ("parser_results.csv", "security_results.csv", "summary.json",
                 "accuracy_per_intent.png", "refusals_by_role.png"):
        assert (tmp_path / name).exists(), name
    assert json.loads((tmp_path / "summary.json").read_text())["parser"] == "fake"


def test_customer_never_gets_staff_data(bank_db, tmp_path, questions):
    parser = EmbeddingParser(encoder=BagOfWordsEncoder(), threshold=0.3)
    staff_only = [q for q in questions if q["category"] == "answerable"
                  and "customer" not in INTENTS[q["intent"]].allowed_roles][:15]
    run(parser, "fake", get_readonly_connection(bank_db), tmp_path, staff_only, charts=False)
    with open(tmp_path / "security_results.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["role"] == "customer":
                assert row["status"] != "ok" or INTENTS[row["got_intent"]].self_scoped, row
