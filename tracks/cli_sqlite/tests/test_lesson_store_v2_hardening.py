from __future__ import annotations

import json
import multiprocessing as mp
import tempfile
import unittest
from pathlib import Path
from queue import Empty
from unittest import mock

from tracks.cli_sqlite.lesson_store_v2 import (
    LessonRecord,
    archive_lessons,
    load_lesson_records,
    migrate_legacy_lessons,
    upsert_lesson_records,
    write_lesson_records,
)


def _record(*, session_id: int, rule_text: str, fingerprint: str) -> LessonRecord:
    return LessonRecord.from_candidate(
        session_id=session_id,
        task_id="aggregate_report",
        task="aggregate report",
        domain="gridtool",
        rule_text=rule_text,
        trigger_fingerprints=(fingerprint,),
        tags=("syntax_structure",),
    )


def _upsert_worker(path_str: str, worker_id: int, iterations: int, start_event: object, queue: object) -> None:
    try:
        if not start_event.wait(timeout=10):
            queue.put(("error", f"worker {worker_id} start timeout"))
            return
        path = Path(path_str)
        for step in range(iterations):
            record = _record(
                session_id=5000 + (worker_id * 100) + step,
                rule_text=f"worker-{worker_id} rule-{step}: quote file paths.",
                fingerprint=f"fp_{worker_id}_{step}",
            )
            upsert_lesson_records(path, [record])
        queue.put(("ok", str(worker_id)))
    except Exception as exc:  # pragma: no cover - defensive test diagnostics
        queue.put(("error", f"{type(exc).__name__}: {exc}"))


def _archive_worker(path_str: str, lesson_ids: list[str], start_event: object, queue: object) -> None:
    try:
        if not start_event.wait(timeout=10):
            queue.put(("error", "archive start timeout"))
            return
        changed = archive_lessons(Path(path_str), lesson_ids=lesson_ids, reason="parallel-archive")
        queue.put(("ok", str(changed)))
    except Exception as exc:  # pragma: no cover - defensive test diagnostics
        queue.put(("error", f"{type(exc).__name__}: {exc}"))


def _migrate_worker(legacy_path_str: str, v2_path_str: str, start_event: object, queue: object) -> None:
    try:
        if not start_event.wait(timeout=10):
            queue.put(("error", "migrate start timeout"))
            return
        migrate_legacy_lessons(legacy_path=Path(legacy_path_str), v2_path=Path(v2_path_str))
        queue.put(("ok", legacy_path_str))
    except Exception as exc:  # pragma: no cover - defensive test diagnostics
        queue.put(("error", f"{type(exc).__name__}: {exc}"))


def _collect_queue_messages(queue: object, *, expected: int) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    for _ in range(expected):
        try:
            status, payload = queue.get(timeout=15)
        except Empty:
            break
        results.append((str(status), str(payload)))
    return results


