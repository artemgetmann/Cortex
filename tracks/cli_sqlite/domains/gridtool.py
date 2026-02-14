#!/usr/bin/env python3
"""gridtool — pipeline-style CSV data processor with non-standard syntax.

Reads commands from stdin, processes CSV data, writes results to stdout.
Errors go to stderr with specific, helpful messages.

Usage:
    python3 gridtool.py --workdir /path/to/workdir
"""

import argparse
import csv
import os
import re
import sys

# Global flag: when True, error messages omit helpful hints
CRYPTIC_MODE = False
# Global flag: when True, error messages hint without giving full answers
SEMI_HELPFUL_MODE = False


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

SQL_MISTAKES = {
    "SELECT": "PICK",
    "ORDER": "RANK",
    "SORT": "RANK",
    "GROUP": "TALLY",
    "OUTPUT": "SHOW",
    "PRINT": "SHOW",
    "FILTER": "KEEP",
    "WHERE": "KEEP",
    "JOIN": "MERGE",
    "DROP": "TOSS",
    "EXCLUDE": "TOSS",
    "COMPUTE": "DERIVE",
    "CALCULATE": "DERIVE",
    "IMPORT": "LOAD",
    "READ": "LOAD",
    "OPEN": "LOAD",
}

VALID_OPS = {"eq", "neq", "gt", "lt", "gte", "lte"}
SYMBOL_OPS = {"=", "!=", ">", "<", ">=", "<=", "==", "<>"}
AGG_FUNCS = {"sum", "count", "avg", "min", "max"}


def _try_float(val: str):
    """Attempt to parse a string as float; return original string on failure."""
    try:
        return float(val)
    except (ValueError, TypeError):
        return val


def _compare(row_val, op: str, target):
    """Apply a word-operator comparison. Both sides are auto-coerced."""
    left = _try_float(row_val)
    right = _try_float(target)
    both_numeric = isinstance(left, float) and isinstance(right, float)
    if not both_numeric:
        left, right = str(left), str(right)
    if op == "eq":
        return left == right
    if op == "neq":
        return left != right
    if op == "gt":
        return left > right
    if op == "lt":
        return left < right
    if op == "gte":
        return left >= right
    if op == "lte":
        return left <= right
    return False  # unreachable after validation


def _parse_quoted(text: str):
    """Extract a double-quoted string from the start of text. Returns (value, rest)."""
    m = re.match(r'"([^"]*)"(.*)', text)
    if not m:
        return None, text
    return m.group(1), m.group(2).strip()


def _available_cols(rows):
    """Return column names from the first row, or empty list."""
    if not rows:
        return []
    return list(rows[0].keys())


def _check_col(col: str, rows, lineno: int):
    """Validate that a column exists; raise on failure."""
    available = _available_cols(rows)
    if col not in available:
        cols_str = ", ".join(available) if available else "(no data loaded)"
        _fail(lineno, f"Column '{col}' not found. Available: {cols_str}")


_CRYPTIC_OVERRIDES: dict[re.Pattern[str], str] = {
    re.compile(r"TALLY syntax:.*"): "TALLY: syntax error.",
    re.compile(r"TALLY: unexpected text.*"): "TALLY: syntax error.",
    re.compile(r"RANK direction must be.*"): "RANK: invalid direction.",
    re.compile(r"RANK syntax:.*"): "RANK: syntax error.",
    re.compile(r"KEEP syntax:.*"): "KEEP: syntax error.",
    re.compile(r"KEEP requires word operator.*"): "KEEP: invalid operator.",
    re.compile(r"KEEP unknown operator.*"): "KEEP: invalid operator.",
    re.compile(r"TOSS syntax:.*"): "TOSS: syntax error.",
    re.compile(r"TOSS requires word operator.*"): "TOSS: invalid operator.",
    re.compile(r"TOSS unknown operator.*"): "TOSS: invalid operator.",
    re.compile(r"DERIVE syntax:.*"): "DERIVE: syntax error.",
    re.compile(r"MERGE syntax:.*"): "MERGE: syntax error.",
    re.compile(r"Unknown function '(\w+)'.*"): r"Unknown function '\1'.",
    re.compile(r"Column '(\w+)' not found\..*"): r"Column '\1' not found.",
    re.compile(r"Unknown command '(\w+)'\..*"): r"Unknown command '\1'.",
    re.compile(r"LOAD path must be quoted\..*"): "LOAD: invalid argument.",
    re.compile(r"MERGE path must be quoted\..*"): "MERGE: invalid argument.",
    re.compile(r"SHOW takes an optional.*"): "SHOW: invalid argument.",
    re.compile(r"File not found:.*"): "File not found.",
}


