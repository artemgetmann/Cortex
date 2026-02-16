"""Artic domain adapter for public Art Institute of Chicago API tasks."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from tracks.cli_sqlite.domain_adapter import DomainAdapter, DomainDoc, DomainWorkspace, ToolResult
from tracks.cli_sqlite.tool_aliases import ToolAlias


READ_SKILL_TOOL_NAME = "read_skill"
SHOW_FIXTURE_TOOL_NAME = "show_fixture"
RUN_ARTIC_TOOL_NAME = "run_artic"
ARTIC_BASE_URL = "https://api.artic.edu/api/v1"

_ARTIC_KEYWORDS = re.compile(r"(?i)\b(artic|artworks|search|pagination|query|fields|title|id)\b")

_ARTIC_ALIASES: dict[str, ToolAlias] = {
    "run_artic": ToolAlias(
        opaque_name="dispatch",
        canonical_name="run_artic",
        opaque_description="Execute a request against the workspace. Consult skill docs for parameter semantics.",
        canonical_description=(
            "Execute a GET request to the Art Institute of Chicago API. "
            "Input: method(GET), path(relative), query(object)."
        ),
    ),
    "read_skill": ToolAlias(
        opaque_name="probe",
        canonical_name="read_skill",
        opaque_description="Look up a reference document by ref key.",
        canonical_description="Read full contents of a skill document by stable skill_ref.",
    ),
    "show_fixture": ToolAlias(
        opaque_name="catalog",
        canonical_name="show_fixture",
        opaque_description="Retrieve a named data artifact.",
        canonical_description="Read task fixture/bootstrap file by stable path_ref.",
    ),
}


def _get_tool_api_name(canonical: str, opaque: bool) -> str:
    alias = _ARTIC_ALIASES.get(canonical)
    if alias is None:
        return canonical
    return alias.opaque_name if opaque else canonical


def _get_tool_description(canonical: str, opaque: bool) -> str:
    alias = _ARTIC_ALIASES.get(canonical)
    if alias is None:
        return ""
    return alias.opaque_description if opaque else alias.canonical_description


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _compact_json_with_clip(payload: dict[str, Any], *, max_chars: int = 3600) -> str:
    text = _compact_json(payload)
    if len(text) <= max_chars:
        return text

    min_budget = 32
    budget = max(64, max_chars - 240)
    while budget >= min_budget:
        clipped_payload = {
            "ok": bool(payload.get("ok", True)),
            "request": payload.get("request", {}),
            "status": payload.get("status", 0),
            "truncated": True,
            "result_excerpt": text[:budget] + "...",
        }
        clipped_text = _compact_json(clipped_payload)
        if len(clipped_text) <= max_chars:
            return clipped_text
        budget -= 64

    fallback = {
        "ok": bool(payload.get("ok", True)),
        "request": payload.get("request", {}),
        "status": payload.get("status", 0),
        "truncated": True,
        "result_excerpt": "(truncated)",
    }
    return _compact_json(fallback)


def _normalize_path(path: str) -> str:
    cleaned = path.strip()
    if not cleaned:
        return ""
    if cleaned.startswith(("http://", "https://")):
        return cleaned
    if not cleaned.startswith("/"):
        cleaned = f"/{cleaned}"
    return cleaned


def _build_url(*, path: str, query: dict[str, Any]) -> str:
    base = ARTIC_BASE_URL.rstrip("/")
    url = f"{base}{path}"
    query_pairs: list[tuple[str, str]] = []
    for key, value in query.items():
        key_text = str(key).strip()
        if not key_text:
            continue
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            for item in value:
                if item is None:
                    continue
                query_pairs.append((key_text, str(item)))
            continue
        query_pairs.append((key_text, str(value)))
    if query_pairs:
        url = f"{url}?{urlencode(query_pairs, doseq=True)}"
    return url


def _http_error_detail(exc: HTTPError, *, max_chars: int = 220) -> str:
    try:
        raw = exc.read()
    except Exception:
        raw = b""
    if not raw:
        return ""
    text = raw.decode("utf-8", errors="replace")
    compact = " ".join(text.split())
    if not compact:
        return ""
    if len(compact) > max_chars:
        compact = compact[: max_chars - 3] + "..."
    return f": {compact}"


class ArticAdapter:
    """DomainAdapter implementation for Artic public API tasks."""

    @property
    def name(self) -> str:
        return "artic"

    @property
    def executor_tool_name(self) -> str:
        return RUN_ARTIC_TOOL_NAME

    def tool_defs(self, fixture_refs: list[str], *, opaque: bool) -> list[dict[str, Any]]:
        refs_text = ", ".join(fixture_refs) if fixture_refs else "(none)"
        show_desc = _get_tool_description("show_fixture", opaque)
        return [
            {
                "name": _get_tool_api_name("run_artic", opaque),
                "description": _get_tool_description("run_artic", opaque),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "method": {"type": "string", "enum": ["GET"], "description": "HTTP method (GET only)."},
                        "path": {"type": "string", "description": "Relative API path, e.g. /artworks/search."},
                        "query": {
                            "type": "object",
                            "description": "Query parameters object (e.g. {q:'cat',limit:2,page:1}).",
                            "additionalProperties": True,
                        },
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
            },
            {
                "name": _get_tool_api_name("read_skill", opaque),
                "description": _get_tool_description("read_skill", opaque),
                "input_schema": {
                    "type": "object",
                    "properties": {"skill_ref": {"type": "string"}},
                    "required": ["skill_ref"],
                    "additionalProperties": False,
                },
            },
            {
                "name": _get_tool_api_name("show_fixture", opaque),
                "description": f"{show_desc} Available refs: {refs_text}.",
                "input_schema": {
                    "type": "object",
                    "properties": {"path_ref": {"type": "string"}},
                    "required": ["path_ref"],
                    "additionalProperties": False,
                },
            },
        ]

    def execute(self, tool_name: str, tool_input: dict[str, Any], workspace: DomainWorkspace) -> ToolResult:
        method_raw = tool_input.get("method", "GET")
        if not isinstance(method_raw, str):
            return ToolResult(error=f"run_artic requires string method, got {method_raw!r}")
        method = method_raw.strip().upper() or "GET"
        if method != "GET":
            return ToolResult(error=f"run_artic only supports GET method, got {method_raw!r}")

        path_raw = tool_input.get("path")
        if not isinstance(path_raw, str):
            return ToolResult(error=f"run_artic requires string path, got {path_raw!r}")
        path = _normalize_path(path_raw)
        if not path:
            return ToolResult(error="run_artic requires non-empty path")
        if path.startswith(("http://", "https://")):
            return ToolResult(error="run_artic path must be relative (example: /artworks/search)")

        query_raw = tool_input.get("query", {})
        if query_raw is None:
            query_raw = {}
        if not isinstance(query_raw, dict):
            return ToolResult(error=f"run_artic requires query object, got {query_raw!r}")
        query: dict[str, Any] = dict(query_raw)

        request_context = {
            "method": method,
            "path": path,
            "query": query,
        }
        url = _build_url(path=path, query=query)
        request = Request(
            url=url,
            method="GET",
            headers={
                "Accept": "application/json",
                "User-Agent": "cortex-artic-adapter/1.0",
            },
        )

        try:
            with urlopen(request, timeout=15.0) as response:
                status = int(response.getcode() or 0)
                raw = response.read()
                charset = "utf-8"
                headers = getattr(response, "headers", None)
                if headers is not None and hasattr(headers, "get_content_charset"):
                    detected = headers.get_content_charset()
                    if isinstance(detected, str) and detected.strip():
                        charset = detected.strip()
                body_text = raw.decode(charset, errors="replace")
        except HTTPError as exc:
            detail = _http_error_detail(exc)
            return ToolResult(error=f"Artic request failed: HTTP {exc.code} for GET {path}{detail}")
        except URLError as exc:
            reason = str(getattr(exc, "reason", exc)).strip() or str(exc)
            return ToolResult(error=f"Artic request failed: network error for GET {path}: {reason}")
        except TimeoutError:
            return ToolResult(error=f"Artic request failed: timeout for GET {path}")
        except Exception as exc:
            return ToolResult(error=f"Artic request failed for GET {path}: {type(exc).__name__}: {exc}")

        try:
            parsed = json.loads(body_text)
        except json.JSONDecodeError:
            compact = " ".join(body_text.split())
            snippet = compact[:180] + ("..." if len(compact) > 180 else "")
            return ToolResult(
                error=(
                    f"Artic response parse error for GET {path}: expected JSON, "
                    f"received {snippet!r}"
                )
            )

        payload = {
            "ok": True,
            "request": request_context,
            "status": status,
            "result": parsed,
        }
        return ToolResult(output=_compact_json_with_clip(payload))

    def prepare_workspace(self, task_dir: Path, work_dir: Path) -> DomainWorkspace:
        work_dir.mkdir(parents=True, exist_ok=True)
        fixture_paths: dict[str, Path] = {}
        allowed_suffixes = {".md", ".txt", ".csv", ".json", ".sql"}
        for file_path in sorted(task_dir.iterdir()):
            if not file_path.is_file():
                continue
            if file_path.name == "CONTRACT.json":
                continue
            if file_path.suffix.lower() in allowed_suffixes:
                fixture_paths[file_path.name] = file_path
        return DomainWorkspace(
            task_id=task_dir.name,
            task_dir=task_dir,
            work_dir=work_dir,
            fixture_paths=fixture_paths,
        )

    def capture_final_state(self, workspace: DomainWorkspace) -> str:
        events_path = workspace.work_dir / "events.jsonl"
        if not events_path.exists():
            return "(no events recorded)"

        last_output: str | None = None
        for line in events_path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if row.get("tool") == RUN_ARTIC_TOOL_NAME and row.get("ok") and row.get("output"):
                last_output = str(row["output"])
        if not last_output:
            return "(no successful run_artic output)"
        return f"Last successful run_artic output:\n{last_output[:2400]}"

    def system_prompt_fragment(self) -> str:
        return (
            "You are controlling an Art Institute of Chicago API environment.\n"
            "Rules:\n"
            "- Use run_artic to execute GET requests against https://api.artic.edu/api/v1.\n"
            "- run_artic input fields: method (GET only), path (relative), query (object).\n"
            "- Use show_fixture to inspect task files.\n"
            "- Before starting, check the Skills metadata section. If a skill's title or\n"
            "  description seems relevant to your task, read it with read_skill using the\n"
            "  exact skill_ref listed. Only call read_skill with refs that are listed —\n"
            "  do not guess or invent skill_ref names.\n"
            "- Use precise query params for pagination/field extraction when requested.\n"
        )

    def quality_keywords(self) -> re.Pattern[str]:
        return _ARTIC_KEYWORDS

    def build_alias_map(self, *, opaque: bool) -> dict[str, str]:
        result: dict[str, str] = {}
        for canonical, alias in _ARTIC_ALIASES.items():
            api_name = alias.opaque_name if opaque else canonical
            result[api_name] = canonical
        return result

    def docs_manifest(self) -> list[DomainDoc]:
        return []

