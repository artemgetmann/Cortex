from __future__ import annotations

import json
import unittest

from tracks.cli_sqlite.error_capture import (
    ErrorEvent,
    build_error_fingerprint,
    event_to_json,
    extract_tags,
)


class FingerprintTests(unittest.TestCase):
    def test_fingerprint_stable_when_only_volatile_values_change(self) -> None:
        # Same failure semantics with different ids, paths, and counters must
        # collapse to one fingerprint for reliable cross-session aggregation.
        error_a = "UNIQUE constraint failed: ledger.event_id='evt-1001' at /tmp/run-123/task.db line 77"
        error_b = "UNIQUE constraint failed: ledger.event_id='evt-9009' at /tmp/run-999/task.db line 2"
        state_a = {"session": "session-001", "step": 7, "cwd": "/tmp/run-123"}
        state_b = {"session": "session-002", "step": 8, "cwd": "/tmp/run-999"}
        action_a = "run_sqlite --db /tmp/run-123/task.db \"INSERT INTO ledger VALUES ('evt-1001')\""
        action_b = "run_sqlite --db /tmp/run-999/task.db \"INSERT INTO ledger VALUES ('evt-9009')\""

        fp_a = build_error_fingerprint(error=error_a, state=state_a, action=action_a)
        fp_b = build_error_fingerprint(error=error_b, state=state_b, action=action_b)

        self.assertEqual(fp_a, fp_b)

    def test_fingerprint_changes_for_materially_different_errors(self) -> None:
        constraint_error = "UNIQUE constraint failed: ledger.event_id"
        timeout_error = "Request timed out after 30 seconds while calling https://api.example.com/jobs"

        fp_constraint = build_error_fingerprint(error=constraint_error, state="", action="run_sqlite INSERT")
        fp_timeout = build_error_fingerprint(error=timeout_error, state="", action="POST /jobs")

        self.assertNotEqual(fp_constraint, fp_timeout)


class TagExtractionTests(unittest.TestCase):
    def test_extract_tags_cli_failure(self) -> None:
        tags = extract_tags(
            error="gridtool: unknown command 'talley'. Usage: gridtool <command> [flags]. Exit code 127",
            action="run_gridtool --input fixture.csv",
            state="stderr: command not found",
        )

        self.assertIn("surface_cli", tags)
        self.assertIn("syntax_error", tags)
        self.assertIn("command_not_found", tags)
        self.assertIn("nonzero_exit", tags)

    def test_extract_tags_non_cli_failure(self) -> None:
        tags = extract_tags(
            error="HTTP 429 Too Many Requests: rate limit exceeded. Retry after 20 seconds.",
            state="Request to https://api.example.com/v1/jobs timed out after 30s due to connection reset.",
            action="POST /v1/jobs",
        )

        self.assertIn("surface_http", tags)
        self.assertIn("rate_limited", tags)
        self.assertIn("timeout", tags)
        self.assertIn("network", tags)
        self.assertIn("retryable", tags)


class SerializationTests(unittest.TestCase):
    def test_error_event_serialization_is_ascii_json(self) -> None:
        event = ErrorEvent(
            channel="hard_failure",
            error="UNIQUE constraint failed: ledger.event_id",
            action="run_sqlite INSERT INTO ledger VALUES ('evt-1')",
            state={"step": 1, "session": "session-001"},
            metadata={"origin": "unit_test"},
        )
        payload = event_to_json(event)
        parsed = json.loads(payload)

        self.assertEqual(parsed["channel"], "hard_failure")
        self.assertEqual(parsed["metadata"]["origin"], "unit_test")
        self.assertTrue(payload.isascii())
        self.assertTrue(str(parsed["fingerprint"]).startswith("ef_"))


if __name__ == "__main__":
    unittest.main()
