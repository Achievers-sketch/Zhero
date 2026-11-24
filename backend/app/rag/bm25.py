"""Baseline lexical retrieval (BM25) with part-number-aware tokenisation.

This is the baseline for Stage 5 (RETRIEVE). Dense/vector retrieval can be added behind
the same interface once embeddings are chosen; keyword search stays useful for exact part
numbers and terminology (blueprint Stage 5).
"""

import math
import re
from collections import Counter

_TOKEN = re.compile(r"[^\W_]+(?:[-_/.][^\W_]+)*")
_SPLIT = re.compile(r"[-_/.]")
_STOPWORDS = frozenset(
    "a an and are as at be by for from how i in is it its of on or that the this to was "
    "what when where which why with does do can should".split()
)


def tokenize(text: str) -> list[str]:
    """Lowercase tokens; compound terms like ``1234-56`` also yield their parts."""
    tokens: list[str] = []
    for match in _TOKEN.finditer(text.casefold()):
        token = match.group()
        parts = _SPLIT.split(token)
        if len(parts) > 1:
            tokens.append(token)
            tokens.extend(p for p in parts if p and p not in _STOPWORDS)
        elif token not in _STOPWORDS:
            tokens.append(token)
    return tokens


class BM25Index:
    def __init__(self, documents: list[list[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.term_freqs = [Counter(doc) for doc in documents]
        self.lengths = [len(doc) for doc in documents]
        self.avg_length = (sum(self.lengths) / len(self.lengths)) if documents else 0.0
        doc_freq: Counter[str] = Counter()
        for freqs in self.term_freqs:
            doc_freq.update(freqs.keys())
        n = len(documents)
        self.idf = {t: math.log(1 + (n - df + 0.5) / (df + 0.5)) for t, df in doc_freq.items()}

    def score(self, query_tokens: list[str]) -> list[float]:
        scores = [0.0] * len(self.term_freqs)
        for term in set(query_tokens):
            idf = self.idf.get(term)
            if idf is None:
                continue
            for i, freqs in enumerate(self.term_freqs):
                tf = freqs.get(term, 0)
                if tf:
                    norm = 1 - self.b + self.b * (self.lengths[i] / (self.avg_length or 1.0))
                    scores[i] += idf * tf * (self.k1 + 1) / (tf + self.k1 * norm)
        return scores


def make_excerpt(text: str, query_tokens: list[str], max_chars: int = 300) -> str:
    """Return the line/sentence of ``text`` that best matches the query, trimmed."""
    segments = [s.strip() for s in re.split(r"\n+|(?<=[.!?])\s+", text) if s.strip()]
    wanted = set(query_tokens)
    best = max(segments, key=lambda s: len(wanted & set(tokenize(s))), default=text.strip())
    if len(wanted & set(tokenize(best))) == 0:
        best = text.strip()
    return best if len(best) <= max_chars else best[: max_chars - 1].rstrip() + "…"
