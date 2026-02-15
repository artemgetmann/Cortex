#!/usr/bin/env python3
"""fluxtool — holdout DSL with remapped command/operator language.

fluxtool intentionally renames gridtool syntax to validate transfer honestly.
It compiles fluxtool commands to gridtool commands, executes gridtool, then
maps error/output vocabulary back to fluxtool terms.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


GRIDTOOL_PATH = Path(__file__).resolve().parent / "gridtool.py"

COMMAND_TO_GRID: dict[str, str] = {
    "IMPORT": "LOAD",
    "FILTER": "KEEP",
    "EXCLUDE": "TOSS",
    "GROUP": "TALLY",
    "SORT": "RANK",
    "COLUMNS": "PICK",
    "COMPUTE": "DERIVE",
    "ATTACH": "MERGE",
    "DISPLAY": "SHOW",
}

GRID_TO_COMMAND = {v: k for k, v in COMMAND_TO_GRID.items()}

OP_TO_GRID = {
    "is": "eq",
    "isnt": "neq",
    "above": "gt",
    "below": "lt",
    "atleast": "gte",
    "atmost": "lte",
}

GRID_TO_OP = {v: k for k, v in OP_TO_GRID.items()}


def _convert_error_mode_map(raw: str) -> str:
    # Convert fluxtool command keys (IMPORT/GROUP/...) to underlying gridtool
    # command keys so per-command error policy still works after translation.
    out: list[str] = []
    text = (raw or "").strip()
    if not text:
        return ""
    for item in text.split(","):
        pair = item.strip()
        if "=" not in pair:
            continue
        cmd, mode = [chunk.strip() for chunk in pair.split("=", 1)]
        grid_cmd = COMMAND_TO_GRID.get(cmd.upper())
        if not grid_cmd:
            continue
        out.append(f"{grid_cmd}={mode}")
    return ",".join(out)


def _translate_filter(cmd: str, args: str, lineno: int) -> str:
    parts = args.split(None, 2)
    if len(parts) < 3:
        raise ValueError(f"ERROR at line {lineno}: {cmd} syntax: {cmd} column op value")
    col, op_raw, value = parts
    op = OP_TO_GRID.get(op_raw.lower())
    if not op:
        valid = ", ".join(sorted(OP_TO_GRID.keys()))
        raise ValueError(f"ERROR at line {lineno}: {cmd} unknown operator '{op_raw}'. Valid: {valid}")
    grid_cmd = COMMAND_TO_GRID[cmd]
    return f"{grid_cmd} {col} {op} {value}"


def _translate_line(line: str, lineno: int) -> str:
    parts = line.split(None, 1)
    cmd = parts[0].upper()
    args = parts[1].strip() if len(parts) > 1 else ""
    if cmd not in COMMAND_TO_GRID:
        known = ", ".join(sorted(COMMAND_TO_GRID.keys()))
        raise ValueError(f"ERROR at line {lineno}: Unknown command '{cmd}'. Valid commands: {known}")

    if cmd == "IMPORT":
        return f"LOAD {args}"
    if cmd in {"FILTER", "EXCLUDE"}:
        return _translate_filter(cmd, args, lineno)
    if cmd == "GROUP":
        # Holdout syntax intentionally remaps arrow token (`=>`) while keeping
        # aggregation semantics equivalent to gridtool TALLY.
        m = re.match(r"(\S+)\s*=>\s*(.*)", args)
        if not m:
            raise ValueError(
                f"ERROR at line {lineno}: GROUP syntax: GROUP group_col => alias=func(col)"
            )
        return f"TALLY {m.group(1)} -> {m.group(2).strip()}"
    if cmd == "SORT":
        parts = args.split(None, 1)
        if len(parts) < 2:
            raise ValueError(f"ERROR at line {lineno}: SORT syntax: SORT column up|down")
        direction = parts[1].strip().lower()
        if direction == "up":
            mapped = "asc"
        elif direction == "down":
            mapped = "desc"
        else:
            raise ValueError(f"ERROR at line {lineno}: SORT direction must be 'up' or 'down', got '{parts[1]}'")
        return f"RANK {parts[0]} {mapped}"
    if cmd == "COLUMNS":
        return f"PICK {args}"
    if cmd == "COMPUTE":
        m = re.match(r"(\w+)\s*:=\s*(.*)", args)
        if not m:
            raise ValueError(f"ERROR at line {lineno}: COMPUTE syntax: COMPUTE new_col := expression")
        return f"DERIVE {m.group(1)} = {m.group(2).strip()}"
    if cmd == "ATTACH":
        m = re.match(r'(".*?")\s+BY\s+(\w+)$', args, flags=re.IGNORECASE)
        if not m:
            raise ValueError(f'ERROR at line {lineno}: ATTACH syntax: ATTACH "file.csv" BY column')
        return f"MERGE {m.group(1)} ON {m.group(2)}"
    if cmd == "DISPLAY":
        return f"SHOW {args}".strip()
    return line


def _translate_script(text: str) -> str:
    # Parse line-by-line to preserve deterministic line numbers in error output.
    translated: list[str] = []
    for idx, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        translated.append(_translate_line(line, idx))
    return "\n".join(translated)


def _map_back_terms(text: str) -> str:
    if not text:
        return text

    out = text
    # Command vocabulary
    for grid_cmd, flux_cmd in GRID_TO_COMMAND.items():
        out = re.sub(rf"\b{re.escape(grid_cmd)}\b", flux_cmd, out)
    # Operators and symbolic hints
    for grid_op, flux_op in GRID_TO_OP.items():
        out = re.sub(rf"\b{re.escape(grid_op)}\b", flux_op, out)
    out = out.replace("->", "=>")
    out = out.replace("asc", "up").replace("desc", "down")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="fluxtool: holdout pipeline CLI")
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--cryptic", action="store_true")
    ap.add_argument("--semi-helpful", action="store_true")
    ap.add_argument("--error-mode-map", default="")
    args = ap.parse_args()

    raw_input = sys.stdin.read()
    try:
        translated = _translate_script(raw_input)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    cmd = ["python3", str(GRIDTOOL_PATH), "--workdir", args.workdir]
    if args.cryptic:
        cmd.append("--cryptic")
    elif args.semi_helpful:
        cmd.append("--semi-helpful")
    mapped_error_mode_map = _convert_error_mode_map(args.error_mode_map)
    if mapped_error_mode_map:
        cmd.extend(["--error-mode-map", mapped_error_mode_map])

    try:
        result = subprocess.run(
            cmd,
            input=translated,
            capture_output=True,
            text=True,
            timeout=5.0,
        )
    except subprocess.TimeoutExpired:
        print("fluxtool timed out after 5.0s", file=sys.stderr)
        return 1
    except FileNotFoundError:
        print("python3 or gridtool.py not found", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"fluxtool execution failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if result.stdout:
        print(_map_back_terms(result.stdout.rstrip("\n")))
    if result.stderr:
        print(_map_back_terms(result.stderr.rstrip("\n")), file=sys.stderr)
    return int(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
