"""Basic checks on the raw question before it reaches the LLM."""
import re

MAX_QUESTION_CHARS = 500


class InputRejected(ValueError):
    pass


def clean_question(question: str | None) -> str:
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", question or "")  # control characters
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        raise InputRejected("Please type a question.")
    if len(text) > MAX_QUESTION_CHARS:
        raise InputRejected(f"Please keep questions under {MAX_QUESTION_CHARS} characters.")
    return text
