from __future__ import annotations

import json
import re
import subprocess
from typing import Any, Callable

from tracks.cli_sqlite.domain_adapter import DomainWorkspace


def _is_equivalent_hotfix_git_am_command(*, command: str, patch_file: str) -> bool:
    """
    Detect equivalent `git am` variants for hotfix transfer contract matching.

    We intentionally allow common equivalent forms that can break strict regex
    matching in CONTRACT required_event_patterns:
    - `git -C target_repo am ../<patch>`
    - `git am --3way ../<patch>`
    - quoted patch path variants (`'../<patch>'`, `"../<patch>"`)
    """
    text = str(command or "")
    patch = str(patch_file or "").strip()
    if not text.strip() or not patch:
        return False
    if not re.search(r"(?i)\bgit\b", text) or not re.search(r"(?i)\bam\b", text):
        return False
    am_calls = re.finditer(
        r"(?is)\bgit\b(?:\s+-C\s+[^\s;&|]+)?\s+am\b(?P<tail>[^\n;&|]*)",
        text,
    )
    for match in am_calls:
        tail = str(match.group("tail") or "")
        if re.search(
            rf"(?is)(?:^|[\s\"'])(?:\./)?(?:\.\./)?{re.escape(patch)}(?:[\s\"']|$)",
            tail,
        ):
            return True
    return False


def _load_hotfix_transfer_expectations(*, workspace: DomainWorkspace, task_id: str) -> dict[str, Any]:
    """
    Resolve deterministic closure-check expectations for hotfix transfer tasks.

    For the hard task, runtime variants come from `variant_spec.json`. For the
    base task, fixed defaults are used.
    """
    expectations: dict[str, Any] = {
        "patch_file": "hotfix.patch",
        "hotfix_file": "hotfix.txt",
        "commit_message": "hotfix: add retry backoff note",
        "summary_lines": [
            "TRANSFER_BRANCH main",
            "TRANSFER_PATCHES 1",
        ],
    }
    if str(task_id).strip() != "shell_git_transfer_hotfix_hard":
        return expectations
    variant_path = workspace.work_dir / "variant_spec.json"
    if not variant_path.exists():
        return expectations
    try:
        variant_payload = json.loads(variant_path.read_text(encoding="utf-8"))
    except Exception:
        return expectations
    if not isinstance(variant_payload, dict):
        return expectations
    patch_file = str(variant_payload.get("patch_file", "")).strip()
    hotfix_file = str(variant_payload.get("hotfix_file", "")).strip()
    commit_message = str(variant_payload.get("commit_message", "")).strip()
    summary_lines = variant_payload.get("summary_lines", [])
    if patch_file:
        expectations["patch_file"] = patch_file
    if hotfix_file:
        expectations["hotfix_file"] = hotfix_file
    if commit_message:
        expectations["commit_message"] = commit_message
    if isinstance(summary_lines, list):
        clean_summary = [str(row).strip() for row in summary_lines if str(row).strip()]
        if clean_summary:
            expectations["summary_lines"] = clean_summary
    return expectations


def _canonicalize_hotfix_transfer_eval_events(
    *,
    events: list[dict[str, Any]],
    workspace: DomainWorkspace,
    task_id: str,
    is_shell_hotfix_transfer_task_fn: Callable[[str], bool],
    load_hotfix_transfer_expectations_fn: Callable[..., dict[str, Any]],
    is_equivalent_hotfix_git_am_command_fn: Callable[..., bool],
) -> list[dict[str, Any]]:
    """
    Canonicalize hotfix transfer git-am event variants before contract matching.

    Scope is intentionally narrow and backward-compatible:
    - only applies to shell hotfix transfer task ids
    - keeps original events intact, optionally appending one synthetic alias
    - never touches persisted events on disk
    """
    if not is_shell_hotfix_transfer_task_fn(task_id):
        return events

    expected = load_hotfix_transfer_expectations_fn(workspace=workspace, task_id=task_id)
    patch_file = str(expected.get("patch_file", "")).strip()
    if not patch_file:
        return events

    canonical_command = f"git am ../{patch_file}"
    canonical_pattern = re.compile(
        rf"(?is)\bgit\s+am\s+\.\./{re.escape(patch_file)}(?:\s|$|[\"'])"
    )

    # Fast path: canonical command already present in raw events.
    for row in events:
        if not isinstance(row, dict) or str(row.get("tool", "")).strip() != "run_bash":
            continue
        tool_input = row.get("tool_input", {})
        if not isinstance(tool_input, dict):
            continue
        command = str(tool_input.get("command", "") or "")
        if canonical_pattern.search(command):
            return events

    # Append one synthetic alias event when we detect an equivalent variant.
    for row in events:
        if not isinstance(row, dict) or str(row.get("tool", "")).strip() != "run_bash":
            continue
        tool_input = row.get("tool_input", {})
        if not isinstance(tool_input, dict):
            continue
        command = str(tool_input.get("command", "") or "")
        if not is_equivalent_hotfix_git_am_command_fn(command=command, patch_file=patch_file):
            continue
        synthetic_event = {
            "step": row.get("step"),
            "tool": "run_bash",
            "tool_input": {"command": canonical_command},
            "ok": True,
            "output": "",
            "error": None,
        }
        return [*events, synthetic_event]
    return events


