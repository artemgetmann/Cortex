from __future__ import annotations

import csv
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
import re


DOT_COMMAND_RE = re.compile(r"(?m)^\s*(\.[a-zA-Z]+)\b(.*)$")
SHELL_ESCAPE_RE = re.compile(r"(?m)^\s*![^\n]*$")
FORBIDDEN_DOT_COMMANDS = {".shell", ".system"}


@dataclass(frozen=True)
class SqliteExecResult:
    ok: bool
    output: str
    error: str | None
    elapsed_s: float
    returncode: int | None = None


@dataclass(frozen=True)
class TaskWorkspace:
    task_id: str
    task_dir: Path
    db_path: Path
    fixture_paths: dict[str, Path]


def _normalize(path: Path) -> Path:
    return path.resolve()


def _is_allowed_read_path(raw_path: str, *, workdir: Path, allowlist: set[Path]) -> bool:
    candidate = Path(raw_path.strip().strip('"').strip("'"))
    if not candidate.is_absolute():
        candidate = _normalize(workdir / candidate)
    else:
        candidate = _normalize(candidate)
    return candidate in allowlist


def validate_sql_safety(
    sql: str,
    *,
    workdir: Path,
    allowed_read_paths: set[Path],
) -> str | None:
    text = sql.strip()
    if not text:
        return "SQL is empty."
    if SHELL_ESCAPE_RE.search(text):
        return "Shell escapes are forbidden in run_sqlite."

    for match in DOT_COMMAND_RE.finditer(text):
        cmd = match.group(1).strip().lower()
        rest = match.group(2).strip()
        if cmd in FORBIDDEN_DOT_COMMANDS:
            return f"Forbidden sqlite dot-command: {cmd}"
        if cmd == ".read":
            if not rest:
                return ".read requires a path argument."
            if not _is_allowed_read_path(rest, workdir=workdir, allowlist=allowed_read_paths):
                return f".read path is not allowlisted: {rest!r}"
            continue
        return f"Unsupported sqlite dot-command: {cmd}"

    return None


def run_sqlite(
    *,
    db_path: Path,
    sql: str,
    timeout_s: float = 5.0,
    allowed_read_paths: set[Path] | None = None,
) -> SqliteExecResult:
    started = time.time()
    workdir = db_path.parent.resolve()
    allowlist = {p.resolve() for p in (allowed_read_paths or set())}
    safety_error = validate_sql_safety(sql, workdir=workdir, allowed_read_paths=allowlist)
    if safety_error:
        return SqliteExecResult(
            ok=False,
            output="",
            error=safety_error,
            elapsed_s=round(time.time() - started, 4),
            returncode=None,
        )

    try:
        completed = subprocess.run(
            ["sqlite3", "-batch", "-noheader", "-csv", str(db_path)],
            input=sql,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            cwd=str(workdir),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return SqliteExecResult(
            ok=False,
            output="",
            error=f"sqlite3 timed out after {timeout_s:.1f}s",
            elapsed_s=round(time.time() - started, 4),
            returncode=None,
        )
    except FileNotFoundError:
        return SqliteExecResult(
            ok=False,
            output="",
            error="sqlite3 binary not found in PATH.",
            elapsed_s=round(time.time() - started, 4),
            returncode=None,
        )
    except Exception as exc:
        return SqliteExecResult(
            ok=False,
            output="",
            error=f"sqlite3 execution failed: {type(exc).__name__}: {exc}",
            elapsed_s=round(time.time() - started, 4),
            returncode=None,
        )

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    ok = completed.returncode == 0
    err = None if ok else (stderr or f"sqlite3 exited with code {completed.returncode}")
    output = stdout if stdout else (stderr if ok and stderr else "")
    return SqliteExecResult(
        ok=ok,
        output=output,
        error=err,
        elapsed_s=round(time.time() - started, 4),
        returncode=completed.returncode,
    )


def _execute_bootstrap_sql(db_path: Path, bootstrap_sql_path: Path) -> None:
    if not bootstrap_sql_path.exists():
        return
    sql = bootstrap_sql_path.read_text(encoding="utf-8")
    result = run_sqlite(
        db_path=db_path,
        sql=sql,
        timeout_s=5.0,
        allowed_read_paths={bootstrap_sql_path.resolve()},
    )
    if not result.ok:
        raise RuntimeError(f"Failed to execute bootstrap SQL: {result.error}")


def _load_fixture_into_seed_table(db_path: Path, fixture_csv_path: Path) -> None:
    if not fixture_csv_path.exists():
        return
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fixture_seed (
                category TEXT NOT NULL,
                amount INTEGER NOT NULL
            )
            """
        )
        conn.execute("DELETE FROM fixture_seed")
        with fixture_csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            rows: list[tuple[str, int]] = []
            for row in reader:
                category = str(row.get("category", "")).strip()
                amount_raw = str(row.get("amount", "0")).strip()
                if not category:
                    continue
                try:
                    amount = int(amount_raw)
                except ValueError:
                    continue
                rows.append((category, amount))
            if rows:
                conn.executemany("INSERT INTO fixture_seed(category, amount) VALUES (?, ?)", rows)
        conn.commit()


def prepare_task_workspace(
    *,
    track_root: Path,
    task_id: str,
    db_path: Path,
) -> TaskWorkspace:
    task_dir = track_root / "tasks" / task_id
    if not task_dir.exists():
        raise FileNotFoundError(f"Unknown task id: {task_id!r} (missing {task_dir})")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    fixture_paths = {
        "fixture.csv": task_dir / "fixture.csv",
        "bootstrap.sql": task_dir / "bootstrap.sql",
    }

    # Bootstrap creates deterministic schema state for each run.
    _execute_bootstrap_sql(db_path, fixture_paths["bootstrap.sql"])

    # Load CSV once into fixture_seed so the model can verify/import from SQL.
    _load_fixture_into_seed_table(db_path, fixture_paths["fixture.csv"])

    return TaskWorkspace(task_id=task_id, task_dir=task_dir, db_path=db_path, fixture_paths=fixture_paths)


def show_fixture_text(*, task_workspace: TaskWorkspace, path_ref: str) -> tuple[str | None, str | None]:
    key = path_ref.strip()
    target = task_workspace.fixture_paths.get(key)
    if target is None:
        return None, f"Unknown path_ref: {path_ref!r}. Allowed: {sorted(task_workspace.fixture_paths.keys())}"
    if not target.exists():
        return None, f"Missing fixture file: {target}"
    try:
        return target.read_text(encoding="utf-8"), None
    except Exception as exc:
        return None, f"Failed reading fixture file {target}: {type(exc).__name__}: {exc}"
