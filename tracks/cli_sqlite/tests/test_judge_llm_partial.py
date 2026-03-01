from __future__ import annotations

from tracks.cli_sqlite.judge_llm import _extract_partial_json_fields


def test_extract_partial_json_fields_recovers_truncated_payload() -> None:
    raw = (
        '{"passed": true, "score": 0.75, "reasons": '
        '["Deduplicated by event_id.", "Rejects captured."]'
    )
    parsed = _extract_partial_json_fields(raw)
    assert parsed is not None
    assert parsed["passed"] is True
    assert parsed["score"] == 0.75
    assert parsed["reasons"] == ["Deduplicated by event_id.", "Rejects captured."]


def test_extract_partial_json_fields_returns_none_without_fields() -> None:
    assert _extract_partial_json_fields("just normal text") is None


def test_extract_partial_json_fields_ignores_sibling_keys_after_reasons() -> None:
    raw = (
        '{"passed": true, "score": 1.0, "reasons": '
        '["rows match expected", "duplicates tracked"], '
        '"doc_grounding": [{"source_id":"step_4","note":"used"}]'
    )
    parsed = _extract_partial_json_fields(raw)
    assert parsed is not None
    assert parsed["reasons"] == ["rows match expected", "duplicates tracked"]
