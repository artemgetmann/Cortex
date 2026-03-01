from __future__ import annotations

from dataclasses import dataclass

from tracks.cli_sqlite.agent_cli import _serialize_prerun_v2_matches


@dataclass(frozen=True)
class _FakeLesson:
    lesson_id: str
    status: str
    task_id: str
    domain: str
    rule_text: str
    reason_code: str
    gap_type: str
    gap_signature: str


@dataclass(frozen=True)
class _FakeScore:
    score: float


@dataclass(frozen=True)
class _FakeMatch:
    lesson: _FakeLesson
    score: _FakeScore
    lane: str


def test_serialize_prerun_v2_matches_returns_structured_objects() -> None:
    rows = _serialize_prerun_v2_matches(
        [
            _FakeMatch(
                lesson=_FakeLesson(
                    lesson_id="lsn_123",
                    status="promoted",
                    task_id="incremental_reconcile",
                    domain="sqlite",
                    rule_text="Use upsert",
                    reason_code="required_query_mismatch",
                    gap_type="required_query",
                    gap_signature="required_query_mismatch|required_query|reject_count",
                ),
                score=_FakeScore(score=0.91),
                lane="strict",
            )
        ]
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["lesson_id"] == "lsn_123"
    assert row["status"] == "promoted"
    assert row["task_id"] == "incremental_reconcile"
    assert row["domain"] == "sqlite"
    assert row["score"] == 0.91
    assert row["lane"] == "strict"
