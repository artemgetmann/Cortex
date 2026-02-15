from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tracks.cli_sqlite.lesson_promotion_v2 import LessonOutcome, apply_outcomes, compute_utility
from tracks.cli_sqlite.lesson_retrieval_v2 import retrieve_on_error, retrieve_pre_run
from tracks.cli_sqlite.lesson_store_v2 import (
    LessonRecord,
    archive_lessons,
    load_lesson_records,
    upsert_lesson_records,
)


def _record(
    *,
    session_id: int,
    rule_text: str,
    status: str = "candidate",
    fingerprints: tuple[str, ...] = ("fp_a",),
    tags: tuple[str, ...] = ("syntax_structure",),
    reliability: float = 0.5,
) -> LessonRecord:
    rec = LessonRecord.from_candidate(
        session_id=session_id,
        task_id="aggregate_report",
        task="aggregate report",
        domain="gridtool",
        rule_text=rule_text,
        trigger_fingerprints=fingerprints,
        tags=tags,
        status=status,
    )
    return LessonRecord(**{**rec.__dict__, "reliability": reliability})


class LessonStoreV2Tests(unittest.TestCase):
    def test_upsert_dedups_and_merges_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "lessons_v2.jsonl"
            first = _record(session_id=1001, rule_text="Use lowercase sum() not SUM().")
            second = _record(session_id=1002, rule_text="Use lowercase sum() not SUM().")
            result = upsert_lesson_records(path, [first, second])
            rows = load_lesson_records(path)
            self.assertEqual(result["inserted"], 1)
            self.assertEqual(result["merged"], 1)
            self.assertEqual(len(rows), 1)
            self.assertEqual(set(rows[0].source_session_ids), {1001, 1002})

    def test_conflict_links_when_same_trigger_has_opposed_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "lessons_v2.jsonl"
            keep = _record(session_id=1101, rule_text="TALLY requires quoted path.", fingerprints=("fp_load",))
            drop = _record(session_id=1102, rule_text="TALLY does not require quoted path.", fingerprints=("fp_load",))
            result = upsert_lesson_records(path, [keep, drop])
            rows = load_lesson_records(path)
            self.assertGreaterEqual(result["conflict_links"], 1)
            self.assertEqual(len(rows), 2)
            self.assertTrue(rows[0].conflict_lesson_ids or rows[1].conflict_lesson_ids)

    def test_archive_lessons_marks_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "lessons_v2.jsonl"
            row = _record(session_id=1201, rule_text='LOAD requires "quoted.csv".')
            upsert_lesson_records(path, [row])
            changed = archive_lessons(path, lesson_ids=[row.lesson_id], reason="stale")
            archived = load_lesson_records(path)[0]
            self.assertEqual(changed, 1)
            self.assertEqual(archived.status, "archived")
            self.assertEqual(archived.archived_reason, "stale")


