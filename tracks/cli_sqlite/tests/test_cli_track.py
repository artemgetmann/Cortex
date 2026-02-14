from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tracks.cli_sqlite.agent_cli import _is_skill_gate_satisfied
from tracks.cli_sqlite.eval_cli import evaluate_cli_session
from tracks.cli_sqlite.executor import prepare_task_workspace, run_sqlite
from tracks.cli_sqlite.learning_cli import (
    Lesson,
    _lesson_quality_score,
    filter_lessons,
    load_relevant_lessons,
    store_lessons,
)
from tracks.cli_sqlite.self_improve_cli import _scores_improving
from tracks.cli_sqlite.tool_aliases import build_alias_map, get_tool_api_name, get_tool_description
from tracks.cli_sqlite.memory_cli import ensure_session, write_event
from tracks.cli_sqlite.self_improve_cli import (
    SkillUpdate,
    auto_promote_queued_candidates,
    queue_skill_update_candidates,
    skill_digest,
)
from tracks.cli_sqlite.skill_routing_cli import build_skill_manifest, resolve_skill_content, route_manifest_entries


class ExecutorTests(unittest.TestCase):
    def test_executor_accepts_safe_sql(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "task.db"
            result = run_sqlite(
                db_path=db_path,
                sql=(
                    "CREATE TABLE t(x INTEGER);\n"
                    "INSERT INTO t(x) VALUES (1);\n"
                    "SELECT x FROM t;"
                ),
            )
            self.assertTrue(result.ok)
            self.assertIn("1", result.output)

    def test_executor_rejects_forbidden_patterns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "task.db"
            result = run_sqlite(db_path=db_path, sql=".shell ls")
            self.assertFalse(result.ok)
            assert result.error is not None
            self.assertIn("Forbidden sqlite dot-command", result.error)

    def test_executor_enforces_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "task.db"
            with mock.patch(
                "tracks.cli_sqlite.executor.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd=["sqlite3"], timeout=5.0),
            ):
                result = run_sqlite(db_path=db_path, sql="SELECT 1;")
            self.assertFalse(result.ok)
            assert result.error is not None
            self.assertIn("timed out", result.error)

    def test_prepare_task_workspace_loads_fixture_seed_with_dynamic_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_dir = root / "tasks" / "dynamic_fixture_case"
            task_dir.mkdir(parents=True, exist_ok=True)
            (task_dir / "bootstrap.sql").write_text("CREATE TABLE IF NOT EXISTS marker(id INTEGER);", encoding="utf-8")
            (task_dir / "fixture.csv").write_text(
                "event_id,category,amount,batch_id\n"
                "e1,drums,5,b1\n"
                "e2,bass,4,b1\n",
                encoding="utf-8",
            )
            db_path = root / "sessions" / "session-001" / "task.db"
            workspace = prepare_task_workspace(track_root=root, task_id="dynamic_fixture_case", db_path=db_path)
            self.assertIn("fixture.csv", workspace.fixture_paths)

            with sqlite3.connect(str(db_path)) as conn:
                rows = conn.execute(
                    "SELECT event_id, category, amount, batch_id FROM fixture_seed ORDER BY event_id;"
                ).fetchall()
            self.assertEqual(rows, [("e1", "drums", "5", "b1"), ("e2", "bass", "4", "b1")])


class SkillRoutingTests(unittest.TestCase):
    def test_manifest_build_route_and_read_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skills_root = Path(tmp) / "skills"
            basics = skills_root / "sqlite" / "basics" / "SKILL.md"
            agg = skills_root / "sqlite" / "import-aggregate" / "SKILL.md"
            basics.parent.mkdir(parents=True, exist_ok=True)
            agg.parent.mkdir(parents=True, exist_ok=True)
            basics.write_text(
                (
                    "---\n"
                    "name: sqlite-basics\n"
                    "description: Base sqlite workflow.\n"
                    "version: 1\n"
                    "---\n\n"
                    "# Basics\n"
                ),
                encoding="utf-8",
            )
            agg.write_text(
                (
                    "---\n"
                    "name: sqlite-import-aggregate\n"
                    "description: Import and aggregate rows.\n"
                    "version: 1\n"
                    "---\n\n"
                    "# Import Aggregate\n"
                ),
                encoding="utf-8",
            )

            manifest = build_skill_manifest(skills_root=skills_root, manifest_path=skills_root / "skills_manifest.json")
            routed = route_manifest_entries(task="sqlite import aggregate task", entries=manifest, top_k=1)
            self.assertEqual(len(routed), 1)
            self.assertEqual(routed[0].skill_ref, "sqlite/import-aggregate")
            content, err = resolve_skill_content(manifest, "sqlite/import-aggregate")
            self.assertIsNone(err)
            assert content is not None
            self.assertIn("Import Aggregate", content)


class EvalTests(unittest.TestCase):
    def _seed_sales(self, db_path: Path) -> None:
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute("CREATE TABLE sales(category TEXT NOT NULL, amount INTEGER NOT NULL)")
            conn.executemany(
                "INSERT INTO sales(category, amount) VALUES (?, ?)",
                [("drums", 5), ("bass", 4), ("lead", 3), ("drums", 8), ("bass", 5), ("lead", 5)],
            )
            conn.commit()

    def test_eval_cli_pass_case(self) -> None:
        track_tasks = Path(__file__).resolve().parents[1] / "tasks"
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "task.db"
            self._seed_sales(db_path)
            events = [
                {"tool": "run_sqlite", "tool_input": {"sql": "CREATE TABLE sales(category TEXT, amount INTEGER);"}, "ok": True},
                {"tool": "run_sqlite", "tool_input": {"sql": "INSERT INTO sales(category, amount) VALUES ('drums', 5);"}, "ok": True},
                {
                    "tool": "run_sqlite",
                    "tool_input": {
                        "sql": "SELECT category, SUM(amount) AS total FROM sales GROUP BY category ORDER BY category;"
                    },
                    "ok": True,
                },
            ]
            result = evaluate_cli_session(
                task="sqlite import aggregate grouped totals",
                task_id="import_aggregate",
                events=events,
                db_path=db_path,
                tasks_root=track_tasks,
            )
            self.assertTrue(result.applicable)
            self.assertTrue(result.passed)
            self.assertEqual(result.score, 1.0)

    def test_eval_cli_fail_case_reason_codes(self) -> None:
        track_tasks = Path(__file__).resolve().parents[1] / "tasks"
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "task.db"
            with sqlite3.connect(str(db_path)) as conn:
                conn.execute("CREATE TABLE sales(category TEXT NOT NULL, amount INTEGER NOT NULL)")
                conn.commit()
            events = [
                {"tool": "run_sqlite", "tool_input": {"sql": "SELECT * FROM sales;"}, "ok": True},
                {"tool": "run_sqlite", "tool_input": {"sql": "DROP TABLE sales;"}, "ok": False},
                {"tool": "run_sqlite", "tool_input": {"sql": "SELECT * FROM missing_table;"}, "ok": False},
            ]
            result = evaluate_cli_session(
                task="sqlite import aggregate grouped totals",
                task_id="import_aggregate",
                events=events,
                db_path=db_path,
                tasks_root=track_tasks,
            )
            self.assertFalse(result.passed)
            self.assertIn("missing_required_pattern", result.reasons)
            self.assertIn("matched_forbidden_pattern", result.reasons)
            self.assertIn("required_query_mismatch", result.reasons)
            self.assertIn("too_many_errors", result.reasons)

    def test_eval_incremental_reconcile_pass_case(self) -> None:
        track_tasks = Path(__file__).resolve().parents[1] / "tasks"
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "task.db"
            with sqlite3.connect(str(db_path)) as conn:
                conn.execute(
                    "CREATE TABLE ledger(event_id TEXT PRIMARY KEY, category TEXT, amount INTEGER, batch_id TEXT, checkpoint_tag TEXT)"
                )
                conn.execute("CREATE TABLE rejects(event_id TEXT, reason TEXT)")
                conn.execute("CREATE TABLE checkpoint_log(checkpoint_tag TEXT PRIMARY KEY, row_count INTEGER)")
                conn.executemany(
                    "INSERT INTO ledger(event_id, category, amount, batch_id, checkpoint_tag) VALUES (?, ?, ?, ?, ?)",
                    [
                        ("e1", "drums", 5, "b1", "CKP-APR-01"),
                        ("e2", "bass", 4, "b1", "CKP-APR-01"),
                        ("e3", "lead", 3, "b1", "CKP-APR-01"),
                        ("e4", "drums", 8, "b1", "CKP-APR-01"),
                    ],
                )
                conn.execute("INSERT INTO rejects(event_id, reason) VALUES ('e2', 'duplicate_event')")
                conn.execute("INSERT INTO checkpoint_log(checkpoint_tag, row_count) VALUES ('CKP-APR-01', 4)")
                conn.commit()

            events = [
                {
                    "tool": "run_sqlite",
                    "tool_input": {
                        "sql": "BEGIN TRANSACTION; INSERT INTO ledger VALUES ('e1','drums',5,'b1','CKP-APR-01'); COMMIT;"
                    },
                    "ok": True,
                },
                {"tool": "run_sqlite", "tool_input": {"sql": "INSERT INTO rejects(event_id, reason) VALUES ('e2', 'duplicate_event');"}, "ok": True},
                {"tool": "run_sqlite", "tool_input": {"sql": "INSERT INTO checkpoint_log(checkpoint_tag, row_count) VALUES ('CKP-APR-01',4);"}, "ok": True},
            ]
            result = evaluate_cli_session(
                task="sqlite incremental reconcile with dedupe",
                task_id="incremental_reconcile",
                events=events,
                db_path=db_path,
                tasks_root=track_tasks,
            )
            self.assertTrue(result.applicable)
            self.assertTrue(result.passed)
            self.assertEqual(result.score, 1.0)


class SkillGateTests(unittest.TestCase):
    def test_skill_gate_requires_intersection(self) -> None:
        self.assertTrue(_is_skill_gate_satisfied(read_skill_refs={"sqlite/basics"}, required_skill_refs=set()))
        self.assertFalse(_is_skill_gate_satisfied(read_skill_refs=set(), required_skill_refs={"sqlite/incremental-reconcile"}))
        self.assertTrue(
            _is_skill_gate_satisfied(
                read_skill_refs={"sqlite/incremental-reconcile"},
                required_skill_refs={"sqlite/incremental-reconcile"},
            )
        )


class LearningAndPromotionTests(unittest.TestCase):
    def test_learning_store_and_load_relevance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lessons.jsonl"
            lessons = [
                Lesson(
                    session_id=1,
                    task_id="import_aggregate",
                    task="sqlite import aggregate grouped totals",
                    category="mistake",
                    lesson="Always order grouped rows by category.",
                    evidence_steps=[2],
                    eval_passed=False,
                    eval_score=0.5,
                    skill_refs_used=["sqlite/import-aggregate"],
                    timestamp="2026-02-13T00:00:00+00:00",
                )
            ]
            count = store_lessons(path=path, lessons=lessons)
            self.assertEqual(count, 1)
            summary, loaded = load_relevant_lessons(
                path=path,
                task_id="import_aggregate",
                task="sqlite import aggregate grouped totals",
            )
            self.assertEqual(loaded, 1)
            self.assertIn("order grouped rows", summary)

    def test_promotion_gate_applies_only_when_trend_condition_met(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skills_root = root / "skills"
            sessions_root = root / "sessions"
            learning_root = root / "learning"
            queue_path = learning_root / "pending_skill_patches.json"
            promoted_path = learning_root / "promoted_skill_patches.json"
            manifest_path = skills_root / "skills_manifest.json"

            skill_path = skills_root / "sqlite" / "basics" / "SKILL.md"
            skill_path.parent.mkdir(parents=True, exist_ok=True)
            skill_path.write_text(
                (
                    "---\n"
                    "name: sqlite-basics\n"
                    "description: Base sqlite workflow.\n"
                    "version: 1\n"
                    "---\n\n"
                    "# SQLite Basics\n"
                    "- Keep SQL deterministic.\n"
                ),
                encoding="utf-8",
            )
            entries = build_skill_manifest(skills_root=skills_root, manifest_path=manifest_path)
            digest = skill_digest(skill_path.read_text(encoding="utf-8"))
            update = SkillUpdate(
                skill_ref="sqlite/basics",
                skill_digest=digest,
                root_cause="Missing explicit ORDER BY guidance caused unstable output.",
                evidence_steps=[3, 4],
                replace_rules=[],
                append_bullets=["Always use ORDER BY in final result queries."],
            )
            queue_result = queue_skill_update_candidates(
                queue_path=queue_path,
                updates=[update],
                confidence=0.9,
                session_id=20,
                task_id="import_aggregate",
                required_skill_digests={"sqlite/basics": digest},
                allowed_skill_refs={"sqlite/basics"},
            )
            self.assertEqual(queue_result["queued"], 1)

            for idx, score in enumerate([0.8, 0.7, 0.75], start=1):
                session_dir = sessions_root / f"session-{idx:03d}"
                session_dir.mkdir(parents=True, exist_ok=True)
                (session_dir / "metrics.json").write_text(
                    json.dumps(
                        {
                            "session_id": idx,
                            "task_id": "import_aggregate",
                            "eval_score": score,
                            "eval_passed": score >= 1.0,
                        }
                    ),
                    encoding="utf-8",
                )

            blocked = auto_promote_queued_candidates(
                entries=entries,
                queue_path=queue_path,
                promoted_path=promoted_path,
                sessions_root=sessions_root,
                task_id="import_aggregate",
                skills_root=skills_root,
                manifest_path=manifest_path,
                min_runs=3,
                min_delta=0.2,
            )
            self.assertEqual(blocked["applied"], 0)
            self.assertEqual(blocked["reason"], "score_not_improving")

            for idx, score in enumerate([0.4, 0.6, 0.8], start=1):
                session_dir = sessions_root / f"session-{idx:03d}"
                (session_dir / "metrics.json").write_text(
                    json.dumps(
                        {
                            "session_id": idx,
                            "task_id": "import_aggregate",
                            "eval_score": score,
                            "eval_passed": score >= 1.0,
                        }
                    ),
                    encoding="utf-8",
                )

            promoted = auto_promote_queued_candidates(
                entries=entries,
                queue_path=queue_path,
                promoted_path=promoted_path,
                sessions_root=sessions_root,
                task_id="import_aggregate",
                skills_root=skills_root,
                manifest_path=manifest_path,
                min_runs=3,
                min_delta=0.2,
            )
            self.assertEqual(promoted["applied"], 1)
            self.assertTrue(promoted_path.exists())
            updated_text = skill_path.read_text(encoding="utf-8")
            self.assertIn("Learned Updates", updated_text)


class SessionResetTests(unittest.TestCase):
    def test_reused_session_id_clears_prior_artifacts(self) -> None:
        cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                sessions_root = Path("sessions")
                first = ensure_session(8, sessions_root=sessions_root)
                write_event(first.events_path, {"step": 1, "tool": "run_sqlite", "ok": True})
                first.metrics_path.write_text('{"ok": true}', encoding="utf-8")
                first.db_path.write_text("stale-db", encoding="utf-8")

                second = ensure_session(8, sessions_root=sessions_root)
                self.assertFalse(second.events_path.exists())
                self.assertFalse(second.metrics_path.exists())
                self.assertFalse(second.db_path.exists())
            finally:
                os.chdir(cwd)


class IntegrationTraceTests(unittest.TestCase):
    def test_scripted_trace_evaluator_and_learning_hooks(self) -> None:
        track_tasks = Path(__file__).resolve().parents[1] / "tasks"
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "task.db"
            with sqlite3.connect(str(db_path)) as conn:
                conn.execute("CREATE TABLE sales(category TEXT NOT NULL, amount INTEGER NOT NULL)")
                conn.executemany(
                    "INSERT INTO sales(category, amount) VALUES (?, ?)",
                    [("drums", 5), ("bass", 4), ("lead", 3), ("drums", 8), ("bass", 5), ("lead", 5)],
                )
                conn.commit()
            scripted_events = [
                {"step": 1, "tool": "run_sqlite", "tool_input": {"sql": "CREATE TABLE sales(category TEXT, amount INTEGER);"}, "ok": True},
                {"step": 2, "tool": "run_sqlite", "tool_input": {"sql": "INSERT INTO sales(category, amount) VALUES ('drums',5);"}, "ok": True},
                {
                    "step": 3,
                    "tool": "run_sqlite",
                    "tool_input": {
                        "sql": "SELECT category, SUM(amount) AS total FROM sales GROUP BY category ORDER BY category;"
                    },
                    "ok": True,
                },
            ]
            eval_result = evaluate_cli_session(
                task="sqlite import aggregate grouped totals",
                task_id="import_aggregate",
                events=scripted_events,
                db_path=db_path,
                tasks_root=track_tasks,
            )
            self.assertTrue(eval_result.passed)


class EvalIdempotentRerunTests(unittest.TestCase):
    def test_eval_idempotent_rerun_pass(self) -> None:
        track_tasks = Path(__file__).resolve().parents[1] / "tasks"
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "task.db"
            with sqlite3.connect(str(db_path)) as conn:
                conn.execute("CREATE TABLE inventory(sku TEXT PRIMARY KEY, product TEXT NOT NULL, quantity INTEGER NOT NULL)")
                conn.executemany(
                    "INSERT INTO inventory(sku, product, quantity) VALUES (?, ?, ?)",
                    [("SKU-001", "Widget A", 10), ("SKU-002", "Widget B", 25), ("SKU-003", "Widget C", 15)],
                )
                conn.commit()
            events = [
                {
                    "tool": "run_sqlite",
                    "tool_input": {
                        "sql": "INSERT OR IGNORE INTO inventory(sku, product, quantity) VALUES ('SKU-001','Widget A',10);"
                    },
                    "ok": True,
                },
            ]
            result = evaluate_cli_session(
                task="sqlite idempotent rerun duplicate handling",
                task_id="idempotent_rerun",
                events=events,
                db_path=db_path,
                tasks_root=track_tasks,
            )
            self.assertTrue(result.applicable)
            self.assertTrue(result.passed)
            self.assertEqual(result.score, 1.0)

    def test_eval_idempotent_rerun_fail_double_count(self) -> None:
        track_tasks = Path(__file__).resolve().parents[1] / "tasks"
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "task.db"
            with sqlite3.connect(str(db_path)) as conn:
                # Simulate plain INSERT without dedup — use a non-PK table to allow dupes
                conn.execute("CREATE TABLE inventory(sku TEXT, product TEXT NOT NULL, quantity INTEGER NOT NULL)")
                conn.executemany(
                    "INSERT INTO inventory(sku, product, quantity) VALUES (?, ?, ?)",
                    [
                        ("SKU-001", "Widget A", 10),
                        ("SKU-002", "Widget B", 25),
                        ("SKU-003", "Widget C", 15),
                        ("SKU-001", "Widget A", 10),
                        ("SKU-002", "Widget B", 25),
                        ("SKU-003", "Widget C", 15),
                    ],
                )
                conn.commit()
            events = [
                {
                    "tool": "run_sqlite",
                    "tool_input": {"sql": "INSERT INTO inventory(sku, product, quantity) VALUES ('SKU-001','Widget A',10);"},
                    "ok": True,
                },
            ]
            result = evaluate_cli_session(
                task="sqlite idempotent rerun duplicate handling",
                task_id="idempotent_rerun",
                events=events,
                db_path=db_path,
                tasks_root=track_tasks,
            )
            self.assertFalse(result.passed)
            self.assertIn("required_query_mismatch", result.reasons)


class EvalPartialFailureRecoveryTests(unittest.TestCase):
    def test_eval_partial_failure_recovery_pass(self) -> None:
        track_tasks = Path(__file__).resolve().parents[1] / "tasks"
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "task.db"
            with sqlite3.connect(str(db_path)) as conn:
                conn.execute("CREATE TABLE transactions(txn_id TEXT PRIMARY KEY, account TEXT NOT NULL, amount INTEGER NOT NULL)")
                conn.execute("CREATE TABLE error_log(txn_id TEXT NOT NULL, reason TEXT NOT NULL)")
                conn.executemany(
                    "INSERT INTO transactions(txn_id, account, amount) VALUES (?, ?, ?)",
                    [("T001", "checking", 500), ("T002", "savings", 300), ("T004", "savings", 200), ("T006", "checking", 150)],
                )
                conn.executemany(
                    "INSERT INTO error_log(txn_id, reason) VALUES (?, ?)",
                    [("T003", "non_numeric_amount"), ("T005", "non_numeric_amount")],
                )
                conn.commit()
            events = [
                {
                    "tool": "run_sqlite",
                    "tool_input": {"sql": "INSERT INTO transactions(txn_id, account, amount) VALUES ('T001','checking',500);"},
                    "ok": True,
                },
                {
                    "tool": "run_sqlite",
                    "tool_input": {"sql": "INSERT INTO error_log(txn_id, reason) VALUES ('T003','non_numeric_amount');"},
                    "ok": True,
                },
            ]
            result = evaluate_cli_session(
                task="sqlite partial failure recovery error handling",
                task_id="partial_failure_recovery",
                events=events,
                db_path=db_path,
                tasks_root=track_tasks,
            )
            self.assertTrue(result.applicable)
            self.assertTrue(result.passed)
            self.assertEqual(result.score, 1.0)

    def test_eval_partial_failure_recovery_fail_missing_errors(self) -> None:
        track_tasks = Path(__file__).resolve().parents[1] / "tasks"
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "task.db"
            with sqlite3.connect(str(db_path)) as conn:
                conn.execute("CREATE TABLE transactions(txn_id TEXT PRIMARY KEY, account TEXT NOT NULL, amount INTEGER NOT NULL)")
                conn.execute("CREATE TABLE error_log(txn_id TEXT NOT NULL, reason TEXT NOT NULL)")
                conn.executemany(
                    "INSERT INTO transactions(txn_id, account, amount) VALUES (?, ?, ?)",
                    [("T001", "checking", 500), ("T002", "savings", 300), ("T004", "savings", 200), ("T006", "checking", 150)],
                )
                # No error_log entries
                conn.commit()
            events = [
                {
                    "tool": "run_sqlite",
                    "tool_input": {"sql": "INSERT INTO transactions(txn_id, account, amount) VALUES ('T001','checking',500);"},
                    "ok": True,
                },
            ]
            result = evaluate_cli_session(
                task="sqlite partial failure recovery error handling",
                task_id="partial_failure_recovery",
                events=events,
                db_path=db_path,
                tasks_root=track_tasks,
            )
            self.assertFalse(result.passed)
            self.assertIn("required_query_mismatch", result.reasons)


class LessonQualityTests(unittest.TestCase):
    def _make_lesson(self, text: str, steps: list[int] | None = None) -> Lesson:
        return Lesson(
            session_id=1,
            task_id="test_task",
            task="test task",
            category="mistake",
            lesson=text,
            evidence_steps=steps or [],
            eval_passed=False,
            eval_score=0.5,
            skill_refs_used=[],
            timestamp="2026-02-14T00:00:00+00:00",
        )

    def test_generic_lesson_scores_zero(self) -> None:
        for text in [
            "Always read the skill document before executing SQL",
            "Be careful with SQL operations",
            "Remember to check the fixture before inserting",
            "Don't forget to verify your output",
        ]:
            lesson = self._make_lesson(text)
            self.assertEqual(_lesson_quality_score(lesson), 0.0, f"Should reject: {text}")

    def test_specific_lesson_passes(self) -> None:
        lesson = self._make_lesson(
            "INSERT INTO ledger missed ON CONFLICT for event_id causing duplicate at step 4",
            steps=[4],
        )
        score = _lesson_quality_score(lesson)
        self.assertGreater(score, 0.15, f"Specific lesson should pass, got {score}")

    def test_filter_removes_generic(self) -> None:
        lessons = [
            self._make_lesson("Always read the skill before running SQL"),
            self._make_lesson("INSERT INTO ledger failed at step 3 due to missing PRIMARY KEY constraint", steps=[3]),
        ]
        filtered = filter_lessons(lessons, min_quality=0.15)
        self.assertEqual(len(filtered), 1)
        self.assertIn("PRIMARY KEY", filtered[0].lesson)


class LessonDedupTests(unittest.TestCase):
    def test_near_identical_lesson_blocked_on_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lessons.jsonl"
            base = Lesson(
                session_id=1,
                task_id="import_aggregate",
                task="test task",
                category="mistake",
                lesson="INSERT INTO ledger failed because ON CONFLICT clause was missing for event_id",
                evidence_steps=[3],
                eval_passed=False,
                eval_score=0.5,
                skill_refs_used=[],
                timestamp="2026-02-14T00:00:00+00:00",
            )
            count1 = store_lessons(path=path, lessons=[base])
            self.assertEqual(count1, 1)

            near_dup = Lesson(
                session_id=2,
                task_id="import_aggregate",
                task="test task",
                category="mistake",
                lesson="INSERT INTO ledger failed because the ON CONFLICT clause was missing for event_id column",
                evidence_steps=[3],
                eval_passed=False,
                eval_score=0.6,
                skill_refs_used=[],
                timestamp="2026-02-14T01:00:00+00:00",
            )
            count2 = store_lessons(path=path, lessons=[near_dup])
            self.assertEqual(count2, 0, "Near-duplicate lesson should be blocked")


class ToolAliasTests(unittest.TestCase):
    def test_standard_mode_returns_canonical_names(self) -> None:
        alias_map = build_alias_map(opaque=False)
        self.assertEqual(alias_map["run_sqlite"], "run_sqlite")
        self.assertEqual(alias_map["read_skill"], "read_skill")
        self.assertEqual(alias_map["show_fixture"], "show_fixture")

    def test_opaque_mode_returns_opaque_names(self) -> None:
        alias_map = build_alias_map(opaque=True)
        self.assertEqual(alias_map["dispatch"], "run_sqlite")
        self.assertEqual(alias_map["probe"], "read_skill")
        self.assertEqual(alias_map["catalog"], "show_fixture")
        self.assertNotIn("run_sqlite", alias_map)

    def test_get_tool_api_name(self) -> None:
        self.assertEqual(get_tool_api_name("run_sqlite", False), "run_sqlite")
        self.assertEqual(get_tool_api_name("run_sqlite", True), "dispatch")
        self.assertEqual(get_tool_api_name("read_skill", True), "probe")
        self.assertEqual(get_tool_api_name("show_fixture", True), "catalog")

    def test_get_tool_description_differs_by_mode(self) -> None:
        standard = get_tool_description("run_sqlite", False)
        opaque = get_tool_description("run_sqlite", True)
        self.assertIn("SQL", standard)
        self.assertNotIn("SQL", opaque)
        self.assertIn("workspace", opaque)

    def test_eval_works_with_canonical_events_from_opaque_run(self) -> None:
        """Events logged with canonical names should evaluate identically regardless of opaque mode."""
        track_tasks = Path(__file__).resolve().parents[1] / "tasks"
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "task.db"
            with sqlite3.connect(str(db_path)) as conn:
                conn.execute("CREATE TABLE sales(category TEXT NOT NULL, amount INTEGER NOT NULL)")
                conn.executemany(
                    "INSERT INTO sales(category, amount) VALUES (?, ?)",
                    [("drums", 5), ("bass", 4), ("lead", 3), ("drums", 8), ("bass", 5), ("lead", 5)],
                )
                conn.commit()
            # Events use canonical tool names (as the agent_cli always logs)
            events = [
                {"tool": "run_sqlite", "tool_input": {"sql": "CREATE TABLE sales(category TEXT, amount INTEGER);"}, "ok": True},
                {"tool": "run_sqlite", "tool_input": {"sql": "INSERT INTO sales(category, amount) VALUES ('drums', 5);"}, "ok": True},
                {
                    "tool": "run_sqlite",
                    "tool_input": {"sql": "SELECT category, SUM(amount) AS total FROM sales GROUP BY category ORDER BY category;"},
                    "ok": True,
                },
            ]
            result = evaluate_cli_session(
                task="sqlite import aggregate grouped totals",
                task_id="import_aggregate",
                events=events,
                db_path=db_path,
                tasks_root=track_tasks,
            )
            self.assertTrue(result.passed)
            self.assertEqual(result.score, 1.0)


class SofterPromotionTests(unittest.TestCase):
    def test_one_regression_still_promotes(self) -> None:
        rows = [
            {"score": 0.4},
            {"score": 0.6},
            {"score": 0.5},
            {"score": 0.8},
        ]
        self.assertTrue(
            _scores_improving(rows, min_runs=4, min_delta=0.2, max_regressions=1),
        )

    def test_two_regressions_blocks(self) -> None:
        rows = [
            {"score": 0.4},
            {"score": 0.6},
            {"score": 0.5},
            {"score": 0.4},
            {"score": 0.8},
        ]
        self.assertFalse(
            _scores_improving(rows, min_runs=5, min_delta=0.2, max_regressions=1),
        )

    def test_max_regressions_zero_matches_old_strict_behavior(self) -> None:
        monotonic = [{"score": 0.4}, {"score": 0.6}, {"score": 0.8}]
        self.assertTrue(
            _scores_improving(monotonic, min_runs=3, min_delta=0.2, max_regressions=0),
        )
        non_monotonic = [{"score": 0.4}, {"score": 0.6}, {"score": 0.5}]
        self.assertFalse(
            _scores_improving(non_monotonic, min_runs=3, min_delta=0.1, max_regressions=0),
        )


if __name__ == "__main__":
    unittest.main()
