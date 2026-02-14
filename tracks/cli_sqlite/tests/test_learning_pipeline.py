#!/usr/bin/env python3
"""End-to-end pipeline test for the learning loop (no API calls required).

Validates:
1. Gridtool error modes (helpful, semi-helpful, cryptic)
2. Lesson quality filter with realistic gridtool lessons
3. Known-wrong pattern filter (poisonous lessons)
4. Lesson storage, dedup, and loading
5. System prompt construction for bootstrap mode
6. Full lesson accumulation simulation

Run directly:  python3 tracks/cli_sqlite/tests/test_learning_pipeline.py
Or via pytest:  python3 -m pytest tracks/cli_sqlite/tests/test_learning_pipeline.py -v
"""
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Make sure imports work
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tracks.cli_sqlite.learning_cli import (
    Lesson,
    _KNOWN_WRONG_PATTERNS,
    _lesson_quality_score,
    filter_lessons,
    load_lessons,
    load_relevant_lessons,
    store_lessons,
)
from tracks.cli_sqlite.domains.gridtool_adapter import GridtoolAdapter, _GRIDTOOL_KEYWORDS

GRIDTOOL_PATH = Path(__file__).resolve().parents[1] / "domains" / "gridtool.py"
FIXTURE_DIR = Path(__file__).resolve().parents[1] / "tasks" / "aggregate_report"

# ── Helpers ──────────────────────────────────────────────────

_passed = 0
_failed = 0


def _check(name: str, condition: bool, detail: str = ""):
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  PASS: {name}")
    else:
        _failed += 1
        print(f"  FAIL: {name} — {detail}")


def _run_gridtool(commands: str, *, semi_helpful: bool = False, cryptic: bool = False) -> tuple[int, str, str]:
    """Run gridtool and return (exit_code, stdout, stderr)."""
    cmd = ["python3", str(GRIDTOOL_PATH), "--workdir", str(FIXTURE_DIR)]
    if semi_helpful:
        cmd.append("--semi-helpful")
    elif cryptic:
        cmd.append("--cryptic")
    result = subprocess.run(cmd, input=commands, capture_output=True, text=True, timeout=5)
    return result.returncode, result.stdout, result.stderr