class RetrievalV2Tests(unittest.TestCase):
    def test_on_error_prefers_fingerprint_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "lessons_v2.jsonl"
            exact = _record(
                session_id=1301,
                rule_text="Use arrow syntax for TALLY.",
                fingerprints=("fp_exact",),
                tags=("syntax_structure",),
                reliability=0.4,
            )
            generic = _record(
                session_id=1302,
                rule_text="Keep functions lowercase.",
                fingerprints=("fp_other",),
                tags=("function_case",),
                reliability=0.9,
            )
            upsert_lesson_records(path, [exact, generic])
            matches, _ = retrieve_on_error(
                path=path,
                error_text="TALLY expected arrow syntax",
                fingerprint="fp_exact",
                query_tags=("syntax_structure",),
                max_results=2,
            )
            self.assertTrue(matches)
            self.assertEqual(matches[0].lesson.lesson_id, exact.lesson_id)

    def test_retrieval_ignores_suppressed_and_conflict_loser(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "lessons_v2.jsonl"
            winner = _record(
                session_id=1401,
                rule_text='LOAD requires "quoted.csv".',
                fingerprints=("fp_load",),
                tags=("path_quote",),
                reliability=0.9,
            )
            loser = _record(
                session_id=1402,
                rule_text="LOAD does not require quoted csv path.",
                fingerprints=("fp_load",),
                tags=("path_quote",),
                reliability=0.2,
            )
            suppressed = _record(
                session_id=1403,
                rule_text="Ignore all syntax errors.",
                status="suppressed",
                fingerprints=("fp_load",),
                tags=("syntax_structure",),
                reliability=0.9,
            )
            upsert_lesson_records(path, [winner, loser, suppressed])
            matches, losers = retrieve_on_error(
                path=path,
                error_text="LOAD path must be quoted",
                fingerprint="fp_load",
                query_tags=("path_quote",),
                max_results=3,
            )
            ids = [match.lesson.lesson_id for match in matches]
            self.assertIn(winner.lesson_id, ids)
            self.assertNotIn(suppressed.lesson_id, ids)
            self.assertIn(loser.lesson_id, losers)

    def test_pre_run_caps_single_source_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "lessons_v2.jsonl"
            rows = [
                _record(session_id=1501, rule_text=f"Rule {idx} for same session", tags=("generic",))
                for idx in range(5)
            ]
            upsert_lesson_records(path, rows)
            matches, _ = retrieve_pre_run(
                path=path,
                task_id="aggregate_report",
                domain="gridtool",
                task_text="aggregate report",
                max_results=5,
            )
            # default guard: max 2 from one source session
            self.assertLessEqual(len(matches), 2)


class PromotionV2Tests(unittest.TestCase):
    def test_compute_utility_weights(self) -> None:
        a = compute_utility(error_reduction=0.5, step_efficiency_gain=0.2, referee_score_gain=None)
        b = compute_utility(error_reduction=0.5, step_efficiency_gain=0.2, referee_score_gain=0.4)
        self.assertAlmostEqual(a, 0.395)
        self.assertAlmostEqual(b, 0.39)

    def test_promote_after_three_positive_outcomes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "lessons_v2.jsonl"
            rec = _record(session_id=1601, rule_text="Use arrow syntax.")
            upsert_lesson_records(path, [rec])
            outcomes = [
                LessonOutcome(lesson_id=rec.lesson_id, error_reduction=0.4, step_efficiency_gain=0.2),
                LessonOutcome(lesson_id=rec.lesson_id, error_reduction=0.5, step_efficiency_gain=0.3),
                LessonOutcome(lesson_id=rec.lesson_id, error_reduction=0.6, step_efficiency_gain=0.3),
            ]
            result = apply_outcomes(path=path, outcomes=outcomes)
            promoted = load_lesson_records(path)[0]
            self.assertEqual(result["promoted"], 1)
            self.assertEqual(promoted.status, "promoted")

    def test_suppress_after_non_positive_outcomes_or_contradiction_loss(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "lessons_v2.jsonl"
            rec = _record(session_id=1701, rule_text="Always use uppercase functions.", status="promoted")
            upsert_lesson_records(path, [rec])
            negative = [
                LessonOutcome(lesson_id=rec.lesson_id, error_reduction=-0.2, step_efficiency_gain=0.0),
                LessonOutcome(lesson_id=rec.lesson_id, error_reduction=-0.1, step_efficiency_gain=-0.1),
                LessonOutcome(lesson_id=rec.lesson_id, error_reduction=0.0, step_efficiency_gain=0.0),
            ]
            apply_outcomes(path=path, outcomes=negative)
            suppressed = load_lesson_records(path)[0]
            self.assertEqual(suppressed.status, "suppressed")

            second = _record(session_id=1702, rule_text="Use lowercase functions.", status="candidate")
            upsert_lesson_records(path, [second])
            contradiction = [LessonOutcome(lesson_id=second.lesson_id, error_reduction=0.0, step_efficiency_gain=0.0, contradiction_lost=True)]
            apply_outcomes(path=path, outcomes=contradiction)
            rows = {row.lesson_id: row for row in load_lesson_records(path)}
            self.assertEqual(rows[second.lesson_id].status, "suppressed")


if __name__ == "__main__":
    unittest.main()
