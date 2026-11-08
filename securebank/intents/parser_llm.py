"""Question -> ParsedRequest, using the local LLM.

The LLM's raw text is never trusted: it must be one JSON object that passes
the ParsedRequest schema. If not, the model gets one more try with the error
message; after that the parser gives up (day 6 adds the embedding fallback).
"""
import json
import re
import time
from dataclasses import dataclass

from pydantic import ValidationError

from securebank.intents.schemas import ParsedRequest
from securebank.llm.prompts import build_parser_messages


@dataclass
class ParseOutcome:
    request: ParsedRequest | None   # None = could not parse
    source: str                     # "llm", "embedding", "embedding_fallback"
    attempts: int = 1
    raw: str = ""                   # the model's raw output (for debugging and the report)
    error: str | None = None
    latency_ms: int = 0


def extract_json(raw: str) -> dict:
    """Find the JSON object in the model output (it sometimes adds ``` fences or text)."""
    text = re.sub(r"```(?:json)?", "", raw).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found")
    return json.loads(text[start:end + 1])


def _short_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "; ".join(f"{'.'.join(map(str, e['loc'])) or 'output'}: {e['msg']}" for e in exc.errors())[:300]
    return str(exc)[:300]


class LLMParser:
    def __init__(self, llm, max_attempts: int = 2, max_new_tokens: int = 80):
        self.llm = llm
        self.max_attempts = max_attempts
        self.max_new_tokens = max_new_tokens

    def parse(self, question: str) -> ParseOutcome:
        started = time.perf_counter()
        messages = build_parser_messages(question)
        raw, error = "", None
        for attempt in range(1, self.max_attempts + 1):
            raw = self.llm.generate(messages, max_new_tokens=self.max_new_tokens)
            try:
                request = ParsedRequest.model_validate(extract_json(raw))
                return ParseOutcome(request, "llm", attempt, raw, None,
                                    round((time.perf_counter() - started) * 1000))
            except (ValueError, ValidationError) as exc:
                error = _short_error(exc)
                messages = messages + [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": f"That output was invalid ({error}). "
                                                "Reply with only the corrected JSON object."},
                ]
        return ParseOutcome(None, "llm", self.max_attempts, raw, error,
                            round((time.perf_counter() - started) * 1000))
