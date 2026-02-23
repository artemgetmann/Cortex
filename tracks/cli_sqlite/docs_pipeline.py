from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tracks.cli_sqlite.domain_adapter import DomainDoc


DOC_MODES = ("none", "lossy", "full")
DOC_RETRIEVAL_MODES = ("off", "auto")


def _tokenize(text: str) -> set[str]:
    normalized = "".join(ch.lower() if ch.isalnum() else " " for ch in str(text))
    return {tok for tok in normalized.split() if tok}


def _jaccard(a: str, b: str) -> float:
    ta = _tokenize(a)
    tb = _tokenize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / float(len(ta | tb))


def _clip_text(text: str, *, max_chars: int) -> str:
    compact = str(text or "").strip()
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3] + "..."


def _doc_tags_match_query(query_tokens: set[str], tags: tuple[str, ...]) -> bool:
    # Domain docs can carry topical tags (e.g., git vs xlsx). In tight budgets,
    # skipping non-overlapping topics prevents unrelated docs from polluting prompts.
    if not tags:
        return True
    tag_tokens = {tag.strip().lower() for tag in tags if tag.strip()}
    if not tag_tokens:
        return True
    if not query_tokens:
        return True
    return bool(tag_tokens & query_tokens)


def normalize_doc_mode(value: str) -> str:
    mode = str(value or "none").strip().lower()
    if mode not in DOC_MODES:
        allowed = ", ".join(DOC_MODES)
        raise ValueError(f"Unknown doc mode: {value!r}. Allowed: {allowed}")
    return mode


def normalize_doc_retrieval_mode(value: str) -> str:
    mode = str(value or "off").strip().lower()
    if mode not in DOC_RETRIEVAL_MODES:
        allowed = ", ".join(DOC_RETRIEVAL_MODES)
        raise ValueError(f"Unknown doc retrieval mode: {value!r}. Allowed: {allowed}")
    return mode


def _strip_html(text: str) -> str:
    no_scripts = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text)
    no_tags = re.sub(r"(?is)<[^>]+>", " ", no_scripts)
    return re.sub(r"\s+", " ", no_tags).strip()


