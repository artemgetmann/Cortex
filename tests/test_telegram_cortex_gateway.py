from __future__ import annotations

import integrations.telegram_cortex_gateway as gateway


def test_classify_run_command_dispatches() -> None:
    decision = gateway.classify_message_text("/run shell_git_transfer_hotfix")
    assert decision.mode == "dispatch"
    assert decision.dispatch_text == "/run shell_git_transfer_hotfix"


def test_classify_plain_text_autorun() -> None:
    original = gateway.AUTO_RUN
    gateway.AUTO_RUN = True
    try:
        decision = gateway.classify_message_text("build a sqlite reconcile task")
    finally:
        gateway.AUTO_RUN = original
    assert decision.mode == "dispatch"
    assert decision.dispatch_text == "/run build a sqlite reconcile task"


def test_classify_unknown_command_is_ignored() -> None:
    decision = gateway.classify_message_text("/foo bar")
    assert decision.mode == "ignore"


def test_format_dispatch_reply_run_summary() -> None:
    payload = {
        "mode": "run",
        "plan": {"task_id": "shell_git_transfer_hotfix", "domain": "shell"},
        "result": {
            "ok": True,
            "session_id": 123,
            "task_id": "shell_git_transfer_hotfix",
            "domain": "shell",
            "metrics": {
                "eval_passed": True,
                "eval_score": 1.0,
                "lesson_activations": 2,
                "v2_retrieval_help_ratio": 0.5,
            },
        },
    }
    text = gateway.format_dispatch_reply(payload)
    assert "Cortex run finished" in text
    assert "eval_passed: True" in text
    assert "lesson_activations: 2" in text
