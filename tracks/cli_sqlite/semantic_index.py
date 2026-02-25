from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Mapping, Sequence


_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STEM_SUFFIXES = ("ing", "ed", "es", "s")

# Lightweight normalization map so semantically-close wording
# (quote/quoted/quotes, file path/filename, load/import) can match.
_CANONICAL_TOKEN_MAP: dict[str, str] = {
    "quotes": "quote",
    "quoted": "quote",
    "quoting": "quote",
    "doublequoted": "quote",
    "filepath": "path",
    "filepaths": "path",
    "filename": "path",
    "filenames": "path",
    "must": "require",
    "needs": "require",
    "needed": "require",
    "requires": "require",
    "required": "require",
    "loading": "import",
    "loaded": "import",
    "loads": "import",
    "load": "import",
    "errors": "error",
    "failed": "error",
    "failure": "error",
    "failing": "error",
}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _stem(token: str) -> str:
    lowered = str(token).strip().lower()
    if not lowered:
        return ""
    for suffix in _STEM_SUFFIXES:
        if len(lowered) > 4 and lowered.endswith(suffix):
            lowered = lowered[: -len(suffix)]
            break
    return lowered


def _canonicalize(token: str) -> str:
    base = _stem(token)
    return _CANONICAL_TOKEN_MAP.get(base, base)


def _tokenize(text: str) -> list[str]:
    normalized: list[str] = []
    for token in _TOKEN_RE.findall(str(text).lower()):
        canonical = _canonicalize(token)
        if canonical:
            normalized.append(canonical)
    return normalized


def _token_counts(tokens: Sequence[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    return counts


def _char_ngrams(text: str, n: int = 3) -> set[str]:
    compact = "".join(ch for ch in str(text).lower() if ch.isalnum())
    if not compact:
        return set()
    if len(compact) <= n:
        return {compact}
    return {compact[idx : idx + n] for idx in range(0, len(compact) - n + 1)}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / float(len(a | b))


@dataclass(frozen=True)
class SemanticIndex:
    """
    Deterministic local semantic scorer.

    This intentionally avoids heavy ML dependencies and model downloads.
    Signal comes from canonicalized token overlap + query coverage +
    character n-gram similarity for small paraphrase tolerance.
    """

    idf: Mapping[str, float]
    unknown_idf: float

    @classmethod
    def from_texts(cls, texts: Sequence[str]) -> "SemanticIndex":
        doc_count = max(1, len(texts))
        df: dict[str, int] = {}
        for text in texts:
            for token in set(_tokenize(text)):
                df[token] = df.get(token, 0) + 1
        idf = {
            token: 1.0 + math.log((1.0 + float(doc_count)) / (1.0 + float(freq)))
            for token, freq in df.items()
        }
        unknown_idf = 1.0 + math.log(1.0 + float(doc_count))
        return cls(idf=idf, unknown_idf=unknown_idf)

    def similarity(self, query_text: str, candidate_text: str) -> float:
        query_tokens = _tokenize(query_text)
        candidate_tokens = _tokenize(candidate_text)
        if not query_tokens or not candidate_tokens:
            return 0.0

        query_counts = _token_counts(query_tokens)
        candidate_counts = _token_counts(candidate_tokens)
        all_tokens = set(query_counts) | set(candidate_counts)

        intersection_mass = 0.0
        union_mass = 0.0
        query_mass = 0.0
        for token in all_tokens:
            weight = float(self.idf.get(token, self.unknown_idf))
            q_count = float(query_counts.get(token, 0))
            c_count = float(candidate_counts.get(token, 0))
            intersection_mass += min(q_count, c_count) * weight
            union_mass += max(q_count, c_count) * weight
            query_mass += q_count * weight

        token_overlap = (intersection_mass / union_mass) if union_mass > 0.0 else 0.0
        query_coverage = (intersection_mass / query_mass) if query_mass > 0.0 else 0.0

        ngram_overlap = _jaccard(
            _char_ngrams(" ".join(query_tokens)),
            _char_ngrams(" ".join(candidate_tokens)),
        )

        score = (0.55 * token_overlap) + (0.30 * query_coverage) + (0.15 * ngram_overlap)
        return _clamp(score, 0.0, 1.0)


def semantic_similarity(query_text: str, candidate_text: str, *, corpus: Sequence[str] = ()) -> float:
    corpus_rows = list(corpus) if corpus else [query_text, candidate_text]
    index = SemanticIndex.from_texts(corpus_rows)
    return index.similarity(query_text, candidate_text)


__all__ = ["SemanticIndex", "semantic_similarity"]