def _read_text_file(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


def _read_text_url(url: str, *, timeout_s: float = 8.0) -> tuple[str | None, str | None]:
    request = urllib.request.Request(
        url=url,
        headers={"User-Agent": "cortex-doc-retriever/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            payload = response.read()
            content_type = str(response.headers.get("Content-Type", "")).lower()
    except urllib.error.URLError as exc:
        return None, f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if not payload:
        return None, "empty_response"
    try:
        text = payload.decode("utf-8", errors="ignore")
    except Exception:
        text = str(payload)
    if "html" in content_type or url.lower().endswith((".html", ".htm")):
        text = _strip_html(text)
    return text, None


def _chunk_text(text: str, *, chunk_chars: int = 900) -> list[str]:
    # Chunk by paragraph-ish units so each chunk stays coherent for retrieval.
    chunks: list[str] = []
    current: list[str] = []
    length = 0
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            if current:
                merged = "\n".join(current).strip()
                if merged:
                    chunks.append(merged)
                current = []
                length = 0
            continue
        if current and length + len(stripped) + 1 > chunk_chars:
            merged = "\n".join(current).strip()
            if merged:
                chunks.append(merged)
            current = [stripped]
            length = len(stripped)
            continue
        current.append(stripped)
        length += len(stripped) + 1
    if current:
        merged = "\n".join(current).strip()
        if merged:
            chunks.append(merged)
    return chunks or [_clip_text(str(text or ""), max_chars=chunk_chars)]


@dataclass(frozen=True)
class RawDoc:
    source_id: str
    source_ref: str
    source_kind: str
    title: str
    text: str
    tags: tuple[str, ...] = ()
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_ref": self.source_ref,
            "source_kind": self.source_kind,
            "title": self.title,
            "text": self.text,
            "tags": list(self.tags),
            "error": self.error,
        }


@dataclass(frozen=True)
class SelectedDocChunk:
    source_id: str
    title: str
    score: float
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "title": self.title,
            "score": round(float(self.score), 4),
            "text": self.text,
        }


@dataclass(frozen=True)
class DocumentationBundle:
    mode: str
    retrieval_mode: str
    budget_tokens: int
    raw_docs: list[RawDoc]
    selected_chunks: list[SelectedDocChunk]
    brief: str
    retriever_model: str | None
    retrieval_query: str
    brief_strategy: str
    load_errors: list[dict[str, str]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "retrieval_mode": self.retrieval_mode,
            "budget_tokens": self.budget_tokens,
            "retriever_model": self.retriever_model,
            "retrieval_query": self.retrieval_query,
            "brief_strategy": self.brief_strategy,
            "load_errors": list(self.load_errors),
            "docs_raw": [doc.to_dict() for doc in self.raw_docs],
            "docs_selected_chunks": [chunk.to_dict() for chunk in self.selected_chunks],
            "docs_brief": self.brief,
        }

    def render_for_prompt(self, *, max_chars: int = 6000) -> str:
        if not self.brief.strip():
            return ""
        parts = [
            (
                "Documentation context\n"
                f"- mode={self.mode}\n"
                f"- retrieval={self.retrieval_mode}\n"
                f"- budget_tokens={self.budget_tokens}\n"
                "Use this as grounding for tool syntax and edge cases:\n"
            ),
            self.brief.strip(),
        ]
        if self.selected_chunks:
            parts.append("\nSource IDs:")
            for chunk in self.selected_chunks[:8]:
                parts.append(f"- {chunk.source_id} ({chunk.title})")
        return _clip_text("\n".join(parts).strip(), max_chars=max_chars)


def _normalize_budget_tokens(value: int) -> int:
    return max(128, int(value or 1200))


def _resolve_local_path(ref: str, *, track_root: Path) -> Path:
    candidate = Path(ref).expanduser()
    if candidate.exists():
        return candidate
    if not candidate.is_absolute():
        cwd_candidate = (Path.cwd() / candidate).resolve()
        if cwd_candidate.exists():
            return cwd_candidate
        track_candidate = (track_root / candidate).resolve()
        if track_candidate.exists():
            return track_candidate
    return candidate


def _collect_explicit_docs(
    *,
    documentation: list[str],
    track_root: Path,
    max_chars_per_doc: int,
) -> list[RawDoc]:
    docs: list[RawDoc] = []
    for idx, raw_ref in enumerate(documentation):
        ref = str(raw_ref or "").strip()
        if not ref:
            continue
        source_id = f"user_doc_{idx+1:02d}"
        if ref.lower().startswith(("http://", "https://")):
            text, err = _read_text_url(ref)
            docs.append(
                RawDoc(
                    source_id=source_id,
                    source_ref=ref,
                    source_kind="url",
                    title=ref,
                    text=_clip_text(text or "", max_chars=max_chars_per_doc),
                    tags=(),
                    error=err,
                )
            )
            continue
        path = _resolve_local_path(ref, track_root=track_root)
        text = _read_text_file(path)
        docs.append(
            RawDoc(
                source_id=source_id,
                source_ref=str(path),
                source_kind="path",
                title=path.name,
                text=_clip_text(text or "", max_chars=max_chars_per_doc),
                tags=(),
                error=None if text is not None else "read_failed_or_missing",
            )
        )
    return docs


def _collect_domain_docs(
    *,
    docs_manifest: list[DomainDoc],
    max_chars_per_doc: int,
) -> list[RawDoc]:
    docs: list[RawDoc] = []
    for item in docs_manifest:
        text = _read_text_file(item.path)
        docs.append(
            RawDoc(
                source_id=item.doc_id,
                source_ref=str(item.path),
                source_kind="domain",
                title=item.title,
                text=_clip_text(text or "", max_chars=max_chars_per_doc),
                tags=getattr(item, "tags", ()) or (),
                error=None if text is not None else "read_failed_or_missing",
            )
        )
    return docs


def _score_chunks(
    *,
    query: str,
    docs: list[RawDoc],
    max_chunks: int,
) -> list[SelectedDocChunk]:
    ranked: list[SelectedDocChunk] = []
    q = query.strip()
    query_tokens = _tokenize(q)
    for doc in docs:
        # Keep chunk ranking task-focused: ignore docs whose tags do not match query tokens.
        if not _doc_tags_match_query(query_tokens, doc.tags):
            continue
        if doc.error or not doc.text.strip():
            continue
        title_bonus = 0.05 if _jaccard(q, doc.title) > 0 else 0.0
        for chunk in _chunk_text(doc.text):
            score = _jaccard(q, chunk) + title_bonus
            if score <= 0:
                continue
            ranked.append(
                SelectedDocChunk(
                    source_id=doc.source_id,
                    title=doc.title,
                    score=score,
                    text=_clip_text(chunk, max_chars=2000),
                )
            )
    ranked.sort(key=lambda row: row.score, reverse=True)
    return ranked[: max(1, int(max_chunks))]


def _fallback_brief(
    *,
    selected_chunks: list[SelectedDocChunk],
    budget_chars: int,
) -> str:
    lines: list[str] = []
    remaining = max(300, budget_chars)
    for chunk in selected_chunks:
        line = f"[{chunk.source_id}] {chunk.text}"
        clipped = _clip_text(line, max_chars=min(remaining, 700))
        if not clipped:
            continue
        lines.append(clipped)
        remaining -= len(clipped) + 1
        if remaining <= 0:
            break
    return "\n".join(lines).strip()


def _distill_with_llm(
    *,
    client: Any,
    model: str,
    task_text: str,
    selected_chunks: list[SelectedDocChunk],
    budget_tokens: int,
) -> str:
    if client is None or not str(model or "").strip() or not selected_chunks:
        return ""
    source_text = "\n\n".join(
        f"[{row.source_id}] {row.title}\n{row.text}" for row in selected_chunks[:12]
    )
    prompt = (
        "Summarize the docs below into an execution brief for a CLI agent.\n"
        "Requirements:\n"
        "- Keep concrete syntax and constraints only.\n"
        "- Prefer command examples over prose.\n"
        "- Include source IDs like [doc_1] in each bullet.\n"
        f"- Keep output under {max(80, int(budget_tokens))} tokens.\n"
        "- Return plain text bullets only.\n\n"
        f"TASK:\n{task_text}\n\n"
        f"DOC CHUNKS:\n{source_text}\n"
    )
    try:
        response = client.messages.create(
            model=model,
            max_tokens=min(1200, max(300, int(budget_tokens) * 2)),
            system="You distill docs into concise execution briefs.",
            messages=[{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        )
    except Exception:
        return ""
    raw = ""
    for block in getattr(response, "content", []):
        data = block.model_dump() if hasattr(block, "model_dump") else block
        if isinstance(data, dict) and str(data.get("type", "")).lower() == "text":
            raw += str(data.get("text", ""))
    return raw.strip()


def build_documentation_bundle(
    *,
    task_text: str,
    track_root: Path,
    docs_manifest: list[DomainDoc],
    documentation: list[str] | None,
    mode: str,
    retrieval_mode: str,
    budget_tokens: int,
    retriever_model: str | None,
    llm_client: Any | None = None,
    max_chunks: int = 10,
) -> DocumentationBundle:
    normalized_mode = normalize_doc_mode(mode)
    normalized_retrieval = normalize_doc_retrieval_mode(retrieval_mode)
    normalized_budget = _normalize_budget_tokens(budget_tokens)
    retrieval_query = str(task_text or "").strip()

    if normalized_mode == "none":
        return DocumentationBundle(
            mode=normalized_mode,
            retrieval_mode=normalized_retrieval,
            budget_tokens=normalized_budget,
            raw_docs=[],
            selected_chunks=[],
            brief="",
            retriever_model=None,
            retrieval_query=retrieval_query,
            brief_strategy="none",
            load_errors=[],
        )

    explicit_docs = _collect_explicit_docs(
        documentation=documentation or [],
        track_root=track_root,
        max_chars_per_doc=24000,
    )
    domain_docs = _collect_domain_docs(
        docs_manifest=docs_manifest,
        max_chars_per_doc=24000,
    )
    raw_docs = explicit_docs + domain_docs
    load_errors = [
        {
            "source_id": doc.source_id,
            "source_ref": doc.source_ref,
            "error": str(doc.error),
        }
        for doc in raw_docs
        if doc.error
    ]

    if normalized_retrieval == "auto":
        selected_chunks = _score_chunks(
            query=retrieval_query,
            docs=raw_docs,
            max_chunks=max_chunks,
        )
    else:
        selected_chunks = []
        query_tokens = _tokenize(retrieval_query)
        for doc in raw_docs:
            if doc.error or not doc.text.strip():
                continue
            # Fallback path (retrieval disabled/offline) still enforces topical filtering.
            if not _doc_tags_match_query(query_tokens, doc.tags):
                continue
            selected_chunks.append(
                SelectedDocChunk(
                    source_id=doc.source_id,
                    title=doc.title,
                    score=1.0,
                    text=_clip_text(doc.text, max_chars=2000),
                )
            )
            if len(selected_chunks) >= max_chunks:
                break

    budget_chars = normalized_budget * 4
    brief = ""
    brief_strategy = "none"
    if normalized_mode == "full":
        # Full mode keeps large context but still obeys explicit budget caps.
        lines: list[str] = []
        for chunk in selected_chunks:
            lines.append(f"[{chunk.source_id}] {chunk.text}")
        brief = _clip_text("\n\n".join(lines), max_chars=max(800, budget_chars))
        brief_strategy = "full"
    else:
        llm_brief = _distill_with_llm(
            client=llm_client,
            model=str(retriever_model or "").strip(),
            task_text=task_text,
            selected_chunks=selected_chunks,
            budget_tokens=normalized_budget,
        )
        if llm_brief:
            brief = _clip_text(llm_brief, max_chars=max(600, budget_chars))
            brief_strategy = "lossy_llm"
        else:
            brief = _fallback_brief(selected_chunks=selected_chunks, budget_chars=max(600, budget_chars))
            brief_strategy = "lossy_fallback"

    return DocumentationBundle(
        mode=normalized_mode,
        retrieval_mode=normalized_retrieval,
        budget_tokens=normalized_budget,
        raw_docs=raw_docs,
        selected_chunks=selected_chunks,
        brief=brief,
        retriever_model=str(retriever_model or "").strip() or None,
        retrieval_query=retrieval_query,
        brief_strategy=brief_strategy,
        load_errors=load_errors,
    )


def write_doc_artifacts(*, session_dir: Path, bundle: DocumentationBundle) -> Path:
    path = session_dir / "docs_artifacts.json"
    path.write_text(json.dumps(bundle.to_dict(), indent=2, ensure_ascii=True), encoding="utf-8")
    return path
