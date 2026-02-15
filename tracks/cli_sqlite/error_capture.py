from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal


ErrorChannel = Literal[
    "hard_failure",
    "constraint_failure",
    "progress_signal",
    "efficiency_signal",
]

ERROR_CHANNELS: tuple[str, ...] = (
    "hard_failure",
    "constraint_failure",
    "progress_signal",
    "efficiency_signal",
)


# These placeholders intentionally collapse volatile values (ids, counters, paths)
# into stable markers so equivalent failures map to one fingerprint.
_UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
    flags=re.IGNORECASE,
)
_HEX_RE = re.compile(r"\b0x[0-9a-f]+\b", flags=re.IGNORECASE)
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
_PATH_RE = re.compile(
    r"(?:[a-zA-Z]:\\[^\s]+|(?:~|/)[^\s]+)",
    flags=re.IGNORECASE,
)
_QUOTED_RE = re.compile(r"'[^'\n]*'|\"[^\"\n]*\"")
_NON_TOKEN_RE = re.compile(r"[^a-z0-9_<>\s]+")
_WS_RE = re.compile(r"\s+")


_FINGERPRINT_STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "and",
        "at",
        "by",
        "for",
        "from",
        "in",
        "into",
        "of",
        "on",
        "the",
        "to",
        "with",
    }
)


_TAG_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("surface_cli", re.compile(r"\b(?:cli|usage:|exit code|stderr|stdout|--?[a-z0-9][a-z0-9_-]*)\b", re.IGNORECASE)),
    ("surface_http", re.compile(r"\b(?:http\s*\d{3}|status\s*\d{3}|https?://|api|request)\b", re.IGNORECASE)),
    ("surface_python", re.compile(r"\b(?:traceback|exception|stack trace|python)\b", re.IGNORECASE)),
    ("constraint", re.compile(r"\b(?:constraint|violation|duplicate key|not null|foreign key|unique)\b", re.IGNORECASE)),
    (
        "syntax_error",
        re.compile(
            r"(?:\bsyntax error\b|\bparse error\b|\binvalid syntax\b|\bunexpected token\b|\busage:\b|\bunknown command\b)",
            re.IGNORECASE,
        ),
    ),
    ("timeout", re.compile(r"\b(?:timeout|timed out|deadline exceeded|lock wait timeout)\b", re.IGNORECASE)),
    ("permission", re.compile(r"\b(?:permission denied|access denied|operation not permitted)\b", re.IGNORECASE)),
    ("not_found", re.compile(r"\b(?:not found|no such file|does not exist|missing)\b", re.IGNORECASE)),
    ("auth", re.compile(r"\b(?:unauthorized|forbidden|authentication|invalid token|expired token)\b", re.IGNORECASE)),
    ("rate_limited", re.compile(r"\b(?:rate limit|too many requests|quota exceeded|http 429|status 429)\b", re.IGNORECASE)),
    ("network", re.compile(r"\b(?:connection reset|connection refused|host unreachable|dns|socket)\b", re.IGNORECASE)),
    ("resource", re.compile(r"\b(?:out of memory|oom|resource exhausted|disk full|no space left)\b", re.IGNORECASE)),
    ("retryable", re.compile(r"\b(?:retry|try again|temporarily unavailable|deadlock)\b", re.IGNORECASE)),
    ("progress", re.compile(r"\b(?:passed|satisfied|completed|improved|resolved|success)\b", re.IGNORECASE)),
    ("efficiency", re.compile(r"\b(?:latency|slow|faster|optimized|token budget|step budget|cost)\b", re.IGNORECASE)),
)


