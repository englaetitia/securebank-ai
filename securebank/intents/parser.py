"""Choose the question parser: llm, embedding, or hybrid (LLM first, embedding if it fails)."""
from securebank.intents.parser_llm import ParseOutcome


class HybridParser:
    def __init__(self, primary, fallback):
        self.primary = primary
        self.fallback = fallback

    def parse(self, question: str) -> ParseOutcome:
        outcome = self.primary.parse(question)
        if outcome.request is not None:
            return outcome
        backup = self.fallback.parse(question, source="embedding_fallback")
        backup.attempts += outcome.attempts
        backup.latency_ms += outcome.latency_ms
        backup.error = outcome.error
        return backup


def build_parser(kind: str = "hybrid"):
    from securebank.intents.parser_embed import EmbeddingParser
    if kind == "embedding":
        return EmbeddingParser()
    from securebank.intents.parser_llm import LLMParser
    from securebank.llm.model import get_llm
    llm_parser = LLMParser(get_llm())
    if kind == "llm":
        return llm_parser
    if kind == "hybrid":
        return HybridParser(llm_parser, EmbeddingParser())
    raise ValueError(f"Unknown parser kind: {kind}")
