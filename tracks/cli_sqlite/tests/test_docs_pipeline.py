from __future__ import annotations

from pathlib import Path

from tracks.cli_sqlite.docs_pipeline import build_documentation_bundle
from tracks.cli_sqlite.domain_adapter import DomainDoc


def test_docs_pipeline_builds_lossy_bundle_from_local_docs(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    local_doc = docs_dir / "sample.md"
    local_doc.write_text(
        (
            "SQLITE QUICK REFERENCE\n\n"
            "Use SELECT category, SUM(amount) FROM sales GROUP BY category ORDER BY category;\n"
            "Use INSERT INTO sales(category, amount) VALUES ('drums', 10);\n"
        ),
        encoding="utf-8",
    )
    domain_doc = docs_dir / "domain.md"
    domain_doc.write_text(
        "Domain docs: use explicit ORDER BY when deterministic output is required.",
        encoding="utf-8",
    )

    bundle = build_documentation_bundle(
        task_text="aggregate totals by category in sqlite",
        track_root=tmp_path,
        docs_manifest=[
            DomainDoc(
                doc_id="sqlite/reference",
                path=domain_doc,
                title="SQLite Domain Reference",
            )
        ],
        documentation=[str(local_doc)],
        mode="lossy",
        retrieval_mode="auto",
        budget_tokens=400,
        retriever_model=None,
        llm_client=None,
    )
    assert bundle.mode == "lossy"
    assert bundle.retrieval_mode == "auto"
    assert len(bundle.raw_docs) >= 2
    assert len(bundle.selected_chunks) >= 1
    assert "sqlite/reference" in {chunk.source_id for chunk in bundle.selected_chunks}
    assert bundle.brief
    assert bundle.brief_strategy in {"lossy_llm", "lossy_fallback"}
    assert bundle.load_errors == []


def test_docs_pipeline_none_mode_is_noop(tmp_path: Path) -> None:
    bundle = build_documentation_bundle(
        task_text="anything",
        track_root=tmp_path,
        docs_manifest=[],
        documentation=["https://example.com"],
        mode="none",
        retrieval_mode="off",
        budget_tokens=500,
        retriever_model=None,
        llm_client=None,
    )
    assert bundle.raw_docs == []
    assert bundle.selected_chunks == []
    assert bundle.brief == ""
    assert bundle.brief_strategy == "none"
    assert bundle.load_errors == []