_SEMI_HELPFUL_OVERRIDES: dict[re.Pattern[str], str] = {
    # TALLY: hints at arrow syntax without showing full format
    re.compile(r"TALLY syntax:.*"): "TALLY: expected arrow operator '->' after group column.",
    re.compile(r"TALLY: unexpected text.*"): "TALLY: separate multiple aggregations with commas.",
    # RANK: hints at valid directions
    re.compile(r"RANK direction must be.*"): "RANK: direction must be a word — 'asc' or 'desc'.",
    re.compile(r"RANK syntax:.*"): "RANK: requires a column name and direction.",
    # KEEP/TOSS: hints at word operators without listing them all
    re.compile(r"KEEP syntax:.*"): "KEEP: requires column, operator, and value.",
    re.compile(r"KEEP requires word operator.*"): "KEEP: operators must be words (like 'eq'), not symbols.",
    re.compile(r"KEEP unknown operator.*"): "KEEP: unknown operator. Use word-based comparison operators.",
    re.compile(r"TOSS syntax:.*"): "TOSS: requires column, operator, and value.",
    re.compile(r"TOSS requires word operator.*"): "TOSS: operators must be words (like 'eq'), not symbols.",
    re.compile(r"TOSS unknown operator.*"): "TOSS: unknown operator. Use word-based comparison operators.",
    # DERIVE: hints at format
    re.compile(r"DERIVE syntax:.*"): "DERIVE: expected 'new_col = expression' format.",
    # MERGE: hints at quoting
    re.compile(r"MERGE syntax:.*"): "MERGE: requires a quoted path and ON keyword.",
    re.compile(r"MERGE path must be quoted\..*"): "MERGE: file path must be in double quotes.",
    # LOAD: hints at quoting
    re.compile(r"LOAD path must be quoted\..*"): "LOAD: file path must be in double quotes.",
    # Functions: hints at case sensitivity
    re.compile(r"Unknown function '(\w+)'.*"): r"Unknown function '\1'. Functions are case-sensitive — use lowercase.",
    # Column: keep column name but strip available list
    re.compile(r"Column '(\w+)' not found\..*"): r"Column '\1' not found in current data.",
    # Command: hint at correct command without listing all
    re.compile(r"Unknown command '(\w+)'\. Did you mean '(\w+)'\?"):
        r"Unknown command '\1'. This is not SQL — gridtool has its own command names.",
    re.compile(r"Unknown command '(\w+)'\..*"): r"Unknown command '\1'. This is not SQL — gridtool has its own command names.",
    # SHOW
    re.compile(r"SHOW takes an optional.*"): "SHOW: optional argument must be a number (row limit).",
    # File not found: keep path but strip resolved path
    re.compile(r"File not found: \"([^\"]+)\" \(resolved.*"): r'File not found: "\1".',
}


def _strip_hints(msg: str) -> str:
    """Replace helpful error messages with opaque versions in cryptic mode."""
    for pattern, replacement in _CRYPTIC_OVERRIDES.items():
        m = pattern.search(msg)
        if m:
            return pattern.sub(replacement, msg)
    return msg


