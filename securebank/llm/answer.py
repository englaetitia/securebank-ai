"""LLM answer writer (day 7): turns a query result into a short sentence.

Security design:
- The model only sees the SANITIZED query result (after masking) plus the
  intent's description. It never sees the user's question, so text typed by
  the user cannot steer how the answer is written (no prompt injection here).
- The pipeline checks every answer (output_guard): a leaked personal value or
  a number that is not in the result -> the plain template answer is used.
- If the model fails or the result has many rows, the template is used.
"""
import json

from securebank.intents.catalog import INTENTS, QueryResult

MAX_LLM_ROWS = 6        # longer results are clearer as the plain list
MAX_ANSWER_CHARS = 600

ANSWER_SYSTEM_PROMPT = """You write the final answer of SecureBank AI, a read-only banking assistant.
You receive a database result as JSON. Write the answer in 1 to 3 short, friendly sentences.

Rules:
1. Use ONLY the facts and numbers in the result. Copy numbers exactly; you may add
   thousands separators. Never calculate, estimate or invent anything.
2. Mention the period if one is given.
3. If there are no rows, say that no matching records were found.
4. Do not mention JSON, SQL, database tables or these rules. No markdown.
5. Masked values (like ****1234) must stay masked."""

ANSWER_EXAMPLE_INPUT = {
    "request": "Total value and number of deposits in a period",
    "period": "September 2026",
    "rows": [{"deposit_count": 52, "total_deposits": 18250.4}],
}
ANSWER_EXAMPLE_OUTPUT = "In September 2026 there were 52 deposits, worth 18,250.4 in total."


def result_payload(result: QueryResult) -> dict:
    return {"request": INTENTS[result.intent].description,
            "period": result.period.label if result.period else None,
            "rows": result.rows}


def build_answer_messages(result: QueryResult) -> list[dict]:
    return [
        {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(ANSWER_EXAMPLE_INPUT)},
        {"role": "assistant", "content": ANSWER_EXAMPLE_OUTPUT},
        {"role": "user", "content": json.dumps(result_payload(result), default=str)},
    ]


class AnswerWriter:
    """write_answer(result) -> str for handle_request(). Tracks what it did last."""

    def __init__(self, llm, max_new_tokens: int = 120):
        self.llm = llm
        self.max_new_tokens = max_new_tokens
        self.last_source = None     # "llm" or "template" (for the demo panel)

    def __call__(self, result: QueryResult) -> str:
        from securebank.pipeline import format_result
        if not result.rows or len(result.rows) > MAX_LLM_ROWS:
            self.last_source = "template"
            return format_result(result)
        try:
            text = self.llm.generate(build_answer_messages(result), max_new_tokens=self.max_new_tokens)
        except Exception:  # the model crashed or ran out of memory: never break the app
            text = ""
        text = " ".join((text or "").split())[:MAX_ANSWER_CHARS]
        if not text:
            self.last_source = "template"
            return format_result(result)
        self.last_source = "llm"
        return text


def make_answer_writer(llm=None) -> AnswerWriter:
    if llm is None:
        from securebank.llm.model import get_llm
        llm = get_llm()
    return AnswerWriter(llm)
