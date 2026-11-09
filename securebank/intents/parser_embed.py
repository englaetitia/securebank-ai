"""Embedding classifier: the fallback (and baseline) question parser.

Each example question is turned into a vector with a multilingual sentence
embedding model (multilingual-e5-large, about 2 GB, runs on CPU; set
SECUREBANK_EMBEDDING_MODEL to use another one, and re-tune the threshold if
you do). A new question gets the intent of the most similar example
(cosine similarity), so French and Arabic work like English.
If nothing is similar enough, the question is out_of_scope; a score just below
the threshold becomes a "Did you mean...?" question instead of a refusal.
Parameters come from the rule-based extractor in slots.py.
Day 7: keyword rules (rules.py) can move a question to a refusal label.
"""
import os
import time

import numpy as np

from securebank.intents.examples import all_examples
from securebank.intents.lang import light_normalize
from securebank.intents.parser_llm import ParseOutcome
from securebank.intents.rules import forced_intent
from securebank.intents.schemas import ParsedRequest
from securebank.intents.slots import extract_params
from securebank.intents.typos import correct_typos

EMBEDDING_MODEL = os.environ.get("SECUREBANK_EMBEDDING_MODEL", "intfloat/multilingual-e5-large")
# Similarity scores depend on the model, so each encoder carries its own settings.
# E5 scores run high: tuned on the development questions (eval/dev_questions.csv and
# eval/multilingual_dev.csv), where accuracy is flat from 0.84 to 0.90 and falls after that.
E5_THRESHOLD, E5_MARGIN = 0.88, 0.03
DEFAULT_THRESHOLD = 0.45        # for encoders that do not set their own
BORDERLINE_MARGIN = 0.10        # scores this far below the threshold get a clarifying question
MAX_CANDIDATES = 2
REFUSAL_LABELS = ("restricted_request", "out_of_scope")


class SentenceEncoder:
    def __init__(self, model_name: str = EMBEDDING_MODEL):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model_name, device="cpu")
        is_e5 = "e5" in model_name
        self.prefix = "query: " if is_e5 else ""                  # E5 models expect this prefix
        self.threshold = E5_THRESHOLD if is_e5 else DEFAULT_THRESHOLD
        self.margin = E5_MARGIN if is_e5 else BORDERLINE_MARGIN

    def encode(self, texts: list[str]) -> np.ndarray:
        return self.model.encode([self.prefix + t for t in texts], normalize_embeddings=True)


class EmbeddingParser:
    def __init__(self, encoder=None, threshold: float | None = None, margin: float | None = None):
        self.encoder = encoder or SentenceEncoder()
        self.threshold = getattr(self.encoder, "threshold", DEFAULT_THRESHOLD) if threshold is None else threshold
        self.margin = getattr(self.encoder, "margin", BORDERLINE_MARGIN) if margin is None else margin
        pairs = all_examples()
        self.example_questions = [q for q, _ in pairs]
        self.example_intents = [i for _, i in pairs]
        self.example_vectors = self.encoder.encode([light_normalize(q) for q in self.example_questions])

    def ranked(self, question: str) -> list[tuple[str, float, str]]:
        """Best (intent, score, example) per intent, highest score first."""
        vector = self.encoder.encode([light_normalize(question)])[0]
        scores = self.example_vectors @ vector
        best = {}
        for index in np.argsort(scores)[::-1]:
            best.setdefault(self.example_intents[index], (float(scores[index]), self.example_questions[index]))
        return [(intent, score, example) for intent, (score, example) in best.items()]

    def nearest(self, question: str) -> tuple[str, float, str]:
        return self.ranked(question)[0]

    def parse(self, question: str, source: str = "embedding") -> ParseOutcome:
        started = time.perf_counter()
        question = correct_typos(question)[0]
        ranking = self.ranked(question)
        intent, score, example = ranking[0]
        candidates = []
        if score < self.threshold:
            if score >= self.threshold - self.margin and intent not in REFUSAL_LABELS:
                candidates = [i for i, s, _ in ranking[:MAX_CANDIDATES]
                              if i not in REFUSAL_LABELS and s >= self.threshold - self.margin]
            intent = "out_of_scope"
        forced = forced_intent(question)          # day 7: keyword safety rules
        if forced:
            candidates = []                       # a refusal is never turned into a question
            if forced != intent:
                intent, example = forced, f"rule:{forced} (was {example!r})"
        request = ParsedRequest(intent=intent, params=extract_params(question, intent))
        return ParseOutcome(request, source, 1, f"nearest: {example!r} (score {score:.2f})", None,
                            round((time.perf_counter() - started) * 1000), candidates)
