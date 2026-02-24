#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# Root is fixed to Cortex repo so dispatch always hits the same learning core.
ROOT_DIR = Path(__file__).resolve().parents[1]
DISPATCHER = ROOT_DIR / "integrations" / "openclaw_agi_dispatch.py"
STATE_PATH = Path(
    os.environ.get(
        "CORTEX_TELEGRAM_STATE_PATH",
        str(ROOT_DIR / "integrations" / "telegram-cortex-bot" / "state.json"),
    )
)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
if not TOKEN:
    TOKEN = os.environ.get("OPENCLAW_AGI_TELEGRAM_BOT_TOKEN", "").strip()

ALLOWED_USERS_RAW = (
    os.environ.get("TELEGRAM_ALLOWED_USERS", "").strip()
    or os.environ.get("OPENCLAW_AGI_ALLOW_FROM", "").strip()
)
ALLOWED_USERS = {
    x.strip()
    for x in ALLOWED_USERS_RAW.split(",")
    if x.strip()
}

AUTO_RUN = os.environ.get("CORTEX_TELEGRAM_AUTO_RUN", "1").strip().lower() not in {
    "0",
    "false",
    "off",
    "no",
}
POLL_TIMEOUT_SECONDS = int(os.environ.get("CORTEX_TELEGRAM_POLL_TIMEOUT_S", "30"))
RUN_TIMEOUT_SECONDS = int(os.environ.get("CORTEX_TELEGRAM_RUN_TIMEOUT_S", "2400"))


@dataclass(frozen=True)
class DispatchDecision:
    mode: str
    dispatch_text: str | None = None
    note: str | None = None


def _api_url(method: str) -> str:
    return f"https://api.telegram.org/bot{TOKEN}/{method}"