def _semi_helpful_hints(msg: str) -> str:
    """Replace detailed error messages with semi-helpful hints."""
    for pattern, replacement in _SEMI_HELPFUL_OVERRIDES.items():
        m = pattern.search(msg)
        if m:
            return pattern.sub(replacement, msg)
    return msg


def _fail(lineno: int, msg: str):
    """Print error to stderr and exit."""
    if CRYPTIC_MODE:
        msg = _strip_hints(msg)
    elif SEMI_HELPFUL_MODE:
        msg = _semi_helpful_hints(msg)
    print(f"ERROR at line {lineno}: {msg}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def cmd_load(args: str, rows, workdir: str, lineno: int):
    path, _ = _parse_quoted(args)
    if path is None:
        _fail(lineno, f'LOAD path must be quoted. Use: LOAD "filename.csv"')
    filepath = os.path.join(workdir, path)
    if not os.path.isfile(filepath):
        _fail(lineno, f'File not found: "{path}" (resolved to {filepath})')
    with open(filepath, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def cmd_keep(args: str, rows, lineno: int):
    if not rows:
        _fail(lineno, "KEEP requires data. Use LOAD first.")
    parts = _tokenize_filter(args, lineno)
    if len(parts) < 3:
        _fail(lineno, "KEEP syntax: KEEP column op value")
    col, op, value = parts[0], parts[1], parts[2]
    _validate_filter(col, op, value, rows, lineno, "KEEP")
    return [r for r in rows if _compare(r[col], op, value)]


def cmd_toss(args: str, rows, lineno: int):
    if not rows:
        _fail(lineno, "TOSS requires data. Use LOAD first.")
    parts = _tokenize_filter(args, lineno)
    if len(parts) < 3:
        _fail(lineno, "TOSS syntax: TOSS column op value")
    col, op, value = parts[0], parts[1], parts[2]
    _validate_filter(col, op, value, rows, lineno, "TOSS")
    return [r for r in rows if not _compare(r[col], op, value)]


def _tokenize_filter(args: str, lineno: int):
    """Split filter args, handling quoted values: col op "quoted value" or col op value."""
    args = args.strip()
    # Try: col op "quoted value"
    m = re.match(r'(\S+)\s+(\S+)\s+"([^"]*)"', args)
    if m:
        return [m.group(1), m.group(2), m.group(3)]
    # Fallback: col op value (unquoted)
    return args.split(None, 2)


def _validate_filter(col, op, value, rows, lineno, cmd_name):
    _check_col(col, rows, lineno)
    if op in SYMBOL_OPS:
        _fail(lineno, f"{cmd_name} requires word operator (eq/neq/gt/lt/gte/lte), got '{op}'")
    if op not in VALID_OPS:
        _fail(lineno, f"{cmd_name} unknown operator '{op}'. Valid: eq, neq, gt, lt, gte, lte")


def cmd_tally(args: str, rows, lineno: int):
    if not rows:
        _fail(lineno, "TALLY requires data. Use LOAD first.")
    m = re.match(r'(\S+)\s*->\s*(.*)', args)
    if not m:
        _fail(lineno, "TALLY syntax: TALLY group_col -> alias=func(agg_col). Got invalid format.")
    group_col = m.group(1)
    agg_str = m.group(2).strip()
    _check_col(group_col, rows, lineno)

    agg_specs = []
    for part in agg_str.split(","):
        part = part.strip()
        if not part:
            continue
        am = re.match(r'(\w+)\s*=\s*(\w+)\((\w+)\)', part)
        if not am:
            _fail(lineno, "TALLY syntax: TALLY group_col -> alias=func(agg_col). Got invalid format.")
        # Detect unparsed trailing text (e.g. missing comma between specs)
        remainder = part[am.end():].strip()
        if remainder:
            _fail(lineno, f"TALLY: unexpected text after '{am.group(0)}': '{remainder}'. "
                  f"Separate multiple aggregations with commas, e.g.: "
                  f"TALLY {group_col} -> a=sum(x), b=count(y)")
        alias, func, agg_col = am.group(1), am.group(2), am.group(3)
        if func != func.lower():
            _fail(lineno, f"Unknown function '{func}'. Use lowercase: {func.lower()}")
        if func not in AGG_FUNCS:
            _fail(lineno, f"Unknown function '{func}'. Available: sum, count, avg, min, max")
        _check_col(agg_col, rows, lineno)
        agg_specs.append((alias, func, agg_col))

    groups = {}
    for r in rows:
        key = r[group_col]
        groups.setdefault(key, []).append(r)

    result = []
    for key, group_rows in groups.items():
        out = {group_col: key}
        for alias, func, agg_col in agg_specs:
            vals = [_try_float(r[agg_col]) for r in group_rows]
            numeric = [v for v in vals if isinstance(v, float)]
            if func == "count":
                out[alias] = str(len(vals))
            elif func == "sum":
                out[alias] = str(sum(numeric))
            elif func == "avg":
                out[alias] = str(sum(numeric) / len(numeric)) if numeric else "0"
            elif func == "min":
                out[alias] = str(min(numeric)) if numeric else ""
            elif func == "max":
                out[alias] = str(max(numeric)) if numeric else ""
        result.append(out)
    return result


def cmd_rank(args: str, rows, lineno: int):
    if not rows:
        _fail(lineno, "RANK requires data. Use LOAD first.")
    parts = args.strip().split()
    if len(parts) < 2:
        _fail(lineno, "RANK syntax: RANK column asc|desc")
    col, direction = parts[0], parts[1].lower()
    _check_col(col, rows, lineno)
    if direction not in ("asc", "desc"):
        _fail(lineno, f"RANK direction must be 'asc' or 'desc', got '{parts[1]}'")
    reverse = direction == "desc"
    return sorted(rows, key=lambda r: _try_float(r[col]), reverse=reverse)


def cmd_pick(args: str, rows, lineno: int):
    if not rows:
        _fail(lineno, "PICK requires data. Use LOAD first.")
    cols = [c.strip() for c in args.split(",")]
    for c in cols:
        _check_col(c, rows, lineno)
    return [{c: r[c] for c in cols} for r in rows]


def cmd_derive(args: str, rows, lineno: int):
    if not rows:
        _fail(lineno, "DERIVE requires data. Use LOAD first.")
    m = re.match(r'(\w+)\s*=\s*(.*)', args)
    if not m:
        _fail(lineno, "DERIVE syntax: DERIVE new_col = expression")
    new_col = m.group(1)
    expr = m.group(2).strip()
    tokens = re.findall(r'[\w.]+|[+\-*/]', expr)
    if not tokens:
        _fail(lineno, "DERIVE expression is empty.")

    available = _available_cols(rows)
    result = []
    for r in rows:
        resolved = []
        for t in tokens:
            if t in ("+", "-", "*", "/"):
                resolved.append(t)
            elif t in available:
                resolved.append(str(_try_float(r[t])))
            else:
                try:
                    float(t)
                    resolved.append(t)
                except ValueError:
                    _fail(lineno, f"Column '{t}' not found. Available: {', '.join(available)}")
        try:
            val = eval(" ".join(resolved))  # safe: only numbers and +-*/
        except ZeroDivisionError:
            val = 0
        except Exception as e:
            _fail(lineno, f"DERIVE evaluation error: {e}")
        new_row = dict(r)
        new_row[new_col] = str(val)
        result.append(new_row)
    return result


def cmd_merge(args: str, rows, workdir: str, lineno: int):
    if not rows:
        _fail(lineno, "MERGE requires data. Use LOAD first.")
    path, rest = _parse_quoted(args)
    if path is None:
        _fail(lineno, 'MERGE path must be quoted. Use: MERGE "file.csv" ON column')
    m = re.match(r'\s*ON\s+(\w+)', rest, re.IGNORECASE)
    if not m:
        _fail(lineno, 'MERGE syntax: MERGE "file.csv" ON column')
    join_col = m.group(1)
    _check_col(join_col, rows, lineno)

    filepath = os.path.join(workdir, path)
    if not os.path.isfile(filepath):
        _fail(lineno, f'File not found: "{path}" (resolved to {filepath})')
    with open(filepath, newline="", encoding="utf-8") as f:
        right_rows = list(csv.DictReader(f))

    if not right_rows:
        return rows

    right_index = {}
    for rr in right_rows:
        if join_col not in rr:
            _fail(lineno, f"Column '{join_col}' not found in '{path}'. Available: {', '.join(right_rows[0].keys())}")
        right_index.setdefault(rr[join_col], []).append(rr)

    result = []
    for lr in rows:
        for rr in right_index.get(lr[join_col], []):
            merged = dict(lr)
            for k, v in rr.items():
                if k != join_col:
                    merged[k] = v
            result.append(merged)
    return result


def cmd_show(args: str, rows, lineno: int):
    if not rows:
        print("(empty)", file=sys.stdout)
        return
    limit = None
    args = args.strip()
    if args:
        try:
            limit = int(args)
        except ValueError:
            _fail(lineno, f"SHOW takes an optional integer (row count), got '{args}'")
    display = rows[:limit] if limit else rows
    cols = list(display[0].keys())
    writer = csv.DictWriter(sys.stdout, fieldnames=cols, lineterminator="\n")
    writer.writeheader()
    writer.writerows(display)


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------

COMMANDS = {"LOAD", "KEEP", "TOSS", "TALLY", "RANK", "PICK", "DERIVE", "MERGE", "SHOW"}


def run(workdir: str, input_stream):
    rows = []
    lines = input_stream.read().splitlines()

    for lineno_0, raw_line in enumerate(lines):
        lineno = lineno_0 + 1
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split(None, 1)
        cmd = parts[0].upper()
        args = parts[1] if len(parts) > 1 else ""

        if cmd not in COMMANDS:
            suggestion = SQL_MISTAKES.get(cmd)
            if suggestion:
                _fail(lineno, f"Unknown command '{cmd}'. Did you mean '{suggestion}'?")
            _fail(lineno, f"Unknown command '{cmd}'. Valid commands: {', '.join(sorted(COMMANDS))}")

        if cmd == "LOAD":
            rows = cmd_load(args, rows, workdir, lineno)
        elif cmd == "KEEP":
            rows = cmd_keep(args, rows, lineno)
        elif cmd == "TOSS":
            rows = cmd_toss(args, rows, lineno)
        elif cmd == "TALLY":
            rows = cmd_tally(args, rows, lineno)
        elif cmd == "RANK":
            rows = cmd_rank(args, rows, lineno)
        elif cmd == "PICK":
            rows = cmd_pick(args, rows, lineno)
        elif cmd == "DERIVE":
            rows = cmd_derive(args, rows, lineno)
        elif cmd == "MERGE":
            rows = cmd_merge(args, rows, workdir, lineno)
        elif cmd == "SHOW":
            cmd_show(args, rows, lineno)


def main():
    global CRYPTIC_MODE, SEMI_HELPFUL_MODE
    parser = argparse.ArgumentParser(description="gridtool: pipeline CSV data processor")
    parser.add_argument("--workdir", required=True, help="Working directory for CSV file resolution")
    parser.add_argument("--cryptic", action="store_true",
                        help="Cryptic error mode: strip helpful hints from error messages")
    parser.add_argument("--semi-helpful", action="store_true",
                        help="Semi-helpful error mode: hint at fixes without giving full syntax")
    args = parser.parse_args()
    CRYPTIC_MODE = args.cryptic
    SEMI_HELPFUL_MODE = args.semi_helpful
    if not os.path.isdir(args.workdir):
        print(f"ERROR: --workdir '{args.workdir}' is not a directory", file=sys.stderr)
        sys.exit(1)
    run(args.workdir, sys.stdin)


if __name__ == "__main__":
    main()
