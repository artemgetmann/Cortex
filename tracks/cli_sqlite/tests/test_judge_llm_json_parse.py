from __future__ import annotations

from tracks.cli_sqlite.judge_llm import _extract_json_object


def test_extract_json_object_parses_plain_json() -> None:
    raw = '{"passed": true, "score": 1.0, "reasons": ["ok"], "doc_grounding": []}'
    obj = _extract_json_object(raw)
    assert obj is not None
    assert obj.get("passed") is True
    assert float(obj.get("score", 0.0)) == 1.0


def test_extract_json_object_parses_fenced_json() -> None:
    raw = """
    analysis text
    ```json
    {"passed": false, "score": 0.25, "reasons": ["missing step"], "doc_grounding": []}
    ```
    """
    obj = _extract_json_object(raw)
    assert obj is not None
    assert obj.get("passed") is False
    assert float(obj.get("score", 0.0)) == 0.25


def test_extract_json_object_parses_balanced_object_inside_markdown() -> None:
    raw = """
    # Evaluation
    Notes: use evidence {not json}
    Result payload:
    {"passed": true, "score": 0.75, "reasons": ["mostly complete"], "doc_grounding": []}
    """
    obj = _extract_json_object(raw)
    assert obj is not None
    assert obj.get("passed") is True
    assert float(obj.get("score", 0.0)) == 0.75