def _coerce_text(value: Any) -> str:
    """Convert any structure to deterministic text suitable for normalization."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list, tuple, set)):
        try:
            return json.dumps(value, ensure_ascii=True, sort_keys=True)
        except TypeError:
            return str(value)
    return str(value)


def _strip_variable_literals(text: str) -> str:
    """Replace runtime-specific substrings with stable placeholders."""
    lowered = text.lower()
    lowered = _UUID_RE.sub("<uuid>", lowered)
    lowered = _HEX_RE.sub("<hex>", lowered)
    lowered = _QUOTED_RE.sub("<str>", lowered)
    lowered = _PATH_RE.sub("<path>", lowered)
    lowered = _NUMBER_RE.sub("<num>", lowered)
    return lowered


def _normalize_component(value: Any) -> str:
    """
    Normalize a component into stable tokens.

    The goal is collision-resistant enough for operational triage while still
    grouping semantically equivalent failures that only differ by run-local data.
    """
    text = _strip_variable_literals(_coerce_text(value))
    text = _NON_TOKEN_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    if not text:
        return ""

    tokens = [tok for tok in text.split(" ") if tok and tok not in _FINGERPRINT_STOPWORDS]
    if not tokens:
        return ""

    # Deduplicate only adjacent repeated tokens to avoid turning a signal-rich
    # sequence into a bag-of-words while still suppressing noisy repetition.
    collapsed: list[str] = []
    for token in tokens:
        if not collapsed or collapsed[-1] != token:
            collapsed.append(token)
    return " ".join(collapsed)


def normalize_error_for_fingerprint(error: Any) -> str:
    """Public helper for stable normalization of error payloads."""
    return _normalize_component(error)


def normalize_state_for_fingerprint(state: Any) -> str:
    """Public helper for stable normalization of state payloads."""
    return _normalize_component(state)


def normalize_action_for_fingerprint(action: Any) -> str:
    """Public helper for stable normalization of action payloads."""
    return _normalize_component(action)


def normalize_fingerprint_inputs(*, error: Any, state: Any = "", action: Any = "") -> dict[str, str]:
    """Return normalized components that feed fingerprint construction."""
    return {
        "error": normalize_error_for_fingerprint(error),
        "state": normalize_state_for_fingerprint(state),
        "action": normalize_action_for_fingerprint(action),
    }


def build_error_fingerprint(*, error: Any, state: Any = "", action: Any = "") -> str:
    """Build a deterministic fingerprint from normalized error/state/action."""
    normalized = normalize_fingerprint_inputs(error=error, state=state, action=action)
    # Prefix each section name so future schema expansion cannot accidentally
    # collide with old fingerprints that relied on positional concatenation.
    stable_blob = f"error={normalized['error']}|state={normalized['state']}|action={normalized['action']}"
    digest = hashlib.sha256(stable_blob.encode("ascii", "ignore")).hexdigest()
    return f"ef_{digest[:20]}"


def extract_tags(*, error: Any = "", state: Any = "", action: Any = "", extra_text: Any = "") -> list[str]:
    """
    Extract generic tags from mixed contexts.

    Tags are intentionally broad: they need to support CLI traces today and be
    reusable for non-CLI transports (HTTP/API/services) without a second schema.
    """
    merged = " ".join(
        [
            _coerce_text(error),
            _coerce_text(state),
            _coerce_text(action),
            _coerce_text(extra_text),
        ]
    ).strip()
    haystack = merged.lower()
    tags: set[str] = set()

    for tag, pattern in _TAG_PATTERNS:
        if pattern.search(haystack):
            tags.add(tag)

    if "unknown command" in haystack or "command not found" in haystack:
        tags.add("command_not_found")
    if re.search(r"\bexit code\s*[1-9][0-9]*\b", haystack):
        tags.add("nonzero_exit")
    if re.search(r"\bhttp\s*5\d\d\b|\bstatus\s*5\d\d\b", haystack):
        tags.add("server_error")
    if re.search(r"\bhttp\s*4\d\d\b|\bstatus\s*4\d\d\b", haystack):
        tags.add("client_error")

    if not tags:
        return ["uncategorized"]
    return sorted(tags)


@dataclass(frozen=True)
class ErrorEvent:
    channel: ErrorChannel
    error: str
    state: Any = ""
    action: Any = ""
    tags: tuple[str, ...] = ()
    fingerprint: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        channel = str(self.channel).strip()
        if channel not in ERROR_CHANNELS:
            allowed = ", ".join(ERROR_CHANNELS)
            raise ValueError(f"Unknown error channel: {self.channel!r}. Allowed: {allowed}")
        object.__setattr__(self, "channel", channel)

        # Normalize user-provided tags to a deterministic canonical tuple.
        if self.tags:
            normalized_tags = tuple(sorted({str(tag).strip().lower() for tag in self.tags if str(tag).strip()}))
        else:
            normalized_tags = tuple(extract_tags(error=self.error, state=self.state, action=self.action))
        object.__setattr__(self, "tags", normalized_tags)

        if self.fingerprint:
            stable_fingerprint = str(self.fingerprint).strip()
        else:
            stable_fingerprint = build_error_fingerprint(error=self.error, state=self.state, action=self.action)
        object.__setattr__(self, "fingerprint", stable_fingerprint)

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "error": self.error,
            "state": self.state,
            "action": self.action,
            "tags": list(self.tags),
            "fingerprint": self.fingerprint,
            "metadata": self.metadata,
        }


def event_to_dict(event: ErrorEvent) -> dict[str, Any]:
    """Serialization helper for metrics/event pipelines."""
    return event.to_dict()


def event_to_json(event: ErrorEvent) -> str:
    """Serialize an event as stable ASCII JSON."""
    return json.dumps(event_to_dict(event), ensure_ascii=True, sort_keys=True)


def events_to_jsonl(events: Iterable[ErrorEvent]) -> str:
    """Serialize a sequence of events into JSONL payload text."""
    return "\n".join(event_to_json(event) for event in events)


__all__ = [
    "ERROR_CHANNELS",
    "ErrorChannel",
    "ErrorEvent",
    "build_error_fingerprint",
    "event_to_dict",
    "event_to_json",
    "events_to_jsonl",
    "extract_tags",
    "normalize_action_for_fingerprint",
    "normalize_error_for_fingerprint",
    "normalize_fingerprint_inputs",
    "normalize_state_for_fingerprint",
]
