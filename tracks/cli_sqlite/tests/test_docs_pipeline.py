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


def test_docs_pipeline_lossy_auto_filters_nonmatching_tagged_domain_docs(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    git_doc = docs_dir / "shell-git-reference.md"
    git_doc.write_text(
        "Use git format-patch and git am for transfer workflows.",
        encoding="utf-8",
    )
    xlsx_doc = docs_dir / "shell-xlsx-reference.md"
    xlsx_doc.write_text(
        "Use openpyxl to edit workbook cells and save reports.",
        encoding="utf-8",
    )

    bundle = build_documentation_bundle(
        task_text="Create a git hotfix patch and apply it cleanly to target repository",
        track_root=tmp_path,
        docs_manifest=[
            DomainDoc(
                doc_id="shell/git-reference",
                path=git_doc,
                title="Shell Git Reference",
                tags=("shell", "git", "patch"),
            ),
            DomainDoc(
                doc_id="shell/xlsx-reference",
                path=xlsx_doc,
                title="Shell XLSX Reference",
                tags=("shell", "xlsx", "openpyxl"),
            ),
        ],
        documentation=[],
        mode="lossy",
        retrieval_mode="auto",
        budget_tokens=400,
        retriever_model=None,
        llm_client=None,
    )
    selected_ids = {chunk.source_id for chunk in bundle.selected_chunks}
    assert "shell/git-reference" in selected_ids
    assert "shell/xlsx-reference" not in selected_ids


def test_docs_pipeline_lossy_off_filters_nonmatching_tagged_domain_docs(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    sqlite_doc = docs_dir / "sqlite-reference.md"
    sqlite_doc.write_text(
        "Use ORDER BY for deterministic output and verify row counts.",
        encoding="utf-8",
    )
    git_doc = docs_dir / "shell-git-reference.md"
    git_doc.write_text(
        "Use git status before and after applying patches.",
        encoding="utf-8",
    )

    bundle = build_documentation_bundle(
        task_text="Reconcile sqlite totals incrementally and verify grouped sums",
        track_root=tmp_path,
        docs_manifest=[
            DomainDoc(
                doc_id="sqlite/reference",
                path=sqlite_doc,
                title="SQLite Reference",
                tags=("sqlite", "sql", "query"),
            ),
            DomainDoc(
                doc_id="shell/git-reference",
                path=git_doc,
                title="Shell Git Reference",
                tags=("shell", "git", "patch"),
            ),
        ],
        documentation=[],
        mode="lossy",
        retrieval_mode="off",
        budget_tokens=400,
        retriever_model=None,
        llm_client=None,
    )
    selected_ids = {chunk.source_id for chunk in bundle.selected_chunks}
    assert "sqlite/reference" in selected_ids
    assert "shell/git-reference" not in selected_ids
