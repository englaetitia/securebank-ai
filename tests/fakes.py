"""Fake LLMs for tests: no model download, instant, predictable."""
import json


class FakeLLM:
    """Returns prepared outputs in order (the last one repeats)."""

    def __init__(self, *outputs):
        self.outputs = [o if isinstance(o, str) else json.dumps(o) for o in outputs]
        self.calls = []

    def generate(self, messages, max_new_tokens=128):
        self.calls.append(messages)
        return self.outputs[min(len(self.calls) - 1, len(self.outputs) - 1)]


class RuleLLM:
    """Picks the output from the last user message with a function."""

    def __init__(self, rule):
        self.rule = rule

    def generate(self, messages, max_new_tokens=128):
        out = self.rule(messages[-1]["content"])
        return out if isinstance(out, str) else json.dumps(out)


class BagOfWordsEncoder:
    """Stand-in for the sentence embedding model: word-count vectors, normalized."""

    def __init__(self, dims: int = 512):
        self.dims = dims

    def encode(self, texts):
        import re
        import zlib

        import numpy as np
        vectors = np.zeros((len(texts), self.dims))
        for row, text in enumerate(texts):
            for word in re.findall(r"[a-z]+", text.lower()):
                vectors[row, zlib.crc32(word[:5].encode()) % self.dims] += 1  # stable hash
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors / np.where(norms == 0, 1, norms)
