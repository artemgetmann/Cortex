from __future__ import annotations

import json
import sys

from tracks.cli_sqlite.scripts import run_cross_domain


def test_cross_domain_runner_emits_json_payload_shape(monkeypatch, capsys) -> None:
    monkeypatch.setattr(run_cross_domain, "load_config", lambda: object())
    monkeypatch.setattr(run_cross_domain, "_clear_escalation", lambda: None)
    monkeypatch.setattr(run_cross_domain, "_clear_lessons", lambda: None)

    def _fake_run_phase(**kwargs):
        phase = kwargs["phase"]
        start_session = int(kwargs["start_session"])
        n_sessions = int(kwargs["n_sessions"])
        domain = str(kwargs["domain"])
        task_id = str(kwargs["task_id"])
        rows = []
        # Deterministic synthetic phase output for contract-style assertions.
        for i in range(n_sessions):
            rows.append(
                {
                    "phase": phase,
                    "domain": domain,
                    "task_id": task_id,
                    "run": i + 1,
                    "session_id": start_session + i,
                    "score": [0.0, 1.0, 1.0][i] if n_sessions >= 3 else 1.0,
                    "passed": [False, True, True][i] if n_sessions >= 3 else True,
                    "steps": 3,
                    "tool_errors": 0 if i > 0 else 2,
                    "lessons_loaded": i,
                    "lessons_generated": 1,
                    "lesson_activations": 0,
                    "elapsed_s": 1.0,
                }
            )
        return rows

    monkeypatch.setattr(run_cross_domain, "_run_phase", _fake_run_phase)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_cross_domain.py",
            "--no-train",
            "--test-sessions",
            "3",
            "--start-session",
            "42000",
            "--max-steps",
            "6",
            "--learning-mode",
            "strict",
        ],
    )

    rc = run_cross_domain.main()
    assert rc == 0

    out = capsys.readouterr().out
    marker = "JSON summary:\n"
    assert marker in out
    payload_text = out.split(marker, 1)[1].strip()
    payload = json.loads(payload_text)

    assert set(payload.keys()) == {"config", "transfer", "runs"}
    assert set(payload["transfer"].keys()) == {"first_pass_index", "post_pass_regressions", "delta"}
    assert payload["transfer"]["first_pass_index"] == 2
    assert payload["transfer"]["post_pass_regressions"] == 0
    assert payload["transfer"]["delta"] == 1.0
    assert len(payload["runs"]) == 3
