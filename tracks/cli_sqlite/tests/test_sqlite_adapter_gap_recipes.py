from __future__ import annotations

from tracks.cli_sqlite.domains.sqlite_adapter import SqliteAdapter


def test_incremental_reconcile_required_query_mismatch_uses_forced_recipe() -> None:
    adapter = SqliteAdapter()
    gaps = [
        {
            "reason_code": "required_query_mismatch",
            "gap_type": "required_query",
            "query_id": "reject_count",
            "query_sql": "SELECT COUNT(*) FROM rejects WHERE reason = 'duplicate_event';",
            "expected_rows": [["1"]],
        }
    ]
    recipes = adapter.deterministic_gap_recipes(
        task_id="incremental_reconcile",
        unresolved_gaps=gaps,
        max_items=3,
    )
    assert recipes
    assert recipes[0].startswith("[forced_repair sqlite_incremental_required_query_mismatch_v1]")
    assert "step1=run_sqlite(" in recipes[0]
    assert "step2=run_sqlite(" in recipes[0]
    assert "step3=if_mismatch_stop_and_report" in recipes[0]
    assert "INSERT INTO ledger(" in recipes[0]
    assert "INSERT OR IGNORE INTO ledger(" not in recipes[0]


def test_non_incremental_required_query_mismatch_falls_back_to_generic_recipe() -> None:
    adapter = SqliteAdapter()
    gaps = [
        {
            "reason_code": "required_query_mismatch",
            "gap_type": "required_query",
            "query_id": "ledger_aggregate",
            "query_sql": "SELECT category, SUM(amount) FROM ledger GROUP BY category;",
            "expected_rows": [["drums", "13"]],
        }
    ]
    recipes = adapter.deterministic_gap_recipes(
        task_id="aggregate_report",
        unresolved_gaps=gaps,
        max_items=3,
    )
    assert recipes
    assert "[forced_repair sqlite_incremental_required_query_mismatch_v1]" not in recipes[0]
    assert "Deterministic sqlite recipe (ledger)" in recipes[0]


def test_incremental_reconcile_missing_pattern_uses_executable_closure_recipe() -> None:
    adapter = SqliteAdapter()
    gaps = [
        {
            "reason_code": "missing_required_pattern",
            "gap_type": "required_sql_pattern",
            "detail": "(?is)insert\\s+into\\s+ledger",
        }
    ]
    recipes = adapter.deterministic_gap_recipes(
        task_id="incremental_reconcile",
        unresolved_gaps=gaps,
        max_items=3,
    )
    assert recipes
    assert recipes[0].startswith("[forced_repair sqlite_incremental_closure_v1]")
    assert "step1=run_sqlite(" in recipes[0]
    assert "step2=run_sqlite(" in recipes[0]
    assert "INSERT INTO ledger(" in recipes[0]


def test_incremental_reconcile_prioritizes_query_mismatch_recipe_first() -> None:
    adapter = SqliteAdapter()
    gaps = [
        {
            "reason_code": "missing_required_pattern",
            "gap_type": "required_sql_pattern",
            "detail": "(?is)begin\\s+(transaction|immediate)",
        },
        {
            "reason_code": "required_query_mismatch",
            "gap_type": "required_query",
            "query_id": "reject_count",
            "query_sql": "SELECT COUNT(*) FROM rejects WHERE reason = 'duplicate_event';",
            "expected_rows": [["1"]],
        },
    ]
    recipes = adapter.deterministic_gap_recipes(
        task_id="incremental_reconcile",
        unresolved_gaps=gaps,
        max_items=1,
    )
    assert recipes
    assert recipes[0].startswith("[forced_repair sqlite_incremental_required_query_mismatch_v1]")