def _run_shell_hotfix_transfer_closure_check(
    *,
    workspace: DomainWorkspace,
    task_id: str,
    is_shell_hotfix_transfer_task_fn: Callable[[str], bool],
    load_hotfix_transfer_expectations_fn: Callable[..., dict[str, Any]],
    build_gap_row_fn: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    """
    Run deterministic pre-stop closure checks for shell hotfix transfer tasks.

    This validates two closure conditions before allowing stop:
    - patch actually landed in `target_repo` history
    - transfer summary file contains required lines
    """
    if not is_shell_hotfix_transfer_task_fn(task_id):
        return {
            "applicable": False,
            "passed": True,
            "evidence": [],
            "missing_gaps": [],
        }
    expected = load_hotfix_transfer_expectations_fn(workspace=workspace, task_id=task_id)
    patch_file = str(expected.get("patch_file", "")).strip()
    hotfix_file = str(expected.get("hotfix_file", "")).strip()
    commit_message = str(expected.get("commit_message", "")).strip()
    summary_lines = [str(row).strip() for row in (expected.get("summary_lines", []) or []) if str(row).strip()]
    patch_path = workspace.work_dir / patch_file
    target_repo = workspace.work_dir / "target_repo"
    hotfix_path = target_repo / hotfix_file
    summary_path = target_repo / "transfer_summary.txt"

    evidence: list[str] = [
        f"closure_check task_id={task_id}",
        f"closure_expect patch_file={patch_file}",
        f"closure_expect hotfix_file={hotfix_file}",
        f"closure_expect summary_lines={json.dumps(summary_lines, ensure_ascii=True)}",
    ]
    missing_gaps: list[dict[str, Any]] = []

    if patch_file and not patch_path.exists():
        missing_gaps.append(
            build_gap_row_fn(
                reason_code="missing_required_file",
                gap_type="required_file",
                detail=patch_file,
            )
        )
    if hotfix_file and not hotfix_path.exists():
        missing_gaps.append(
            build_gap_row_fn(
                reason_code="missing_required_file",
                gap_type="required_file",
                detail=f"target_repo/{hotfix_file}",
            )
        )

    if not summary_path.exists():
        missing_gaps.append(
            build_gap_row_fn(
                reason_code="missing_required_file",
                gap_type="required_file",
                detail="target_repo/transfer_summary.txt",
            )
        )
    else:
        summary_text = summary_path.read_text(encoding="utf-8", errors="replace")
        for line in summary_lines:
            if line not in summary_text:
                missing_gaps.append(
                    build_gap_row_fn(
                        reason_code="missing_required_file_content_pattern",
                        gap_type="required_file_content_pattern",
                        detail=f"target_repo/transfer_summary.txt::{line}",
                    )
                )

    # Ensure the target history contains the expected patch commit subject.
    # This catches "file copied manually" paths that bypass actual patch apply.
    if commit_message and target_repo.exists():
        try:
            log_result = subprocess.run(
                ["git", "-C", str(target_repo), "log", "--format=%s", "-n", "20"],
                capture_output=True,
                text=True,
                timeout=6.0,
                check=False,
            )
            if log_result.returncode != 0:
                missing_gaps.append(
                    build_gap_row_fn(
                        reason_code="missing_required_event_pattern",
                        gap_type="required_event_pattern",
                        detail=f"git_log_failed:{(log_result.stderr or log_result.stdout or '').strip()}",
                    )
                )
            else:
                subjects = [row.strip() for row in (log_result.stdout or "").splitlines() if row.strip()]
                if commit_message not in subjects:
                    missing_gaps.append(
                        build_gap_row_fn(
                            reason_code="missing_required_event_pattern",
                            gap_type="required_event_pattern",
                            detail=commit_message,
                        )
                    )
        except Exception as exc:
            missing_gaps.append(
                build_gap_row_fn(
                    reason_code="missing_required_event_pattern",
                    gap_type="required_event_pattern",
                    detail=f"git_log_exception:{type(exc).__name__}:{exc}",
                )
            )

    # Ensure the expected hotfix file is present in HEAD tree (committed state).
    if hotfix_file and target_repo.exists():
        show_result = subprocess.run(
            ["git", "-C", str(target_repo), "show", f"HEAD:{hotfix_file}"],
            capture_output=True,
            text=True,
            timeout=6.0,
            check=False,
        )
        if show_result.returncode != 0:
            missing_gaps.append(
                build_gap_row_fn(
                    reason_code="missing_required_file",
                    gap_type="required_file",
                    detail=f"target_repo/{hotfix_file}",
                )
            )

    deduped: list[dict[str, Any]] = []
    seen_signatures: set[str] = set()
    for gap in missing_gaps:
        signature = str(gap.get("gap_signature", "")).strip()
        if not signature or signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        deduped.append(gap)
    missing_gaps = deduped
    if missing_gaps:
        evidence.extend(
            [f"closure_missing {row.get('reason_code')}::{row.get('gap_type')}::{row.get('detail')}" for row in missing_gaps]
        )
    else:
        evidence.append("closure_check passed")
    return {
        "applicable": True,
        "passed": len(missing_gaps) == 0,
        "evidence": evidence,
        "missing_gaps": missing_gaps,
        "expected": expected,
    }
