import pytest

from eval.run_parser_eval import evaluate, load_questions, normalize
from securebank.intents.parser import HybridParser
from securebank.intents.parser_embed import EmbeddingParser
from securebank.intents.parser_llm import LLMParser, ParseOutcome
from securebank.intents.schemas import ParsedRequest
from tests.fakes import BagOfWordsEncoder, FakeLLM


@pytest.fixture(scope="module")
def embed():
    return EmbeddingParser(encoder=BagOfWordsEncoder(), threshold=0.3)


def test_embedding_parser_picks_nearest_intent(embed):
    out = embed.parse("How many savings accounts were opened in September?")
    assert out.request.intent == "count_new_accounts"
    assert out.request.params == {"period": "september", "account_type": "savings"}
    assert out.source == "embedding"


def test_unrelated_question_is_out_of_scope(embed):
    assert embed.parse("zzz qqq xyz").request.intent == "out_of_scope"


def test_hybrid_uses_llm_when_it_works(embed):
    llm = FakeLLM({"intent": "count_customers", "params": {}})
    out = HybridParser(LLMParser(llm), embed).parse("How many customers?")
    assert out.source == "llm" and out.request.intent == "count_customers"


def test_hybrid_falls_back_when_llm_fails(embed):
    out = HybridParser(LLMParser(FakeLLM("garbage")), embed).parse("How many savings accounts were opened?")
    assert out.source == "embedding_fallback"
    assert out.request.intent == "count_new_accounts"
    assert out.attempts == 3 and out.error  # 2 LLM attempts + 1 fallback, LLM error kept


# ---- Evaluation script --------------------------------------------------------------

class OracleParser:
    """Always right: checks the evaluation script itself."""

    def __init__(self, questions):
        self.answers = {q["question"]: q for q in questions}

    def parse(self, question):
        q = self.answers[question]
        return ParseOutcome(ParsedRequest(intent=q["intent"], params=q["params"]), "llm")


def test_dev_set_labels_are_valid():
    questions = load_questions()
    assert len(questions) >= 50
    for q in questions:
        assert not isinstance(normalize(q["intent"], q["params"]), str), q


def test_dev_set_covers_every_intent():
    from securebank.intents.catalog import INTENTS
    assert {q["intent"] for q in load_questions()} == set(INTENTS)


def test_dev_set_does_not_overlap_training_examples():
    from securebank.intents.examples import all_examples
    from securebank.llm.prompts import FEW_SHOT
    seen = {q.lower() for q, _ in all_examples()} | {q.lower() for q, _ in FEW_SHOT}
    assert not [q["question"] for q in load_questions() if q["question"].lower() in seen]


def test_oracle_scores_100_percent():
    questions = load_questions()
    summary, _ = evaluate(OracleParser(questions), questions)
    assert summary["intent_accuracy"] == summary["exact_match_accuracy"] == 1.0
    assert summary["restricted_missed"] == 0


def test_params_compared_by_meaning():
    assert normalize("total_deposits", {"period": "October"}) == normalize("total_deposits", {"period": "in october"})
    assert normalize("total_deposits", {"period": "October"}) != normalize("total_deposits", {"period": "September"})
