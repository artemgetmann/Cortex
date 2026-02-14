#!/usr/bin/env python3
"""End-to-end pipeline test for the learning loop (no API calls required).

Validates:
1. Gridtool error modes (helpful, semi-helpful, cryptic)
2. Lesson quality filter with realistic gridtool lessons
3. Known-wrong pattern filter (poisonous lessons)
4. Lesson storage, dedup, and loading
5. System prompt construction for bootstrap mode
6. Full lesson accumulation simulation
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

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        print(f"  FAIL: {name} — {detail}")


def run_gridtool(commands: str, *, semi_helpful: bool = False, cryptic: bool = False) -> tuple[int, str, str]:
    """Run gridtool and return (exit_code, stdout, stderr)."""
    cmd = ["python3", str(GRIDTOOL_PATH), "--workdir", str(FIXTURE_DIR)]
    if semi_helpful:
        cmd.append("--semi-helpful")
    elif cryptic:
        cmd.append("--cryptic")
    result = subprocess.run(cmd, input=commands, capture_output=True, text=True, timeout=5)
    return result.returncode, result.stdout, result.stderr


def make_lesson(lesson_text: str, *, category: str = "mistake", session_id: int = 9501,
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


# ============================================================
# Section 1: Gridtool error modes
# ============================================================
print("\n=== 1. Gridtool Error Modes ===")

# Correct syntax should always work
ec, out, err = run_gridtool('LOAD "fixture.csv"\nTALLY region -> total=sum(amount), cnt=count(amount)\nRANK total desc\nSHOW')
check("Correct syntax passes", ec == 0, f"exit={ec} err={err}")
check("Output has 3 regions", out.count("\n") == 4, f"lines={out.count(chr(10))}")  # header + 3 rows

# Unquoted LOAD — all three modes
ec_h, _, err_h = run_gridtool('LOAD fixture.csv')
ec_s, _, err_s = run_gridtool('LOAD fixture.csv', semi_helpful=True)
ec_c, _, err_c = run_gridtool('LOAD fixture.csv', cryptic=True)
check("Helpful: LOAD shows Use: LOAD", 'Use: LOAD' in err_h, err_h)
check("Semi-helpful: LOAD hints at double quotes", 'double quotes' in err_s, err_s)
check("Cryptic: LOAD just says invalid", 'invalid argument' in err_c, err_c)

# TALLY without arrow
ec_h, _, err_h = run_gridtool('LOAD "fixture.csv"\nTALLY region total=sum(amount)')
ec_s, _, err_s = run_gridtool('LOAD "fixture.csv"\nTALLY region total=sum(amount)', semi_helpful=True)
ec_c, _, err_c = run_gridtool('LOAD "fixture.csv"\nTALLY region total=sum(amount)', cryptic=True)
check("Helpful: TALLY shows full syntax", 'TALLY group_col ->' in err_h, err_h)
check("Semi-helpful: TALLY hints at arrow", "arrow operator '->'" in err_s, err_s)
check("Cryptic: TALLY just says syntax error", err_c.strip() == "ERROR at line 2: TALLY: syntax error.", err_c)

# Uppercase function
ec_h, _, err_h = run_gridtool('LOAD "fixture.csv"\nTALLY region -> total=SUM(amount)')
ec_s, _, err_s = run_gridtool('LOAD "fixture.csv"\nTALLY region -> total=SUM(amount)', semi_helpful=True)
check("Helpful: uppercase func shows lowercase fix", 'lowercase: sum' in err_h, err_h)
check("Semi-helpful: uppercase func hints case-sensitive", 'case-sensitive' in err_s, err_s)

# Missing alias
ec_s, _, err_s = run_gridtool('LOAD "fixture.csv"\nTALLY region -> sum(amount)', semi_helpful=True)
check("Semi-helpful: missing alias hints at alias name", "alias name before '='" in err_s, err_s)

# SQL GROUP BY mistake
ec_s, _, err_s = run_gridtool('LOAD "fixture.csv"\nGROUP BY region', semi_helpful=True)
check("Semi-helpful: GROUP hints not SQL", 'not SQL' in err_s, err_s)


# ============================================================
# Section 2: Lesson quality filter
# ============================================================
print("\n=== 2. Lesson Quality Filter ===")

good_lessons = [
    "TALLY requires arrow syntax: TALLY col -> alias=func(agg_col). Error at step 2.",
    "LOAD path must be in double quotes: LOAD \"file.csv\". Error at step 1.",
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

for lesson_text in good_lessons:
    lesson = make_lesson(lesson_text)
    score = _lesson_quality_score(lesson, domain_keywords=_GRIDTOOL_KEYWORDS)
    check(f"Good lesson passes (score={score:.2f}): {lesson_text[:60]}...", score >= 0.15, f"score={score}")

for lesson_text in bad_lessons:
    lesson = make_lesson(lesson_text)
    score = _lesson_quality_score(lesson, domain_keywords=_GRIDTOOL_KEYWORDS)
    check(f"Bad lesson rejected (score={score:.2f}): {lesson_text[:60]}...", score < 0.15, f"score={score}")


# ============================================================
# Section 3: Known-wrong pattern filter
# ============================================================
print("\n=== 3. Known-Wrong Pattern Filter ===")

poisonous = [
    "TALLY only supports one aggregation per call, so use separate TALLY commands for each aggregation.",
    "TALLY does not support multiple aggregations — use one TALLY per aggregation.",
    "TALLY supports a single aggregation only. Use TALLY twice.",
    "Cannot perform multiple aggregations in TALLY.",
    "read_skill failed with unknown ref 'gridtool'",
    "skill_ref 'aggregate' not found — try looking up available skills",
]

not_poisonous = [
    "TALLY requires arrow syntax: TALLY col -> alias=func(agg_col)",
    "Use comma-separated aggregations: TALLY col -> a=sum(x), b=count(y)",
    "Functions must be lowercase in TALLY: sum, count, avg, min, max",
    "LOAD requires double-quoted path: LOAD \"file.csv\"",
]

for text in poisonous:
    check(f"Poisonous blocked: {text[:70]}...", bool(_KNOWN_WRONG_PATTERNS.search(text)), text)

for text in not_poisonous:
    check(f"Good lesson not blocked: {text[:70]}...", not _KNOWN_WRONG_PATTERNS.search(text), text)


# ============================================================
# Section 4: Lesson storage, dedup, and loading
# ============================================================
print("\n=== 4. Lesson Storage & Loading ===")

with tempfile.TemporaryDirectory() as tmpdir:
    lessons_path = Path(tmpdir) / "lessons.jsonl"

    # Store initial lessons
    lessons_batch1 = [
        make_lesson("LOAD requires quoted path: LOAD \"file.csv\". Error at step 1.", session_id=9501),
        make_lesson("TALLY arrow syntax: TALLY col -> alias=func(agg_col). Error at step 2.", session_id=9501),
    ]
    stored1 = store_lessons(path=lessons_path, lessons=lessons_batch1)
    check("Batch 1: stored 2 lessons", stored1 == 2, f"stored={stored1}")

    # Store duplicate — should be deduped
    lessons_batch2 = [
        make_lesson("LOAD requires quoted path: LOAD \"file.csv\". Error at step 1.", session_id=9502),
        make_lesson("Functions must be lowercase: sum() not SUM(). Error at step 3.", session_id=9502),
    ]
    stored2 = store_lessons(path=lessons_path, lessons=lessons_batch2)
    check("Batch 2: deduped duplicate, stored 1", stored2 == 1, f"stored={stored2}")

    # Load and verify
    loaded = load_lessons(lessons_path)
    check("Total loaded = 3", len(loaded) == 3, f"loaded={len(loaded)}")

    # Load relevant lessons
    text, count = load_relevant_lessons(
        path=lessons_path,
        task_id="aggregate_report",
        task="Load sales data, tally by region, rank, show",
    )
    check("Relevant lessons loaded = 3", count == 3, f"count={count}")
    check("Lessons text has header", "CRITICAL lessons" in text, text[:100])

    # Store a poisonous lesson — should be stored but filtered at load time
    poisonous_lesson = make_lesson(
        "TALLY only supports one aggregation per call, use separate TALLY commands.",
        session_id=9503,
    )
    # Bypass filter_lessons by writing directly
    with lessons_path.open("a") as f:
        f.write(json.dumps(poisonous_lesson.to_dict()) + "\n")

    raw_loaded = load_lessons(lessons_path)
    check("Raw load includes poisonous lesson", len(raw_loaded) == 4, f"raw={len(raw_loaded)}")

    text2, count2 = load_relevant_lessons(
        path=lessons_path,
        task_id="aggregate_report",
        task="Load sales data, tally by region, rank, show",
    )
    check("Relevant load filters poisonous lesson", count2 == 3, f"count={count2}")
    check("Poisonous text not in output", "only supports one" not in text2, text2[:200])


# ============================================================
# Section 5: Bootstrap system prompt construction
# ============================================================
print("\n=== 5. Bootstrap System Prompt ===")

adapter = GridtoolAdapter(semi_helpful_errors=True)
fragment = adapter.system_prompt_fragment()

# Verify the fragment contains expected content
check("Fragment mentions gridtool CLI", "gridtool CLI" in fragment, fragment[:100])
check("Fragment mentions NOT SQL", "NOT SQL" in fragment, fragment[:200])
check("Fragment lists commands", "LOAD" in fragment and "TALLY" in fragment, fragment)

# Simulate bootstrap mode: strip read_skill instructions
stripped = re.sub(
    r"- Before starting.*?do not guess or invent skill_ref names\.\n",
    "",
    fragment,
    flags=re.DOTALL,
)
check("Bootstrap strips read_skill instructions", "read_skill" not in stripped, stripped)
check("Bootstrap keeps gridtool commands", "LOAD" in stripped and "TALLY" in stripped, stripped)

# Verify tool filtering
tools = adapter.tool_defs(["fixture.csv"], opaque=False)
check("Full tools include read_skill", any(t["name"] == "read_skill" for t in tools), str([t["name"] for t in tools]))
bootstrap_tools = [t for t in tools if t["name"] != "read_skill"]
check("Bootstrap tools exclude read_skill", not any(t["name"] == "read_skill" for t in bootstrap_tools), str([t["name"] for t in bootstrap_tools]))
check("Bootstrap tools keep run_gridtool", any(t["name"] == "run_gridtool" for t in bootstrap_tools), str([t["name"] for t in bootstrap_tools]))
check("Bootstrap tools keep show_fixture", any(t["name"] == "show_fixture" for t in bootstrap_tools), str([t["name"] for t in bootstrap_tools]))


# ============================================================
# Section 6: Lesson accumulation simulation
# ============================================================
print("\n=== 6. Lesson Accumulation Simulation ===")

# Simulate what should happen across 5 sessions:
# Each session "discovers" some syntax, lessons accumulate, later sessions have more lessons
with tempfile.TemporaryDirectory() as tmpdir:
    lessons_path = Path(tmpdir) / "lessons.jsonl"

    # Session 1: discovers LOAD quoting and TALLY arrow
    session1_lessons = [
        make_lesson(
            'LOAD requires double-quoted path: LOAD "file.csv", not LOAD file.csv. Error at step 1.',
            session_id=9501, eval_score=0.0,
        ),
        make_lesson(
            "TALLY uses arrow syntax: TALLY group_col -> alias=func(agg_col). Error at step 3.",
            session_id=9501, eval_score=0.0,
        ),
    ]
    store_lessons(path=lessons_path, lessons=session1_lessons)

    # Session 2 loads 2 lessons, discovers lowercase functions
    _, count_s2 = load_relevant_lessons(path=lessons_path, task_id="aggregate_report",
                                         task="Load sales data, tally by region")
    check("Session 2 loads 2 lessons from session 1", count_s2 == 2, f"count={count_s2}")

    session2_lessons = [
        make_lesson(
            "Functions in TALLY must be lowercase: sum, count, avg, min, max. Got SUM error at step 2.",
            session_id=9502, eval_score=0.0,
        ),
    ]
    store_lessons(path=lessons_path, lessons=session2_lessons)

    # Session 3 loads 3 lessons, discovers comma-separated aggregations
    _, count_s3 = load_relevant_lessons(path=lessons_path, task_id="aggregate_report",
                                         task="Load sales data, tally by region")
    check("Session 3 loads 3 lessons from sessions 1-2", count_s3 == 3, f"count={count_s3}")

    session3_lessons = [
        make_lesson(
            "Multiple TALLY aggregations use commas: TALLY col -> a=sum(x), b=count(y). Error at step 3.",
            session_id=9503, eval_score=0.25,
        ),
    ]
    store_lessons(path=lessons_path, lessons=session3_lessons)

    # Session 4 loads 4 lessons, discovers RANK syntax
    _, count_s4 = load_relevant_lessons(path=lessons_path, task_id="aggregate_report",
                                         task="Load sales data, tally by region")
    check("Session 4 loads 4 lessons from sessions 1-3", count_s4 == 4, f"count={count_s4}")

    session4_lessons = [
        make_lesson(
            "RANK syntax: RANK col asc|desc. Direction must be lowercase word. Successful at step 4.",
            session_id=9504, eval_score=0.75, eval_passed=False, category="shortcut",
        ),
    ]
    store_lessons(path=lessons_path, lessons=session4_lessons)

    # Session 5 loads 5 lessons — should have enough to pass
    text_s5, count_s5 = load_relevant_lessons(path=lessons_path, task_id="aggregate_report",
                                               task="Load sales data, tally by region")
    check("Session 5 loads 5 lessons from sessions 1-4", count_s5 == 5, f"count={count_s5}")

    # Verify all key syntax patterns are present in loaded lessons
    check("Lessons cover LOAD quoting", 'LOAD' in text_s5 and 'quot' in text_s5.lower(), text_s5[:500])
    check("Lessons cover TALLY arrow", '->' in text_s5, text_s5[:500])
    check("Lessons cover lowercase functions", 'lowercase' in text_s5.lower(), text_s5[:500])
    check("Lessons cover comma aggregations", 'comma' in text_s5.lower(), text_s5[:500])
    check("Lessons cover RANK", 'RANK' in text_s5, text_s5[:500])

    # Verify lesson count grows monotonically
    check("Lesson count grows: 2 -> 3 -> 4 -> 5",
          count_s2 < count_s3 < count_s4 < count_s5,
          f"{count_s2} -> {count_s3} -> {count_s4} -> {count_s5}")


# ============================================================
# Section 7: capture_final_state from events
# ============================================================
print("\n=== 7. capture_final_state ===")

with tempfile.TemporaryDirectory() as tmpdir:
    work_dir = Path(tmpdir)
    events_path = work_dir / "events.jsonl"

    # Write some events including a successful gridtool output
    events = [
        {"step": 1, "tool": "show_fixture", "ok": True, "output": "region,product,amount..."},
        {"step": 2, "tool": "run_gridtool", "ok": False, "error": "LOAD: invalid argument."},
        {"step": 3, "tool": "run_gridtool", "ok": True, "output": "region,total,cnt\nNorth,4200.0,4\nSouth,3200.0,3\nEast,2750.0,3"},
    ]
    with events_path.open("w") as f:
        for evt in events:
            f.write(json.dumps(evt) + "\n")

    from tracks.cli_sqlite.domain_adapter import DomainWorkspace
    workspace = DomainWorkspace(
        task_id="aggregate_report",
        task_dir=FIXTURE_DIR,
        work_dir=work_dir,
        fixture_paths={},
    )

    adapter = GridtoolAdapter()
    state = adapter.capture_final_state(workspace)
    check("Final state contains last successful output", "North,4200.0,4" in state, state[:200])
    check("Final state doesn't contain error", "invalid argument" not in state, state[:200])


# ============================================================
# Summary
# ============================================================
print(f"\n{'='*60}")
print(f"  RESULTS: {passed} passed, {failed} failed")
print(f"{'='*60}")

sys.exit(1 if failed > 0 else 0)