def _make_lesson(lesson_text: str, *, category: str = "mistake", session_id: int = 9501,
                 eval_passed: bool = False, eval_score: float = 0.0) -> Lesson:
    return Lesson(
        session_id=session_id,
        task_id="aggregate_report",
        task="Load sales data, tally by region, rank, show",
        category=category,
        lesson=lesson_text,
        evidence_steps=[2, 3],
        eval_passed=eval_passed,
        eval_score=eval_score,
        skill_refs_used=[],
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


# ── pytest-compatible test functions ─────────────────────────

def test_gridtool_error_modes():
    """Section 1: Gridtool error modes (helpful, semi-helpful, cryptic)."""
    # Correct syntax
    ec, out, err = _run_gridtool('LOAD "fixture.csv"\nTALLY region -> total=sum(amount), cnt=count(amount)\nRANK total desc\nSHOW')
    assert ec == 0, f"exit={ec} err={err}"
    assert out.count("\n") == 4, f"Expected 4 lines (header + 3 rows), got {out.count(chr(10))}"

    # Unquoted LOAD — all three modes
    _, _, err_h = _run_gridtool('LOAD fixture.csv')
    _, _, err_s = _run_gridtool('LOAD fixture.csv', semi_helpful=True)
    _, _, err_c = _run_gridtool('LOAD fixture.csv', cryptic=True)
    assert 'Use: LOAD' in err_h
    assert 'double quotes' in err_s
    assert 'invalid argument' in err_c

    # TALLY without arrow
    _, _, err_h = _run_gridtool('LOAD "fixture.csv"\nTALLY region total=sum(amount)')
    _, _, err_s = _run_gridtool('LOAD "fixture.csv"\nTALLY region total=sum(amount)', semi_helpful=True)
    _, _, err_c = _run_gridtool('LOAD "fixture.csv"\nTALLY region total=sum(amount)', cryptic=True)
    assert 'TALLY group_col ->' in err_h
    assert "arrow operator '->'" in err_s
    assert err_c.strip() == "ERROR at line 2: TALLY: syntax error."

    # Uppercase function
    _, _, err_h = _run_gridtool('LOAD "fixture.csv"\nTALLY region -> total=SUM(amount)')
    _, _, err_s = _run_gridtool('LOAD "fixture.csv"\nTALLY region -> total=SUM(amount)', semi_helpful=True)
    assert 'lowercase: sum' in err_h
    assert 'case-sensitive' in err_s

    # Missing alias
    _, _, err_s = _run_gridtool('LOAD "fixture.csv"\nTALLY region -> sum(amount)', semi_helpful=True)
    assert "alias name before '='" in err_s

    # Arrow present but bad aggregation format (e.g., SUM amount instead of alias=func(col))
    _, _, err_s = _run_gridtool('LOAD "fixture.csv"\nTALLY region -> SUM amount, COUNT', semi_helpful=True)
    assert 'alias=func(col)' in err_s, f"Bad agg format should mention alias=func(col), got: {err_s}"

    # SQL GROUP BY mistake
    _, _, err_s = _run_gridtool('LOAD "fixture.csv"\nGROUP BY region', semi_helpful=True)
    assert 'not SQL' in err_s


def test_lesson_quality_filter():
    """Section 2: Good gridtool lessons pass, generic advice rejected."""
    good_lessons = [
        "TALLY requires arrow syntax: TALLY col -> alias=func(agg_col). Error at step 2.",
        'LOAD path must be in double quotes: LOAD "file.csv". Error at step 1.',
        "Functions must be lowercase: use sum() not SUM(). Error at step 3.",
        "KEEP/TOSS use word operators (eq, neq, gt, lt, gte, lte), not symbols (=, >, <). Error at step 4.",
        "Multiple TALLY aggregations separated by commas: TALLY col -> a=sum(x), b=count(y). Error at step 3.",
    ]
    bad_lessons = [
        "Always read the skill document before executing commands.",
        "Be careful when writing SQL queries.",
        "Remember to check the documentation.",
        "The agent should pay attention to syntax.",
        "Make sure to read all available resources first.",
    ]
    for text in good_lessons:
        lesson = _make_lesson(text)
        score = _lesson_quality_score(lesson, domain_keywords=_GRIDTOOL_KEYWORDS)
        assert score >= 0.15, f"Good lesson scored too low ({score}): {text[:60]}"

    for text in bad_lessons:
        lesson = _make_lesson(text)
        score = _lesson_quality_score(lesson, domain_keywords=_GRIDTOOL_KEYWORDS)
        assert score < 0.15, f"Bad lesson scored too high ({score}): {text[:60]}"


def test_known_wrong_patterns():
    """Section 3: Poisonous lessons blocked, good ones pass."""
    poisonous = [
        "TALLY only supports one aggregation per call, so use separate TALLY commands for each aggregation.",
        "TALLY does not support multiple aggregations — use one TALLY per aggregation.",
        "TALLY supports a single aggregation only. Use TALLY twice.",
        "Cannot perform multiple aggregations in TALLY.",
        "TALLY syntax does not use arrow operator '->'.",
        "TALLY doesn't use arrow operator.",
        "TALLY does not need -> operator.",
        "read_skill failed with unknown ref 'gridtool'",
        "skill_ref 'aggregate' not found — try looking up available skills",
    ]
    not_poisonous = [
        "TALLY requires arrow syntax: TALLY col -> alias=func(agg_col)",
        "Use comma-separated aggregations: TALLY col -> a=sum(x), b=count(y)",
        "Functions must be lowercase in TALLY: sum, count, avg, min, max",
        'LOAD requires double-quoted path: LOAD "file.csv"',
    ]
    for text in poisonous:
        assert _KNOWN_WRONG_PATTERNS.search(text), f"Should be blocked: {text[:70]}"
    for text in not_poisonous:
        assert not _KNOWN_WRONG_PATTERNS.search(text), f"Should NOT be blocked: {text[:70]}"


def test_lesson_storage_dedup_loading():
    """Section 4: Storage, dedup, and poisonous-lesson filtering at load time."""
    with tempfile.TemporaryDirectory() as tmpdir:
        lessons_path = Path(tmpdir) / "lessons.jsonl"

        batch1 = [
            _make_lesson('LOAD requires quoted path: LOAD "file.csv". Error at step 1.', session_id=9501),
            _make_lesson("TALLY arrow syntax: TALLY col -> alias=func(agg_col). Error at step 2.", session_id=9501),
        ]
        stored1 = store_lessons(path=lessons_path, lessons=batch1)
        assert stored1 == 2

        batch2 = [
            _make_lesson('LOAD requires quoted path: LOAD "file.csv". Error at step 1.', session_id=9502),
            _make_lesson("Functions must be lowercase: sum() not SUM(). Error at step 3.", session_id=9502),
        ]
        stored2 = store_lessons(path=lessons_path, lessons=batch2)
        assert stored2 == 1, f"Expected 1 (dup filtered), got {stored2}"

        loaded = load_lessons(lessons_path)
        assert len(loaded) == 3

        text, count = load_relevant_lessons(
            path=lessons_path, task_id="aggregate_report",
            task="Load sales data, tally by region, rank, show",
        )
        assert count == 3
        assert "CRITICAL lessons" in text

        # Write poisonous lesson directly (bypass filter)
        poisonous_lesson = _make_lesson(
            "TALLY only supports one aggregation per call, use separate TALLY commands.",
            session_id=9503,
        )
        with lessons_path.open("a") as f:
            f.write(json.dumps(poisonous_lesson.to_dict()) + "\n")

        raw_loaded = load_lessons(lessons_path)
        assert len(raw_loaded) == 4

        text2, count2 = load_relevant_lessons(
            path=lessons_path, task_id="aggregate_report",
            task="Load sales data, tally by region, rank, show",
        )
        assert count2 == 3, f"Poisonous lesson not filtered: count={count2}"
        assert "only supports one" not in text2


def test_bootstrap_system_prompt():
    """Section 5: Bootstrap prompt strips read_skill, keeps gridtool info."""
    adapter = GridtoolAdapter(semi_helpful_errors=True)
    fragment = adapter.system_prompt_fragment()

    assert "gridtool CLI" in fragment
    assert "NOT SQL" in fragment
    assert "LOAD" in fragment and "TALLY" in fragment

    # Bootstrap mode strips read_skill instructions
    stripped = re.sub(
        r"- Before starting.*?do not guess or invent skill_ref names\.\n",
        "", fragment, flags=re.DOTALL,
    )
    assert "read_skill" not in stripped
    assert "LOAD" in stripped and "TALLY" in stripped

    # Tool filtering
    tools = adapter.tool_defs(["fixture.csv"], opaque=False)
    assert any(t["name"] == "read_skill" for t in tools)
    bootstrap_tools = [t for t in tools if t["name"] != "read_skill"]
    assert not any(t["name"] == "read_skill" for t in bootstrap_tools)
    assert any(t["name"] == "run_gridtool" for t in bootstrap_tools)
    assert any(t["name"] == "show_fixture" for t in bootstrap_tools)


def test_bootstrap_task_text_cleanup():
    """Section 5b: Bootstrap mode strips read_skill from task text."""
    task_text = (
        "gridtool task: aggregate_report.\n\n"
        "Goal:\n1) Load the sales data from fixture.csv\n"
        "Constraints:\n"
        "- Use only run_gridtool, read_skill, and show_fixture tools.\n"
        "- Read the gridtool skill document before attempting any commands.\n"
        "- gridtool has its own syntax — it is NOT SQL.\n"
    )
    cleaned = re.sub(r"- Read the .*?skill document.*?\n", "", task_text)
    cleaned = re.sub(r",?\s*read_skill,?", "", cleaned)
    assert "read_skill" not in cleaned
    assert "Read the gridtool skill document" not in cleaned
    assert "run_gridtool" in cleaned
    assert "show_fixture" in cleaned
    assert "NOT SQL" in cleaned


def test_lesson_accumulation():
    """Section 6: Lessons accumulate monotonically across sessions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        lessons_path = Path(tmpdir) / "lessons.jsonl"

        store_lessons(path=lessons_path, lessons=[
            _make_lesson('LOAD requires double-quoted path: LOAD "file.csv", not LOAD file.csv. Error at step 1.', session_id=9501, eval_score=0.0),
            _make_lesson("TALLY uses arrow syntax: TALLY group_col -> alias=func(agg_col). Error at step 3.", session_id=9501, eval_score=0.0),
        ])

        _, count_s2 = load_relevant_lessons(path=lessons_path, task_id="aggregate_report", task="Load sales data, tally by region")
        assert count_s2 == 2

        store_lessons(path=lessons_path, lessons=[
            _make_lesson("Functions in TALLY must be lowercase: sum, count, avg, min, max. Got SUM error at step 2.", session_id=9502, eval_score=0.0),
        ])
        _, count_s3 = load_relevant_lessons(path=lessons_path, task_id="aggregate_report", task="Load sales data, tally by region")
        assert count_s3 == 3

        store_lessons(path=lessons_path, lessons=[
            _make_lesson("Multiple TALLY aggregations use commas: TALLY col -> a=sum(x), b=count(y). Error at step 3.", session_id=9503, eval_score=0.25),
        ])
        _, count_s4 = load_relevant_lessons(path=lessons_path, task_id="aggregate_report", task="Load sales data, tally by region")
        assert count_s4 == 4

        store_lessons(path=lessons_path, lessons=[
            _make_lesson("RANK syntax: RANK col asc|desc. Direction must be lowercase word. Successful at step 4.",
                         session_id=9504, eval_score=0.75, eval_passed=False, category="shortcut"),
        ])
        text_s5, count_s5 = load_relevant_lessons(path=lessons_path, task_id="aggregate_report", task="Load sales data, tally by region")
        assert count_s5 == 5

        assert "LOAD" in text_s5 and "quot" in text_s5.lower()
        assert "->" in text_s5
        assert "lowercase" in text_s5.lower()
        assert "comma" in text_s5.lower()
        assert "RANK" in text_s5
        assert count_s2 < count_s3 < count_s4 < count_s5


def test_capture_final_state():
    """Section 7: capture_final_state extracts last successful output from events."""
    from tracks.cli_sqlite.domain_adapter import DomainWorkspace

    with tempfile.TemporaryDirectory() as tmpdir:
        work_dir = Path(tmpdir)
        events_path = work_dir / "events.jsonl"
        events = [
            {"step": 1, "tool": "show_fixture", "ok": True, "output": "region,product,amount..."},
            {"step": 2, "tool": "run_gridtool", "ok": False, "error": "LOAD: invalid argument."},
            {"step": 3, "tool": "run_gridtool", "ok": True, "output": "region,total,cnt\nNorth,4200.0,4\nSouth,3200.0,3\nEast,2750.0,3"},
        ]
        with events_path.open("w") as f:
            for evt in events:
                f.write(json.dumps(evt) + "\n")

        workspace = DomainWorkspace(
            task_id="aggregate_report", task_dir=FIXTURE_DIR,
            work_dir=work_dir, fixture_paths={},
        )
        adapter = GridtoolAdapter()
        state = adapter.capture_final_state(workspace)
        assert "North,4200.0,4" in state
        assert "invalid argument" not in state


# ── Script-mode runner ───────────────────────────────────────

def _run_all_as_script():
    """Run all tests as a standalone script with detailed output."""
    global _passed, _failed
    _passed = 0
    _failed = 0

    print("\n=== 1. Gridtool Error Modes ===")
    # Correct syntax
    ec, out, err = _run_gridtool('LOAD "fixture.csv"\nTALLY region -> total=sum(amount), cnt=count(amount)\nRANK total desc\nSHOW')
    _check("Correct syntax passes", ec == 0, f"exit={ec} err={err}")
    _check("Output has 3 regions", out.count("\n") == 4, f"lines={out.count(chr(10))}")
    ec_h, _, err_h = _run_gridtool('LOAD fixture.csv')
    ec_s, _, err_s = _run_gridtool('LOAD fixture.csv', semi_helpful=True)
    ec_c, _, err_c = _run_gridtool('LOAD fixture.csv', cryptic=True)
    _check("Helpful: LOAD shows Use: LOAD", 'Use: LOAD' in err_h, err_h)
    _check("Semi-helpful: LOAD hints at double quotes", 'double quotes' in err_s, err_s)
    _check("Cryptic: LOAD just says invalid", 'invalid argument' in err_c, err_c)
    _, _, err_h = _run_gridtool('LOAD "fixture.csv"\nTALLY region total=sum(amount)')
    _, _, err_s = _run_gridtool('LOAD "fixture.csv"\nTALLY region total=sum(amount)', semi_helpful=True)
    _, _, err_c = _run_gridtool('LOAD "fixture.csv"\nTALLY region total=sum(amount)', cryptic=True)
    _check("Helpful: TALLY shows full syntax", 'TALLY group_col ->' in err_h, err_h)
    _check("Semi-helpful: TALLY hints at arrow", "arrow operator '->'" in err_s, err_s)
    _check("Cryptic: TALLY just says syntax error", err_c.strip() == "ERROR at line 2: TALLY: syntax error.", err_c)
    _, _, err_h = _run_gridtool('LOAD "fixture.csv"\nTALLY region -> total=SUM(amount)')
    _, _, err_s = _run_gridtool('LOAD "fixture.csv"\nTALLY region -> total=SUM(amount)', semi_helpful=True)
    _check("Helpful: uppercase func shows lowercase fix", 'lowercase: sum' in err_h, err_h)
    _check("Semi-helpful: uppercase func hints case-sensitive", 'case-sensitive' in err_s, err_s)
    _, _, err_s = _run_gridtool('LOAD "fixture.csv"\nTALLY region -> sum(amount)', semi_helpful=True)
    _check("Semi-helpful: missing alias hints at alias name", "alias name before '='" in err_s, err_s)
    _, _, err_s = _run_gridtool('LOAD "fixture.csv"\nGROUP BY region', semi_helpful=True)
    _check("Semi-helpful: GROUP hints not SQL", 'not SQL' in err_s, err_s)

    print("\n=== 2. Lesson Quality Filter ===")
    good = [
        "TALLY requires arrow syntax: TALLY col -> alias=func(agg_col). Error at step 2.",
        'LOAD path must be in double quotes: LOAD "file.csv". Error at step 1.',
        "Functions must be lowercase: use sum() not SUM(). Error at step 3.",
        "KEEP/TOSS use word operators (eq, neq, gt, lt, gte, lte), not symbols (=, >, <). Error at step 4.",
        "Multiple TALLY aggregations separated by commas: TALLY col -> a=sum(x), b=count(y). Error at step 3.",
    ]
    bad = [
        "Always read the skill document before executing commands.",
        "Be careful when writing SQL queries.",
        "Remember to check the documentation.",
        "The agent should pay attention to syntax.",
        "Make sure to read all available resources first.",
    ]
    for t in good:
        score = _lesson_quality_score(_make_lesson(t), domain_keywords=_GRIDTOOL_KEYWORDS)
        _check(f"Good lesson passes (score={score:.2f}): {t[:60]}...", score >= 0.15, f"score={score}")
    for t in bad:
        score = _lesson_quality_score(_make_lesson(t), domain_keywords=_GRIDTOOL_KEYWORDS)
        _check(f"Bad lesson rejected (score={score:.2f}): {t[:60]}...", score < 0.15, f"score={score}")

    print("\n=== 3. Known-Wrong Pattern Filter ===")
    poisonous = [
        "TALLY only supports one aggregation per call, so use separate TALLY commands for each aggregation.",
        "TALLY does not support multiple aggregations — use one TALLY per aggregation.",
        "TALLY supports a single aggregation only. Use TALLY twice.",
        "Cannot perform multiple aggregations in TALLY.",
        "TALLY syntax does not use arrow operator '->'.",
        "TALLY doesn't use arrow operator.",
        "TALLY does not need -> operator.",
        "read_skill failed with unknown ref 'gridtool'",
        "skill_ref 'aggregate' not found — try looking up available skills",
    ]
    not_poisonous = [
        "TALLY requires arrow syntax: TALLY col -> alias=func(agg_col)",
        "Use comma-separated aggregations: TALLY col -> a=sum(x), b=count(y)",
        "Functions must be lowercase in TALLY: sum, count, avg, min, max",
        'LOAD requires double-quoted path: LOAD "file.csv"',
    ]
    for t in poisonous:
        _check(f"Poisonous blocked: {t[:70]}...", bool(_KNOWN_WRONG_PATTERNS.search(t)), t)
    for t in not_poisonous:
        _check(f"Good lesson not blocked: {t[:70]}...", not _KNOWN_WRONG_PATTERNS.search(t), t)

    print("\n=== 4. Lesson Storage & Loading ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        lp = Path(tmpdir) / "lessons.jsonl"
        s1 = store_lessons(path=lp, lessons=[
            _make_lesson('LOAD requires quoted path: LOAD "file.csv". Error at step 1.', session_id=9501),
            _make_lesson("TALLY arrow syntax: TALLY col -> alias=func(agg_col). Error at step 2.", session_id=9501),
        ])
        _check("Batch 1: stored 2 lessons", s1 == 2, f"stored={s1}")
        s2 = store_lessons(path=lp, lessons=[
            _make_lesson('LOAD requires quoted path: LOAD "file.csv". Error at step 1.', session_id=9502),
            _make_lesson("Functions must be lowercase: sum() not SUM(). Error at step 3.", session_id=9502),
        ])
        _check("Batch 2: deduped duplicate, stored 1", s2 == 1, f"stored={s2}")
        loaded = load_lessons(lp)
        _check("Total loaded = 3", len(loaded) == 3, f"loaded={len(loaded)}")
        text, count = load_relevant_lessons(path=lp, task_id="aggregate_report", task="Load sales data, tally by region, rank, show")
        _check("Relevant lessons loaded = 3", count == 3, f"count={count}")
        _check("Lessons text has header", "CRITICAL lessons" in text, text[:100])
        # Bypass filter: write poisonous directly
        pl = _make_lesson("TALLY only supports one aggregation per call, use separate TALLY commands.", session_id=9503)
        with lp.open("a") as f:
            f.write(json.dumps(pl.to_dict()) + "\n")
        raw = load_lessons(lp)
        _check("Raw load includes poisonous lesson", len(raw) == 4, f"raw={len(raw)}")
        text2, count2 = load_relevant_lessons(path=lp, task_id="aggregate_report", task="Load sales data, tally by region, rank, show")
        _check("Relevant load filters poisonous lesson", count2 == 3, f"count={count2}")
        _check("Poisonous text not in output", "only supports one" not in text2, text2[:200])

    print("\n=== 5. Bootstrap System Prompt ===")
    adapter = GridtoolAdapter(semi_helpful_errors=True)
    frag = adapter.system_prompt_fragment()
    _check("Fragment mentions gridtool CLI", "gridtool CLI" in frag, frag[:100])
    _check("Fragment mentions NOT SQL", "NOT SQL" in frag, frag[:200])
    _check("Fragment lists commands", "LOAD" in frag and "TALLY" in frag, frag)
    stripped = re.sub(r"- Before starting.*?do not guess or invent skill_ref names\.\n", "", frag, flags=re.DOTALL)
    _check("Bootstrap strips read_skill instructions", "read_skill" not in stripped, stripped)
    _check("Bootstrap keeps gridtool commands", "LOAD" in stripped and "TALLY" in stripped, stripped)
    tools = adapter.tool_defs(["fixture.csv"], opaque=False)
    _check("Full tools include read_skill", any(t["name"] == "read_skill" for t in tools), str([t["name"] for t in tools]))
    bt = [t for t in tools if t["name"] != "read_skill"]
    _check("Bootstrap tools exclude read_skill", not any(t["name"] == "read_skill" for t in bt), str([t["name"] for t in bt]))
    _check("Bootstrap tools keep run_gridtool", any(t["name"] == "run_gridtool" for t in bt), str([t["name"] for t in bt]))
    _check("Bootstrap tools keep show_fixture", any(t["name"] == "show_fixture" for t in bt), str([t["name"] for t in bt]))

    print("\n=== 5b. Bootstrap Task Text Cleanup ===")
    task_text = (
        "gridtool task: aggregate_report.\n\n"
        "Goal:\n1) Load the sales data from fixture.csv\n"
        "Constraints:\n"
        "- Use only run_gridtool, read_skill, and show_fixture tools.\n"
        "- Read the gridtool skill document before attempting any commands.\n"
        "- gridtool has its own syntax — it is NOT SQL.\n"
    )
    cleaned = re.sub(r"- Read the .*?skill document.*?\n", "", task_text)
    cleaned = re.sub(r",?\s*read_skill,?", "", cleaned)
    _check("Task text strips read_skill", "read_skill" not in cleaned, cleaned)
    _check("Task text strips skill doc instruction", "Read the gridtool skill document" not in cleaned, cleaned)
    _check("Task text keeps run_gridtool", "run_gridtool" in cleaned, cleaned)
    _check("Task text keeps NOT SQL", "NOT SQL" in cleaned, cleaned)

    print("\n=== 6. Lesson Accumulation Simulation ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        lp = Path(tmpdir) / "lessons.jsonl"
        store_lessons(path=lp, lessons=[
            _make_lesson('LOAD requires double-quoted path: LOAD "file.csv", not LOAD file.csv. Error at step 1.', session_id=9501, eval_score=0.0),
            _make_lesson("TALLY uses arrow syntax: TALLY group_col -> alias=func(agg_col). Error at step 3.", session_id=9501, eval_score=0.0),
        ])
        _, c2 = load_relevant_lessons(path=lp, task_id="aggregate_report", task="Load sales data, tally by region")
        _check("Session 2 loads 2 lessons from session 1", c2 == 2, f"count={c2}")
        store_lessons(path=lp, lessons=[
            _make_lesson("Functions in TALLY must be lowercase: sum, count, avg, min, max. Got SUM error at step 2.", session_id=9502, eval_score=0.0),
        ])
        _, c3 = load_relevant_lessons(path=lp, task_id="aggregate_report", task="Load sales data, tally by region")
        _check("Session 3 loads 3 lessons from sessions 1-2", c3 == 3, f"count={c3}")
        store_lessons(path=lp, lessons=[
            _make_lesson("Multiple TALLY aggregations use commas: TALLY col -> a=sum(x), b=count(y). Error at step 3.", session_id=9503, eval_score=0.25),
        ])
        _, c4 = load_relevant_lessons(path=lp, task_id="aggregate_report", task="Load sales data, tally by region")
        _check("Session 4 loads 4 lessons from sessions 1-3", c4 == 4, f"count={c4}")
        store_lessons(path=lp, lessons=[
            _make_lesson("RANK syntax: RANK col asc|desc. Direction must be lowercase word. Successful at step 4.",
                         session_id=9504, eval_score=0.75, eval_passed=False, category="shortcut"),
        ])
        t5, c5 = load_relevant_lessons(path=lp, task_id="aggregate_report", task="Load sales data, tally by region")
        _check("Session 5 loads 5 lessons from sessions 1-4", c5 == 5, f"count={c5}")
        _check("Lessons cover LOAD quoting", 'LOAD' in t5 and 'quot' in t5.lower(), t5[:500])
        _check("Lessons cover TALLY arrow", '->' in t5, t5[:500])
        _check("Lessons cover lowercase functions", 'lowercase' in t5.lower(), t5[:500])
        _check("Lessons cover comma aggregations", 'comma' in t5.lower(), t5[:500])
        _check("Lessons cover RANK", 'RANK' in t5, t5[:500])
        _check("Lesson count grows: 2 -> 3 -> 4 -> 5", c2 < c3 < c4 < c5, f"{c2} -> {c3} -> {c4} -> {c5}")

    print("\n=== 7. capture_final_state ===")
    from tracks.cli_sqlite.domain_adapter import DomainWorkspace
    with tempfile.TemporaryDirectory() as tmpdir:
        wd = Path(tmpdir)
        ep = wd / "events.jsonl"
        events = [
            {"step": 1, "tool": "show_fixture", "ok": True, "output": "region,product,amount..."},
            {"step": 2, "tool": "run_gridtool", "ok": False, "error": "LOAD: invalid argument."},
            {"step": 3, "tool": "run_gridtool", "ok": True, "output": "region,total,cnt\nNorth,4200.0,4\nSouth,3200.0,3\nEast,2750.0,3"},
        ]
        with ep.open("w") as f:
            for evt in events:
                f.write(json.dumps(evt) + "\n")
        ws = DomainWorkspace(task_id="aggregate_report", task_dir=FIXTURE_DIR, work_dir=wd, fixture_paths={})
        state = GridtoolAdapter().capture_final_state(ws)
        _check("Final state contains last successful output", "North,4200.0,4" in state, state[:200])
        _check("Final state doesn't contain error", "invalid argument" not in state, state[:200])

    print(f"\n{'='*60}")
    print(f"  RESULTS: {_passed} passed, {_failed} failed")
    print(f"{'='*60}")
    return _failed


if __name__ == "__main__":
    sys.exit(1 if _run_all_as_script() > 0 else 0)