def _http_json(
    method: str,
    payload: dict[str, Any] | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    body = None
    headers = {}
    if payload is not None:
        body = urllib.parse.urlencode(payload).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    # Telegram Bot API accepts form-encoded POST payloads for both read/write methods.
    req = urllib.request.Request(_api_url(method), data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def _load_offset() -> int:
    # Offset persistence prevents replaying old updates after restarts.
    if not STATE_PATH.exists():
        return 0
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return 0
    value = payload.get("offset")
    if isinstance(value, int) and value >= 0:
        return value
    return 0


def _save_offset(offset: int) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps({"offset": int(offset)}, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def classify_message_text(text: str) -> DispatchDecision:
    normalized = " ".join(text.strip().split())
    if not normalized:
        return DispatchDecision(mode="ignore")
    lowered = normalized.lower()

    if lowered in {"/start", "/help"}:
        return DispatchDecision(mode="help")
    if lowered.startswith("/learn-status") or lowered.startswith("/status"):
        return DispatchDecision(mode="dispatch", dispatch_text=normalized)
    if lowered.startswith("/run"):
        return DispatchDecision(mode="dispatch", dispatch_text=normalized)
    if lowered.startswith("/chat"):
        return DispatchDecision(mode="dispatch", dispatch_text=normalized)
    if normalized.startswith("/"):
        return DispatchDecision(mode="ignore", note="Unsupported command for Cortex bridge.")

    if AUTO_RUN:
        # Plain text goes through Cortex loop by default so Telegram feels like one main agent.
        # This is intentionally simple and can be disabled for strict command-only operation.
        return DispatchDecision(mode="dispatch", dispatch_text=f"/run {normalized}")

    return DispatchDecision(mode="ignore", note="Send /run <task> to execute Cortex.")


def _dispatch(chat_scope: str, text: str) -> dict[str, Any]:
    cmd = [
        "python3",
        str(DISPATCHER),
        "--chat-id",
        chat_scope,
        "--text",
        text,
    ]
    # Dispatch stays out-of-process to keep transport logic isolated from core runtime failures.
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT_DIR),
        capture_output=True,
        text=True,
        timeout=RUN_TIMEOUT_SECONDS,
    )
    stdout = (proc.stdout or "").strip()
    if not stdout:
        return {
            "ok": False,
            "error": "dispatcher produced no output",
            "stderr_tail": "\n".join((proc.stderr or "").splitlines()[-12:]),
            "returncode": proc.returncode,
        }
    try:
        payload = json.loads(stdout)
    except Exception:
        return {
            "ok": False,
            "error": "dispatcher output is not valid JSON",
            "stdout_tail": "\n".join(stdout.splitlines()[-12:]),
            "stderr_tail": "\n".join((proc.stderr or "").splitlines()[-12:]),
            "returncode": proc.returncode,
        }

    payload["_returncode"] = proc.returncode
    if proc.stderr:
        payload["_stderr_tail"] = "\n".join(proc.stderr.splitlines()[-12:])
    return payload


def _format_status(payload: dict[str, Any]) -> str:
    latest = payload.get("latest_session") or {}
    return (
        "Cortex learning status\n"
        f"- lessons_total: {payload.get('lessons_total', 0)}\n"
        f"- lessons_scoped: {payload.get('lessons_scoped', 0)}\n"
        f"- latest_task: {latest.get('task_id')}\n"
        f"- latest_domain: {latest.get('domain')}\n"
        f"- eval_passed: {latest.get('eval_passed')}\n"
        f"- eval_score: {latest.get('eval_score')}\n"
        f"- lesson_activations: {latest.get('lesson_activations')}\n"
        f"- retrieval_help_ratio: {latest.get('v2_retrieval_help_ratio')}"
    )


def _format_run(payload: dict[str, Any]) -> str:
    plan = payload.get("plan") or {}
    result = payload.get("result") or {}
    metrics = result.get("metrics") or {}
    lines = [
        "Cortex run finished",
        f"- ok: {result.get('ok')}",
        f"- task_id: {result.get('task_id') or plan.get('task_id')}",
        f"- domain: {result.get('domain') or plan.get('domain')}",
        f"- session_id: {result.get('session_id')}",
        f"- eval_passed: {metrics.get('eval_passed')}",
        f"- eval_score: {metrics.get('eval_score')}",
        f"- lesson_activations: {metrics.get('lesson_activations')}",
        f"- retrieval_help_ratio: {metrics.get('v2_retrieval_help_ratio')}",
    ]
    stderr_tail = payload.get("_stderr_tail") or result.get("stderr_tail")
    if stderr_tail:
        lines.append("- stderr_tail:")
        lines.append(str(stderr_tail))
    return "\n".join(lines)


def format_dispatch_reply(payload: dict[str, Any]) -> str:
    mode = str(payload.get("mode", ""))
    if not payload.get("ok", True) and mode != "run":
        return (
            "Cortex bridge error\n"
            f"- error: {payload.get('error')}\n"
            f"- returncode: {payload.get('returncode') or payload.get('_returncode')}"
        )
    if mode == "status":
        return _format_status(payload)
    if mode == "chat":
        return str(payload.get("reply", "Chat mode."))
    if mode == "run":
        return _format_run(payload)
    return json.dumps(payload, ensure_ascii=True, indent=2)


def _send_message(chat_id: int, text: str) -> None:
    chunk_size = 3500
    remaining = text
    while remaining:
        chunk = remaining[:chunk_size]
        remaining = remaining[chunk_size:]
        _http_json(
            "sendMessage",
            payload={
                "chat_id": str(chat_id),
                "text": chunk,
            },
            timeout=30,
        )


def _process_update(update: dict[str, Any]) -> None:
    message = update.get("message") or update.get("edited_message") or {}
    if not isinstance(message, dict):
        return
    text = message.get("text")
    if not isinstance(text, str):
        return

    from_user = message.get("from") or {}
    user_id = str(from_user.get("id", "")).strip()
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if not isinstance(chat_id, int):
        return

    # Hard gate: if allowlist is set, reject everything else immediately.
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        _send_message(chat_id, "Unauthorized.")
        return

    decision = classify_message_text(text)
    if decision.mode == "ignore":
        if decision.note:
            _send_message(chat_id, decision.note)
        return
    if decision.mode == "help":
        _send_message(
            chat_id,
            (
                "Cortex Telegram bridge\n"
                "- /run <task or task_id>\n"
                "- /learn-status\n"
                "- /chat <message>\n"
                f"- plain text maps to /run: {AUTO_RUN}"
            ),
        )
        return

    assert decision.dispatch_text is not None
    # Send immediate ack so user sees progress while long CLI runs execute.
    _send_message(chat_id, "Running Cortex task...")
    chat_scope = f"tg-{chat_id}"
    payload = _dispatch(chat_scope=chat_scope, text=decision.dispatch_text)
    _send_message(chat_id, format_dispatch_reply(payload))


def _poll_updates(offset: int) -> tuple[int, list[dict[str, Any]]]:
    data = _http_json(
        "getUpdates",
        payload={
            "offset": str(offset),
            "timeout": str(POLL_TIMEOUT_SECONDS),
            "allowed_updates": json.dumps(["message", "edited_message"]),
        },
        timeout=POLL_TIMEOUT_SECONDS + 10,
    )
    if not data.get("ok"):
        return offset, []
    result = data.get("result")
    if not isinstance(result, list):
        return offset, []

    next_offset = offset
    rows: list[dict[str, Any]] = []
    for entry in result:
        if not isinstance(entry, dict):
            continue
        update_id = entry.get("update_id")
        if isinstance(update_id, int):
            next_offset = max(next_offset, update_id + 1)
        rows.append(entry)
    return next_offset, rows


def main() -> int:
    if not TOKEN:
        print("error: TELEGRAM_BOT_TOKEN is required")
        return 2
    if not DISPATCHER.exists():
        print(f"error: dispatcher missing at {DISPATCHER}")
        return 2

    offset = _load_offset()
    print("Cortex Telegram bridge started")
    print(f"- auto_run: {AUTO_RUN}")
    print(f"- allowed_users: {','.join(sorted(ALLOWED_USERS)) or '(all)'}")
    print(f"- state_path: {STATE_PATH}")
    # Long-poll loop: this is intentionally single-process and minimal for debuggability.
    while True:
        try:
            next_offset, rows = _poll_updates(offset)
            for row in rows:
                _process_update(row)
            if next_offset != offset:
                offset = next_offset
                _save_offset(offset)
        except KeyboardInterrupt:
            print("stopped")
            return 0
        except subprocess.TimeoutExpired:
            # Timeout means a run exceeded configured runtime budget.
            print("warning: dispatcher timeout")
            time.sleep(1.0)
        except urllib.error.URLError as exc:
            print(f"warning: telegram transport error: {exc}")
            time.sleep(2.0)
        except Exception as exc:
            print(f"warning: unexpected error: {exc}")
            time.sleep(1.0)


if __name__ == "__main__":
    raise SystemExit(main())