class LessonStoreV2HardeningTests(unittest.TestCase):
    def _assert_processes_joined(self, processes: list[mp.Process]) -> None:
        for process in processes:
            process.join(timeout=20)
        alive = [process.pid for process in processes if process.is_alive()]
        self.assertFalse(alive, f"stuck processes: {alive}")
        for process in processes:
            self.assertEqual(process.exitcode, 0, f"worker exited with {process.exitcode}")

    def test_upsert_is_cross_process_safe(self) -> None:
        # This stresses read-modify-write collisions. Without locking, workers can
        # overwrite each other's progress and final row count drops below expected.
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "lessons_v2.jsonl"
            worker_count = 6
            iterations = 8
            expected_total = worker_count * iterations
            ctx = mp.get_context("spawn")
            start_event = ctx.Event()
            queue = ctx.Queue()
            processes = [
                ctx.Process(target=_upsert_worker, args=(str(path), worker_id, iterations, start_event, queue))
                for worker_id in range(worker_count)
            ]
            for process in processes:
                process.start()
            start_event.set()
            self._assert_processes_joined(processes)

            results = _collect_queue_messages(queue, expected=worker_count)
            self.assertEqual(len(results), worker_count)
            errors = [payload for status, payload in results if status != "ok"]
            self.assertFalse(errors, f"worker errors: {errors}")

            rows = load_lesson_records(path)
            self.assertEqual(len(rows), expected_total)

    def test_archive_is_cross_process_safe(self) -> None:
        # Each process archives a disjoint slice concurrently. Locking guarantees
        # the final snapshot includes every archive update.
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "lessons_v2.jsonl"
            seed_rows = [
                _record(
                    session_id=6100 + idx,
                    rule_text=f"seed-{idx}: quote file paths.",
                    fingerprint=f"seed_fp_{idx}",
                )
                for idx in range(24)
            ]
            upsert_lesson_records(path, seed_rows)
            lesson_ids = [record.lesson_id for record in load_lesson_records(path)]
            chunks = [lesson_ids[0:6], lesson_ids[6:12], lesson_ids[12:18], lesson_ids[18:24]]

            ctx = mp.get_context("spawn")
            start_event = ctx.Event()
            queue = ctx.Queue()
            processes = [
                ctx.Process(target=_archive_worker, args=(str(path), chunk, start_event, queue))
                for chunk in chunks
            ]
            for process in processes:
                process.start()
            start_event.set()
            self._assert_processes_joined(processes)

            results = _collect_queue_messages(queue, expected=len(chunks))
            self.assertEqual(len(results), len(chunks))
            errors = [payload for status, payload in results if status != "ok"]
            self.assertFalse(errors, f"worker errors: {errors}")

            rows = load_lesson_records(path)
            self.assertEqual(len(rows), len(seed_rows))
            self.assertTrue(all(row.status == "archived" for row in rows))
            self.assertTrue(all(row.archived_reason == "parallel-archive" for row in rows))

    def test_migrate_is_cross_process_safe(self) -> None:
        # Parallel migration jobs feed different legacy files into one V2 store.
        # Locking prevents last-writer-wins data loss across these merges.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            v2_path = root / "lessons_v2.jsonl"
            legacy_paths: list[Path] = []
            expected_lessons: set[str] = set()
            for batch in range(3):
                legacy_path = root / f"legacy_{batch}.jsonl"
                rows = []
                for idx in range(5):
                    lesson = f"legacy batch {batch} lesson {idx}"
                    expected_lessons.add(lesson)
                    rows.append(
                        {
                            "session_id": 7000 + (batch * 10) + idx,
                            "task_id": "aggregate_report",
                            "task": "aggregate report",
                            "domain": "gridtool",
                            "lesson": lesson,
                            "eval_score": 0.6,
                            "trigger_fingerprints": [f"legacy_fp_{batch}_{idx}"],
                        }
                    )
                legacy_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
                legacy_paths.append(legacy_path)

            ctx = mp.get_context("spawn")
            start_event = ctx.Event()
            queue = ctx.Queue()
            processes = [
                ctx.Process(target=_migrate_worker, args=(str(legacy_path), str(v2_path), start_event, queue))
                for legacy_path in legacy_paths
            ]
            for process in processes:
                process.start()
            start_event.set()
            self._assert_processes_joined(processes)

            results = _collect_queue_messages(queue, expected=len(legacy_paths))
            self.assertEqual(len(results), len(legacy_paths))
            errors = [payload for status, payload in results if status != "ok"]
            self.assertFalse(errors, f"worker errors: {errors}")

            rows = load_lesson_records(v2_path)
            self.assertEqual(len(rows), len(expected_lessons))
            self.assertEqual({row.rule_text for row in rows}, expected_lessons)

    def test_write_keeps_previous_file_if_replace_fails(self) -> None:
        # Atomic replace guarantees we either keep the old snapshot or install the
        # new snapshot; we should never leave a truncated in-place file behind.
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "lessons_v2.jsonl"
            original = _record(session_id=8001, rule_text="original snapshot", fingerprint="orig_fp")
            replacement = _record(session_id=8002, rule_text="replacement snapshot", fingerprint="new_fp")
            write_lesson_records(path, [original])
            before_bytes = path.read_bytes()

            with mock.patch("tracks.cli_sqlite.lesson_store_v2.os.replace", side_effect=OSError("replace failed")):
                with self.assertRaises(OSError):
                    write_lesson_records(path, [replacement])

            self.assertEqual(path.read_bytes(), before_bytes)
            rows = load_lesson_records(path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].rule_text, original.rule_text)
            self.assertEqual(list(path.parent.glob(f".{path.name}.tmp.*.jsonl")), [])

