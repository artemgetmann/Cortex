from __future__ import annotations

from tracks.cli_sqlite.semantic_index import SemanticIndex, semantic_similarity


def test_similarity_is_deterministic_for_same_inputs() -> None:
    corpus = [
        "LOAD requires double-quoted filename before execution.",
        "If path errors happen, rerun command with clean flags.",
    ]
    index = SemanticIndex.from_texts(corpus)
    query = "ERROR: IMPORT path must be in quotes"
    candidate = "LOAD requires double-quoted filename before execution."
    first = index.similarity(query, candidate)
    second = index.similarity(query, candidate)
    assert first == second
    assert 0.0 <= first <= 1.0


def test_similarity_prefers_paraphrase_over_unrelated_text() -> None:
    query = "ERROR: IMPORT path must be in quotes"
    paraphrase = "LOAD requires double-quoted filename before execution."
    unrelated = "Use ORDER BY for stable output rows."
    corpus = [paraphrase, unrelated]
    assert semantic_similarity(query, paraphrase, corpus=corpus) > semantic_similarity(
        query,
        unrelated,
        corpus=corpus,
    )
