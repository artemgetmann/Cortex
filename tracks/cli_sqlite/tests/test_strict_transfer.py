from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from tracks.cli_sqlite.domain_adapter import DomainDoc
from tracks.cli_sqlite.domains.fluxtool_adapter import FluxtoolAdapter
from tracks.cli_sqlite.domains.gridtool_adapter import GridtoolAdapter
from tracks.cli_sqlite.domains.sqlite_adapter import SqliteAdapter
from tracks.cli_sqlite.knowledge_provider import LocalDocsKnowledgeProvider
from tracks.cli_sqlite.learning_cli import Lesson, find_lessons_for_error


def _lesson(text: str, *, category: str = "mistake") -> Lesson:
    return Lesson(
        session_id=1,
        task_id="aggregate_report",
        task="aggregate report",
        category=category,
        lesson=text,
        evidence_steps=[1],
        eval_passed=False,
        eval_score=0.0,
        skill_refs_used=[],
        timestamp="2026-02-15T00:00:00+00:00",
    )


def test_strict_hint_matching_is_semantic_and_capped() -> None:
    lessons = [
        _lesson('IMPORT requires a quoted path: IMPORT "file.csv".'),
        _lesson("GROUP needs => syntax: GROUP key => total=sum(amount)."),
        _lesson("Use lowercase functions: sum, count, avg."),
        _lesson("DISPLAY 5 limits output to five rows."),
    ]
    hints = find_lessons_for_error(
        "ERROR at line 1: IMPORT path must be quoted.",
        lessons,
        learning_mode="strict",
    )
    assert 1 <= len(hints) <= 2
    assert any("quoted" in h.lower() for h in hints)


def test_legacy_hint_matching_keeps_command_pattern_path() -> None:
    lessons = [
        _lesson("TALLY uses arrow syntax: TALLY key -> total=sum(amount)."),
        _lesson('LOAD requires quotes: LOAD "file.csv".'),
    ]
    hints = find_lessons_for_error(
        "ERROR at line 2: TALLY: expected arrow operator '->'.",
        lessons,
        learning_mode="legacy",
    )
    assert hints
    assert "TALLY" in hints[0]


def test_local_docs_provider_retrieves_relevant_chunks() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        a = root / "a.md"
        b = root / "b.md"
        a.write_text("GROUP syntax uses => and lowercase sum/count functions.", encoding="utf-8")
        b.write_text("SQLite uses SELECT and GROUP BY statements.", encoding="utf-8")
        docs = [
            DomainDoc(doc_id="fluxtool/ref", path=a, title="Fluxtool", tags=("group", "syntax")),
            DomainDoc(doc_id="sqlite/ref", path=b, title="SQLite", tags=("sql",)),
        ]
        provider = LocalDocsKnowledgeProvider(chunk_chars=200)
        chunks = provider.retrieve(query="GROUP => sum count syntax", docs=docs, max_chunks=2)
        assert chunks
        assert chunks[0].source_id == "fluxtool/ref"


def test_domain_docs_manifest_exposed() -> None:
    assert SqliteAdapter().docs_manifest()
    assert GridtoolAdapter().docs_manifest()
    assert FluxtoolAdapter().docs_manifest()


def test_fluxtool_translates_and_executes_commands() -> None:
    fluxtool_path = Path(__file__).resolve().parents[1] / "domains" / "fluxtool.py"
    fixture_dir = Path(__file__).resolve().parents[1] / "tasks" / "aggregate_report_holdout"

    cmd = ["python3", str(fluxtool_path), "--workdir", str(fixture_dir)]
    script = '\n'.join(
        [
            'IMPORT "fixture.csv"',
            "GROUP region => total=sum(amount), cnt=count(amount)",
            "SORT total down",
            "DISPLAY",
        ]
    )
    ok = subprocess.run(cmd, input=script, capture_output=True, text=True, timeout=5)
    assert ok.returncode == 0, ok.stderr
    assert "region,total,cnt" in ok.stdout

    bad = subprocess.run(cmd, input="IMPORT fixture.csv", capture_output=True, text=True, timeout=5)
    assert bad.returncode != 0
    assert "IMPORT" in bad.stderr
