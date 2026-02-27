from __future__ import annotations

from tracks.cli_sqlite import agent_cli


def test_contract_pattern_to_hint_text_simplifies_common_regex_tokens() -> None:
    raw_pattern = r"(?is)git\s+am\s+\.\./hotfix_gamma\.patch"
    hint = agent_cli._contract_pattern_to_hint_text(raw_pattern)
    assert "git am ../hotfix_gamma.patch" in hint
    assert "(?is)" not in hint
    assert "\\s+" not in hint


def test_build_contract_execution_guidance_from_contract_includes_required_and_forbidden() -> None:
    contract = {
        "signals": {
            "required_event_patterns": [
                r"(?is)git\s+init\s+source_repo",
                r"(?is)git\s+init\s+target_repo",
            ],
            "forbidden_event_patterns": [
                r"(?is)\b/tmp\b",
            ],
        }
    }
    guidance = agent_cli._build_contract_execution_guidance_from_contract(contract=contract)
    assert "Deterministic contract closure checklist" in guidance
    assert "required: git init source_repo" in guidance
    assert "required: git init target_repo" in guidance
    assert "avoid: /tmp" in guidance
    assert "repair and verify before final stop" in guidance


def test_build_contract_execution_guidance_from_contract_empty_when_no_signals() -> None:
    assert agent_cli._build_contract_execution_guidance_from_contract(contract={}) == ""
