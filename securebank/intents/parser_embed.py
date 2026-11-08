"""Embedding classifier: the fallback (and baseline) question parser.

Each example question is turned into a vector with a small sentence
embedding model (all-MiniLM-L6-v2, about 90 MB, runs fine on CPU). A new
question gets the intent of the most similar example (cosine similarity).
If nothing is similar enough, the question is out_of_scope.
Parameters come from the rule-based extractor in slots.py.
Day 7: keyword rules (rules.py) can move a question to a refusal label.
"""
import time

import numpy as np

from securebank.intents.examples import all_examples
from securebank.intents.parser_llm import ParseOutcome
from securebank.intents.rules import forced_intent
from securebank.intents.schemas import ParsedRequest
from securebank.intents.slots import extract_params

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class SentenceEncoder:
    def __init__(self, model_name: str = EMBEDDING_MODEL):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model_name, device="cpu")

    def encode(self, texts: list[str]) -> np.ndarray:
        return self.model.encode(texts, normalize_embeddings=True)


class EmbeddingParser:
    def __init__(self, encoder=None, threshold: float = 0.45):
        self.encoder = encoder or SentenceEncoder()
        self.threshold = threshold
        pairs = all_examples()
        self.example_questions = [q for q, _ in pairs]
        self.example_intents = [i for _, i in pairs]
        self.example_vectors = self.encoder.encode(self.example_questions)

    def nearest(self, question: str) -> tuple[str, float, str]:
        vector = self.encoder.encode([question])[0]
        scores = self.example_vectors @ vector
        best = int(np.argmax(scores))
        return self.example_intents[best], float(scores[best]), self.example_questions[best]

    def parse(self, question: str, source: str = "embedding") -> ParseOutcome:
        started = time.perf_counter()
        intent, score, example = self.nearest(question)
        if score < self.threshold:
            intent = "out_of_scope"
        forced = forced_intent(question)          # day 7: keyword safety rules
        if forced and forced != intent:
            intent, example = forced, f"rule:{forced} (was {example!r})"
        request = ParsedRequest(intent=intent, params=extract_params(question, intent))
        return ParseOutcome(request, source, 1, f"nearest: {example!r} (score {score:.2f})", None,
                            round((time.perf_counter() - started) * 1000))
