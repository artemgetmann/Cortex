from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from tracks.cli_sqlite.domain_adapter import DomainDoc


def _tokenize(text: str) -> set[str]:
    # Keep retrieval scoring deterministic and cheap: lowercase alnum tokens only.
    normalized = "".join(ch.lower() if ch.isalnum() else " " for ch in text)
    return {tok for tok in normalized.split() if tok}


def _jaccard(a: str, b: str) -> float:
    ta = _tokenize(a)
    tb = _tokenize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / float(len(ta | tb))


@dataclass(frozen=True)
class RetrievedChunk:
    source_id: str
    source_path: str
    source_title: str
    text: str
    score: float


class KnowledgeProvider(Protocol):
    def retrieve(
        self,
        *,
        query: str,
        docs: list[DomainDoc],
        max_chunks: int = 4,
    ) -> list[RetrievedChunk]:
        ...


class LocalDocsKnowledgeProvider:
    """Simple local-doc retrieval for strict-mode critic context."""

    def __init__(self, *, chunk_chars: int = 900) -> None:
        self._chunk_chars = max(250, int(chunk_chars))

    def _read_chunks(self, path: Path) -> list[str]:
        # Chunk by paragraph-ish blocks so retrieved context preserves local syntax
        # patterns (examples + surrounding rules) without blowing token budget.
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            return []

        chunks: list[str] = []
        current: list[str] = []
        current_len = 0
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                if current:
                    chunk = "\n".join(current).strip()
                    if chunk:
                        chunks.append(chunk)
                    current = []
                    current_len = 0
                continue
            if current_len + len(stripped) > self._chunk_chars and current:
                chunk = "\n".join(current).strip()
                if chunk:
                    chunks.append(chunk)
                current = [stripped]
                current_len = len(stripped)
            else:
                current.append(stripped)
                current_len += len(stripped) + 1

        if current:
            chunk = "\n".join(current).strip()
            if chunk:
                chunks.append(chunk)
        return chunks

    def retrieve(
        self,
        *,
        query: str,
        docs: list[DomainDoc],
        max_chunks: int = 4,
    ) -> list[RetrievedChunk]:
        # Two-stage local ranking:
        # 1) lexical similarity via Jaccard(query, chunk)
        # 2) small tag bonus from adapter-provided doc tags
        # This keeps strict-mode retrieval domain-agnostic and reproducible.
        ranked: list[RetrievedChunk] = []
        q = (query or "").strip()
        if not q:
            return []

        for doc in docs:
            chunks = self._read_chunks(doc.path)
            if not chunks:
                continue
            tag_bonus = 0.0
            if doc.tags:
                tag_bonus = min(0.25, 0.05 * sum(1 for t in doc.tags if t.lower() in q.lower()))
            for chunk in chunks:
                score = _jaccard(q, chunk) + tag_bonus
                if score <= 0:
                    continue
                ranked.append(
                    RetrievedChunk(
                        source_id=doc.doc_id,
                        source_path=str(doc.path),
                        source_title=doc.title,
                        text=chunk,
                        score=score,
                    )
                )

        ranked.sort(key=lambda c: c.score, reverse=True)
        return ranked[: max(1, int(max_chunks))]
