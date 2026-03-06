from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable


@dataclass
class PosttaskPhaseOutcome:
    critic_no_updates: bool
    repeated_error_signatures: list[str]
    v2_candidate_lessons: list[dict[str, Any]]
    promoted_lesson_ids: list[str]
    suppressed_lesson_ids: list[str]


def run_posttask_phase(
    *,
    posttask_learn: bool,
    client: Any | None,
    architecture_mode: str,
    memory_v2_demo_mode: bool,
    skill_manifest_entries: list[Any],
    loop_watchdog_decision: Any,
    watchdog_disable_posttask_effective: bool,
    metrics: dict[str, Any],
    events: list[dict[str, Any]],
    routed_entries: list[Any],
    self_edit_manifest_entries: list[Any],
    effective_self_edit_mode_active: bool,
    task_text: str,
    eval_result: dict[str, Any],
    session_id: int,
    task_id: str,
    domain: str,
    read_skill_refs: set[str],
    learning_mode: str,
    runtime_temperature: float | None,
    final_unresolved_gaps: list[dict[str, Any]],
    run_error_events: list[Any],
    repeated_error_signatures: list[str],
    structured_lessons_required: bool,
    contract_gap_deterministic_recipes: bool,
    adapter: Any,
    opaque_tools: bool,
    benchmark_placebo: bool,
    lesson_activation_records: list[dict[str, Any]],
    contradiction_loser_counts: dict[str, int],
    model_executor: str,
    critic_model_for_run: str,
    posttask_mode: str,
    run_id: str | None,
    paths: Any,
    self_edit_mode_active: bool,
    promotion_min_runs: int,
    promotion_min_delta: float,
    promotion_max_regressions: int,
    max_steps: int,
    sessions_root: Path,
    track_root: Path,
    skills_root: Path,
    manifest_path: Path,
    queue_path: Path,
    promoted_path: Path,
    lessons_path: Path,
    lessons_v2_path: Path,
    deps: dict[str, Any],
) -> PosttaskPhaseOutcome:
    critic_no_updates = False
    v2_candidate_lessons: list[dict[str, Any]] = []
    promoted_lesson_ids: list[str] = []
    suppressed_lesson_ids: list[str] = []

    if posttask_learn and client is not None:
        patching_enabled = architecture_mode == "full" and not memory_v2_demo_mode and bool(skill_manifest_entries)
        if not bool(skill_manifest_entries):
            metrics["posttask_skill_patching_skipped_by_mode"] = True
            metrics["posttask_skill_patching_skip_reason"] = "no_skill_manifest"
        if bool(loop_watchdog_decision) and bool(watchdog_disable_posttask_effective):
            patching_enabled = False
            metrics["posttask_skill_patching_skipped_by_mode"] = True
            metrics["posttask_skill_patching_skip_reason"] = "loop_watchdog_safe_mode"
        metrics["posttask_patch_attempted"] = patching_enabled
        tail_events = [
            {
                "step": row.get("step"),
                "tool": row.get("tool"),
                "tool_input": row.get("tool_input"),
                "ok": row.get("ok"),
                "error": row.get("error"),
            }
            for row in events[-20:]
        ]
        routed_refs = [entry.skill_ref for entry in routed_entries]
        patch_manifest_entries = skill_manifest_entries
        patch_snapshot_refs = routed_refs
        if bool(effective_self_edit_mode_active) and self_edit_manifest_entries:
            patch_manifest_entries = list(self_edit_manifest_entries)
            patch_snapshot_refs = [entry.skill_ref for entry in patch_manifest_entries]
        skill_snapshots, _skill_digests = deps["_load_skill_snapshots"](
            entries=patch_manifest_entries,
            routed_refs=patch_snapshot_refs,
        )
        domain_keywords = adapter.quality_keywords()
        critic_context = ""
        critic_context_sources: list[str] = []
        if learning_mode == "strict":
            retrieval_query = deps["_build_critic_context_query"](
                task_text=task_text,
                eval_result=eval_result,
                events_tail=tail_events,
            )
            docs_bundle = deps["docs_bundle"]
            if deps["doc_mode"] != "none" and docs_bundle.selected_chunks:
                retrieved_chunks = docs_bundle.selected_chunks[:4]
            else:
                docs = adapter.docs_manifest()
                retrieved_chunks = deps["knowledge_provider"].retrieve(
                    query=retrieval_query,
                    docs=docs,
                    max_chunks=4,
                )
            critic_context = deps["_format_critic_context"](retrieved_chunks)
            critic_context_sources = [str(getattr(chunk, "source_id", "")) for chunk in retrieved_chunks]
        metrics["critic_context_sources"] = critic_context_sources
        lesson_model_for_run = model_executor if architecture_mode == "simplified" else critic_model_for_run
        lesson_result = deps["generate_lessons"](
            client=client,
            model=lesson_model_for_run,
            session_id=session_id,
            task_id=task_id,
            task=task_text,
            eval_result=eval_result,
            events_tail=tail_events,
            skill_refs_used=sorted(read_skill_refs),
            domain_name=domain,
            learning_mode=learning_mode,
            critic_context=critic_context,
            domain_keywords=domain_keywords,
            temperature=runtime_temperature,
            unresolved_gaps=final_unresolved_gaps,
            structured_fields_required=False,
        )
        metrics["critic_raw_lessons"] = [deps["_serialize_lesson"](lesson) for lesson in lesson_result.raw_lessons]
        metrics["critic_filtered_lessons"] = [deps["_serialize_lesson"](lesson) for lesson in lesson_result.filtered_lessons]
        filtered_texts = {lesson.lesson for lesson in lesson_result.filtered_lessons}
        rejected = [lesson for lesson in lesson_result.raw_lessons if lesson.lesson not in filtered_texts]
        metrics["critic_rejected_lessons"] = [deps["_serialize_lesson"](lesson) for lesson in rejected]
        metrics["critic_generation_error"] = str(getattr(lesson_result, "error", "") or "")
        metrics["critic_generation_parsed_items"] = int(getattr(lesson_result, "parsed_items", 0) or 0)
        metrics["critic_generation_raw_chars"] = len(str(getattr(lesson_result, "raw_response_text", "") or ""))
        metrics["lessons_generated"] = deps["store_lessons"](path=lessons_path, lessons=lesson_result.filtered_lessons)
        deps["prune_lessons"](lessons_path, max_per_task=20, domain_keywords=domain_keywords)

        v2_reflection = deps["generate_lessons"](
            client=client,
            model=model_executor,
            session_id=session_id,
            task_id=task_id,
            task=task_text,
            eval_result=eval_result,
            events_tail=tail_events,
            skill_refs_used=sorted(read_skill_refs),
            domain_name=domain,
            learning_mode=learning_mode,
            critic_context=critic_context,
            domain_keywords=domain_keywords,
            temperature=runtime_temperature,
            unresolved_gaps=final_unresolved_gaps,
            structured_fields_required=bool(structured_lessons_required),
        )
        metrics["v2_generation_error"] = str(getattr(v2_reflection, "error", "") or "")
        metrics["v2_generation_parsed_items"] = int(getattr(v2_reflection, "parsed_items", 0) or 0)
        metrics["v2_generation_raw_chars"] = len(str(getattr(v2_reflection, "raw_response_text", "") or ""))
        hard_events = [event for event in run_error_events if event.channel == "hard_failure"]
        fingerprint_counts = Counter(event.fingerprint for event in hard_events)
        recurring_fingerprints = [fingerprint for fingerprint, count in fingerprint_counts.items() if count >= 2]
        prioritized_fingerprints = recurring_fingerprints or [fingerprint for fingerprint, _ in fingerprint_counts.most_common(3)]
        if not repeated_error_signatures:
            repeated_error_signatures = list(recurring_fingerprints)
        v2_candidates: list[Any] = []
        structured_gap_rows = list(final_unresolved_gaps)
        structured_gap_by_signature = {
            str(row.get("gap_signature", "")).strip(): row
            for row in structured_gap_rows
            if str(row.get("gap_signature", "")).strip()
        }
        structured_reason_gap_pairs = {
            (
                str(row.get("reason_code", "")).strip(),
                str(row.get("gap_type", "")).strip(),
            )
            for row in structured_gap_rows
            if str(row.get("reason_code", "")).strip() and str(row.get("gap_type", "")).strip()
        }
        allowed_action_tools = deps["_allowed_action_tools_for_adapter"](adapter=adapter, opaque_tools=opaque_tools)
        fallback_rules: list[str] = []
        source_lesson_rows: list[dict[str, Any]] = []
        structured_model_rows_added = 0
        deterministic_gap_signatures: set[str] = set()
        deterministic_reason_gap_pairs: set[tuple[str, str]] = set()
        if structured_lessons_required and structured_gap_rows and bool(contract_gap_deterministic_recipes):
            deterministic_rules = deps["_deterministic_gap_fix_recipes"](
                adapter=adapter,
                domain=domain,
                task_id=task_id,
                unresolved_gaps=structured_gap_rows,
                max_items=3,
            )
            for idx, recipe in enumerate(deterministic_rules):
                gap_row = structured_gap_rows[min(idx, len(structured_gap_rows) - 1)]
                reason_code = str(gap_row.get("reason_code", "")).strip()
                gap_type = str(gap_row.get("gap_type", "")).strip()
                gap_signature = str(gap_row.get("gap_signature", "")).strip()
                action_template = deps["_extract_action_template_from_legacy_lesson"](
                    lesson_text=recipe,
                    executor_tool_name=str(adapter.executor_tool_name),
                )
                # In strict mode deterministic fallbacks must still be executable.
                # If we cannot extract a real tool call, skip this row instead of
                # generating a lesson that retrieval will reject later.
                if structured_lessons_required and not action_template:
                    continue
                expected_evidence = gap_signature or f"{reason_code}|{gap_type}"
                source_lesson_rows.append(
                    {
                        "lesson_text": recipe,
                        "gap_row": gap_row,
                        "reason_code": reason_code,
                        "gap_type": gap_type,
                        "gap_signature": gap_signature,
                        "action_template": action_template,
                        "expected_evidence": expected_evidence,
                        "source_kind": "deterministic",
                    }
                )
                if gap_signature:
                    deterministic_gap_signatures.add(gap_signature)
                if reason_code and gap_type:
                    deterministic_reason_gap_pairs.add((reason_code, gap_type))
            fallback_rules = list(deterministic_rules)
            metrics["v2_structured_fallback_lessons"] = len(deterministic_rules)

        for idx, lesson in enumerate(v2_reflection.filtered_lessons):
            text = str(getattr(lesson, "lesson", "")).strip()
            if not text:
                continue
            if structured_lessons_required:
                valid_structured, rejection_reason, structured_payload = deps["_validate_structured_model_lesson"](
                    lesson=lesson,
                    unresolved_gap_rows=structured_gap_rows,
                    allowed_action_tools=allowed_action_tools,
                )
                if not valid_structured:
                    reason_key = str(rejection_reason).strip() or "invalid_structured_lesson"
                    metrics["v2_schema_rejection_counts"][reason_key] = int(
                        metrics["v2_schema_rejection_counts"].get(reason_key, 0)
                    ) + 1
                    continue
                trigger_signature = str(structured_payload.get("trigger_gap_signature", "")).strip()
                gap_row = structured_gap_by_signature.get(trigger_signature, {})
                reason_code = str(structured_payload.get("reason_code", "")).strip()
                gap_type = str(structured_payload.get("gap_type", "")).strip()

                # Deterministic recipes are the safer source of truth. If a
                # model-generated lesson targets a gap family already covered by
                # deterministic repair logic, skip it instead of storing a
                # second, noisier version of the same fix.
                if trigger_signature and trigger_signature in deterministic_gap_signatures:
                    metrics["v2_schema_rejection_counts"]["covered_by_deterministic_recipe"] = int(
                        metrics["v2_schema_rejection_counts"].get("covered_by_deterministic_recipe", 0)
                    ) + 1
                    continue
                if reason_code and gap_type and (reason_code, gap_type) in deterministic_reason_gap_pairs:
                    metrics["v2_schema_rejection_counts"]["covered_by_deterministic_recipe"] = int(
                        metrics["v2_schema_rejection_counts"].get("covered_by_deterministic_recipe", 0)
                    ) + 1
                    continue

                action_template = str(structured_payload.get("action_template", "")).strip()
                expected_evidence = str(structured_payload.get("expected_evidence", "")).strip()
                normalized_note = " ".join(text.split()).strip()
                if normalized_note:
                    lesson_text = (
                        f"WHEN gap_signature={trigger_signature}: {action_template} "
                        f"EXPECT: {expected_evidence}. NOTE: {normalized_note}"
                    )
                else:
                    lesson_text = (
                        f"WHEN gap_signature={trigger_signature}: {action_template} "
                        f"EXPECT: {expected_evidence}."
                    )
                source_lesson_rows.append(
                    {
                        "lesson_text": lesson_text,
                        "gap_row": gap_row,
                        "reason_code": reason_code,
                        "gap_type": gap_type,
                        "gap_signature": trigger_signature,
                        "action_template": action_template,
                        "expected_evidence": expected_evidence,
                        "source_kind": "model_structured",
                    }
                )
                structured_model_rows_added += 1
                continue
            gap_row = structured_gap_rows[min(idx, len(structured_gap_rows) - 1)] if structured_gap_rows else {}
            source_lesson_rows.append(
                {
                    "lesson_text": text,
                    "gap_row": gap_row,
                    "reason_code": str(gap_row.get("reason_code", "")).strip(),
                    "gap_type": str(gap_row.get("gap_type", "")).strip(),
                    "gap_signature": str(gap_row.get("gap_signature", "")).strip(),
                    "action_template": "",
                    "expected_evidence": "",
                    "source_kind": "model_legacy",
                }
            )

        if (
            structured_lessons_required
            and structured_gap_rows
            and structured_model_rows_added == 0
            and not deterministic_gap_signatures
            and not deterministic_reason_gap_pairs
        ):
            legacy_sources = list(lesson_result.filtered_lessons) + list(v2_reflection.filtered_lessons)
            backfilled_count = 0
            for idx, legacy_lesson in enumerate(legacy_sources):
                legacy_text = str(getattr(legacy_lesson, "lesson", "")).strip()
                if not legacy_text:
                    continue
                action_template = deps["_extract_action_template_from_legacy_lesson"](
                    lesson_text=legacy_text,
                    executor_tool_name=str(adapter.executor_tool_name),
                )
                if not action_template:
                    continue
                gap_row = structured_gap_rows[min(idx, len(structured_gap_rows) - 1)]
                trigger_signature = str(gap_row.get("gap_signature", "")).strip()
                reason_code = str(gap_row.get("reason_code", "")).strip()
                gap_type = str(gap_row.get("gap_type", "")).strip()
                if not (trigger_signature and reason_code and gap_type):
                    continue
                evidence = trigger_signature
                valid_backfill, _, payload = deps["_validate_structured_model_lesson"](
                    lesson=SimpleNamespace(
                        trigger_gap_signature=trigger_signature,
                        reason_code=reason_code,
                        gap_type=gap_type,
                        action_template=action_template,
                        expected_evidence=evidence,
                    ),
                    unresolved_gap_rows=structured_gap_rows,
                    allowed_action_tools=allowed_action_tools,
                )
                if not valid_backfill:
                    continue
                source_lesson_rows.append(
                    {
                        "lesson_text": (
                            f"WHEN gap_signature={payload['trigger_gap_signature']}: "
                            f"{payload['action_template']} EXPECT: {payload['expected_evidence']}."
                        ),
                        "gap_row": gap_row,
                        "reason_code": str(payload.get("reason_code", "")).strip(),
                        "gap_type": str(payload.get("gap_type", "")).strip(),
                        "gap_signature": str(payload.get("trigger_gap_signature", "")).strip(),
                        "action_template": str(payload["action_template"]).strip(),
                        "expected_evidence": str(payload["expected_evidence"]).strip(),
                        "source_kind": "legacy_backfill",
                    }
                )
                backfilled_count += 1
            metrics["v2_legacy_backfill_lessons"] = int(backfilled_count)

        seen_lesson_texts: set[str] = set()
        for source_row in source_lesson_rows:
            lesson_text = str(source_row.get("lesson_text", "")).strip()
            gap_row = source_row.get("gap_row", {}) if isinstance(source_row.get("gap_row", {}), dict) else {}
            action_template = str(source_row.get("action_template", "")).strip()
            expected_evidence = str(source_row.get("expected_evidence", "")).strip()
            normalized_text = " ".join(str(lesson_text).lower().split())
            if normalized_text in seen_lesson_texts:
                continue
            seen_lesson_texts.add(normalized_text)
            reason_code = str(source_row.get("reason_code", "")).strip() or str(gap_row.get("reason_code", "")).strip()
            gap_type = str(source_row.get("gap_type", "")).strip() or str(gap_row.get("gap_type", "")).strip()
            gap_signature = str(source_row.get("gap_signature", "")).strip() or str(gap_row.get("gap_signature", "")).strip()

            # Keep structured lessons bound to real unresolved gaps only.
            # This prevents generic "eval_reason" signatures from entering memory,
            # which otherwise creates silent retrieval misses later.
            if structured_lessons_required and gap_signature and "|" in gap_signature:
                parts = gap_signature.split("|", 2)
                if len(parts) >= 2:
                    reason_code = reason_code or parts[0].strip()
                    gap_type = gap_type or parts[1].strip()
            if structured_lessons_required:
                signature_bound = bool(gap_signature and gap_signature in structured_gap_by_signature)
                reason_gap_bound = bool(reason_code and gap_type and (reason_code, gap_type) in structured_reason_gap_pairs)
                if not signature_bound and reason_gap_bound:
                    # Canonicalize to a stable signature in the current unresolved set.
                    for row in structured_gap_rows:
                        if (
                            str(row.get("reason_code", "")).strip() == reason_code
                            and str(row.get("gap_type", "")).strip() == gap_type
                        ):
                            canonical_signature = str(row.get("gap_signature", "")).strip()
                            if canonical_signature:
                                gap_signature = canonical_signature
                                break
                signature_bound = bool(gap_signature and gap_signature in structured_gap_by_signature)
                reason_gap_bound = bool(reason_code and gap_type and (reason_code, gap_type) in structured_reason_gap_pairs)
                if not signature_bound and not reason_gap_bound:
                    metrics["v2_schema_rejection_counts"]["unbound_trigger_gap_signature"] = int(
                        metrics["v2_schema_rejection_counts"].get("unbound_trigger_gap_signature", 0)
                    ) + 1
                    continue
            tags = deps["extract_tags"](error=lesson_text)
            v2_candidates.append(
                deps["lesson_record_cls"].from_candidate(
                    session_id=session_id,
                    task_id=task_id,
                    task=task_text,
                    domain=domain,
                    rule_text=lesson_text,
                    trigger_fingerprints=prioritized_fingerprints,
                    tags=tags,
                    status="candidate",
                    reason_code=reason_code,
                    gap_type=gap_type,
                    gap_signature=gap_signature,
                    action_template=action_template,
                    expected_evidence=expected_evidence,
                )
            )
        v2_candidate_lessons = [
            {
                "lesson_id": row.lesson_id,
                "rule_text": row.rule_text,
                "trigger_fingerprints": list(row.trigger_fingerprints),
                "tags": list(row.tags),
                "reason_code": row.reason_code,
                "gap_type": row.gap_type,
                "gap_signature": row.gap_signature,
                "action_template": row.action_template,
                "expected_evidence": row.expected_evidence,
            }
            for row in v2_candidates
        ]
        posttask_lessons_raw = {
            "raw_lessons": [deps["_serialize_lesson"](lesson) for lesson in v2_reflection.raw_lessons],
            "filtered_lessons": [deps["_serialize_lesson"](lesson) for lesson in v2_reflection.filtered_lessons],
            "fallback_rules": list(fallback_rules),
            "unresolved_gaps": list(final_unresolved_gaps),
            "generation_error": str(getattr(v2_reflection, "error", "") or ""),
            "generation_parsed_items": int(getattr(v2_reflection, "parsed_items", 0) or 0),
            "generation_raw_response": str(getattr(v2_reflection, "raw_response_text", "") or ""),
        }
        posttask_lessons_applied = {
            "candidates": v2_candidate_lessons,
            "structured_required": bool(structured_lessons_required),
        }
        posttask_lessons_raw_path = paths.session_dir / "posttask_lessons_raw.json"
        posttask_lessons_applied_path = paths.session_dir / "posttask_lessons_applied.json"
        posttask_lessons_raw_path.write_text(
            json.dumps(posttask_lessons_raw, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
        posttask_lessons_applied_path.write_text(
            json.dumps(posttask_lessons_applied, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
        metrics["posttask_lessons_raw_path"] = str(posttask_lessons_raw_path)
        metrics["posttask_lessons_applied_path"] = str(posttask_lessons_applied_path)
        v2_store_result = deps["upsert_lesson_records"](lessons_v2_path, v2_candidates)
        metrics["v2_lessons_generated"] = int(v2_store_result.get("inserted", 0))
        metrics["v2_lessons_merged"] = int(v2_store_result.get("merged", 0))
        metrics["v2_conflict_links"] = int(v2_store_result.get("conflict_links", 0))
        metrics["v2_fingerprint_counts"] = dict(fingerprint_counts)
        metrics["v2_fingerprint_recurrence"] = sum(1 for count in fingerprint_counts.values() if count > 1)
        metrics["v2_fingerprint_recurrence_before"] = metrics["v2_fingerprint_recurrence"]

        recent_scores = deps["_load_recent_eval_scores"](sessions_root=sessions_root, task_id=task_id, domain=domain)
        baseline_score = (sum(recent_scores) / float(len(recent_scores))) if recent_scores else None
        referee_gain = None if baseline_score is None else float(metrics.get("eval_score", 0.0) or 0.0) - baseline_score

        activations_by_lesson: dict[str, dict[str, float]] = defaultdict(lambda: {"error": 0.0, "eff": 0.0, "count": 0.0})
        helped = 0
        effective_activation_records = 0
        fingerprints_recur_after: set[str] = set()
        for activation in lesson_activation_records:
            if bool(activation.get("placebo_applied", False)):
                continue
            effective_activation_records += 1
            step_idx = int(activation.get("step", 0) or 0)
            fingerprint = str(activation.get("fingerprint", ""))
            repeats_after = sum(
                1
                for event in hard_events
                if event.fingerprint == fingerprint and int(event.metadata.get("step", 0) or 0) > step_idx
            )
            error_reduction = 1.0 if repeats_after == 0 else -deps["_clamp"](repeats_after / 3.0, 0.0, 1.0)
            step_efficiency_gain = deps["_clamp"](
                1.0 - (float(metrics.get("steps", 0) or 0) / float(max(1, max_steps))),
                -1.0,
                1.0,
            )
            if error_reduction > 0:
                helped += 1
            if repeats_after > 0:
                fingerprints_recur_after.add(fingerprint)
            for lesson_id in activation.get("lesson_ids", []):
                lesson_key = str(lesson_id).strip()
                if not lesson_key:
                    continue
                bucket = activations_by_lesson[lesson_key]
                bucket["error"] += error_reduction
                bucket["eff"] += step_efficiency_gain
                bucket["count"] += 1.0

        outcomes: list[Any] = []
        current_records_by_id = {row.lesson_id: row for row in deps["load_lesson_records"](lessons_v2_path)}
        unresolved_reason_codes = {
            str(row.get("reason_code", "")).strip()
            for row in final_unresolved_gaps
            if str(row.get("reason_code", "")).strip()
        }
        unresolved_gap_signatures = {
            str(row.get("gap_signature", "")).strip()
            for row in final_unresolved_gaps
            if str(row.get("gap_signature", "")).strip()
        }
        for lesson_id, bucket in activations_by_lesson.items():
            count = max(1.0, bucket["count"])
            current_record = current_records_by_id.get(lesson_id)
            gap_resolved: bool | None = None
            same_signature_failed = False
            if current_record is not None and (
                str(current_record.reason_code).strip() or str(current_record.gap_type).strip()
            ):
                candidate_signature = str(current_record.gap_signature).strip()
                candidate_reason = str(current_record.reason_code).strip()
                if candidate_signature:
                    gap_resolved = candidate_signature not in unresolved_gap_signatures
                    same_signature_failed = not bool(gap_resolved)
                elif candidate_reason:
                    gap_resolved = candidate_reason not in unresolved_reason_codes
                else:
                    gap_resolved = True
            outcomes.append(
                deps["lesson_outcome_cls"](
                    lesson_id=lesson_id,
                    error_reduction=bucket["error"] / count,
                    step_efficiency_gain=bucket["eff"] / count,
                    referee_score_gain=referee_gain,
                    major_regression=bool(metrics.get("eval_score", 0.0) < 0.2 and metrics.get("tool_errors", 0) > 0),
                    contradiction_lost=False,
                    gap_resolved=gap_resolved,
                    same_signature_failed=same_signature_failed,
                )
            )
        for lesson_id, count in contradiction_loser_counts.items():
            if benchmark_placebo:
                continue
            if count <= 0:
                continue
            outcomes.append(
                deps["lesson_outcome_cls"](
                    lesson_id=lesson_id,
                    error_reduction=0.0,
                    step_efficiency_gain=0.0,
                    referee_score_gain=referee_gain,
                    contradiction_lost=True,
                    gap_resolved=False,
                )
            )
        records_before = {row.lesson_id: row.status for row in deps["load_lesson_records"](lessons_v2_path)}
        promotion_result_v2 = deps["apply_outcomes"](path=lessons_v2_path, outcomes=outcomes)
        records_after = {row.lesson_id: row.status for row in deps["load_lesson_records"](lessons_v2_path)}
        promoted_lesson_ids = sorted(
            lesson_id
            for lesson_id, status in records_after.items()
            if status == "promoted" and records_before.get(lesson_id) != "promoted"
        )
        suppressed_lesson_ids = sorted(
            lesson_id
            for lesson_id, status in records_after.items()
            if status == "suppressed" and records_before.get(lesson_id) != "suppressed"
        )
        metrics["v2_promoted"] = int(promotion_result_v2.get("promoted", 0))
        metrics["v2_suppressed"] = int(promotion_result_v2.get("suppressed", 0))
        metrics["v2_outcomes_updated"] = int(promotion_result_v2.get("updated", 0))
        metrics["v2_promoted_ids"] = promoted_lesson_ids
        metrics["v2_suppressed_ids"] = suppressed_lesson_ids
        metrics["v2_fingerprint_recurrence_after"] = len(fingerprints_recur_after)
        metrics["v2_retrieval_help_ratio"] = round(
            float(helped) / float(max(1, effective_activation_records)),
            4,
        )
        metrics["v2_retrieval_help_ratio_effective"] = metrics["v2_retrieval_help_ratio"]
        activation_by_step: dict[str, int] = {}
        activation_lane_counts: Counter[str] = Counter()
        activation_by_step_effective: dict[str, int] = {}
        activation_lane_counts_effective: Counter[str] = Counter()
        activation_records_effective = 0
        for activation in lesson_activation_records:
            step_key = str(int(activation.get("step", 0) or 0))
            lesson_ids = activation.get("lesson_ids", [])
            step_count = len(lesson_ids) if isinstance(lesson_ids, list) else 0
            activation_by_step[step_key] = activation_by_step.get(step_key, 0) + step_count
            lane_map = activation.get("lesson_lanes", {})
            if isinstance(lane_map, dict):
                for lane in lane_map.values():
                    lane_text = str(lane).strip().lower()
                    if lane_text:
                        activation_lane_counts[lane_text] += 1
            if bool(activation.get("placebo_applied", False)):
                continue
            activation_records_effective += 1
            activation_by_step_effective[step_key] = activation_by_step_effective.get(step_key, 0) + step_count
            if isinstance(lane_map, dict):
                for lane in lane_map.values():
                    lane_text = str(lane).strip().lower()
                    if lane_text:
                        activation_lane_counts_effective[lane_text] += 1
        metrics["v2_lesson_activations_by_step"] = activation_by_step
        metrics["v2_lesson_activations_by_step_effective"] = activation_by_step_effective
        metrics["v2_lesson_activations_per_run"] = len(lesson_activation_records)
        metrics["v2_lesson_activations_per_run_effective"] = activation_records_effective
        metrics["v2_lesson_activation_rate"] = round(
            float(metrics.get("v2_lesson_activations", 0) or 0) / float(max(1, int(metrics.get("steps", 0) or 0))),
            4,
        )
        metrics["v2_lesson_activation_lane_counts"] = dict(activation_lane_counts)
        metrics["v2_lesson_activation_lane_counts_effective"] = dict(activation_lane_counts_effective)

        if not patching_enabled:
            metrics["posttask_skill_patching_skipped_by_mode"] = True
            if not metrics.get("posttask_skill_patching_skip_reason"):
                if memory_v2_demo_mode:
                    metrics["posttask_skill_patching_skip_reason"] = "memory_v2_demo_mode"
                else:
                    metrics["posttask_skill_patching_skip_reason"] = "architecture_mode"
        else:
            proposed_updates, confidence, reflection_raw = deps["propose_skill_updates"](
                client=client,
                model=critic_model_for_run,
                task=task_text,
                metrics=metrics,
                eval_result=eval_result,
                events_tail=tail_events,
                routed_skill_refs=routed_refs,
                read_skill_refs=sorted(read_skill_refs),
                skill_snapshots=skill_snapshots,
                domain_name=adapter.name,
            )
            if not proposed_updates:
                parse_rejection_counts = {
                    "parse_fail": 0,
                    "required_digest_mismatch": 0,
                    "duplicate_jaccard": 0,
                    "replace_miss": 0,
                }
                parsed_updates, parsed_confidence = deps["parse_reflection_response"](
                    reflection_raw,
                    rejection_counts=parse_rejection_counts,
                )
                if parsed_updates:
                    proposed_updates = parsed_updates
                    confidence = parsed_confidence
                for reason, count in parse_rejection_counts.items():
                    metrics["posttask_rejection_counts"][reason] = int(
                        metrics["posttask_rejection_counts"].get(reason, 0)
                    ) + int(count)

            critic_no_updates = len(proposed_updates) == 0
            required_digests = {update.skill_ref: update.skill_digest for update in proposed_updates}
            if bool(effective_self_edit_mode_active):
                allowed_refs = deps["self_edit_allowed_refs"]()
            else:
                allowed_refs = {update.skill_ref for update in proposed_updates}

            if bool(effective_self_edit_mode_active):
                proposal_status = "proposed" if proposed_updates else "rejected"
                proposal_reason = None if proposed_updates else "no_updates"
                deps["append_self_edit_gate_event"](
                    sessions_root=sessions_root,
                    run_id=run_id or "",
                    session_id=session_id,
                    task_id=task_id,
                    domain=domain,
                    learn_mode=learning_mode,
                    stage="proposal",
                    status=proposal_status,
                    reason=proposal_reason,
                    metadata={
                        "confidence": float(confidence),
                        "update_count": int(len(proposed_updates)),
                    },
                )
                metrics["self_edit_gate_events"] = int(metrics.get("self_edit_gate_events", 0) or 0) + 1

            effective_posttask_mode = posttask_mode
            if bool(effective_self_edit_mode_active) and posttask_mode != "direct":
                effective_posttask_mode = "direct"
                metrics["self_edit_forced_direct_mode"] = True

            if bool(effective_self_edit_mode_active):
                patch_result = deps["apply_guarded_self_edit_updates"](
                    entries=patch_manifest_entries,
                    updates=proposed_updates,
                    confidence=confidence,
                    track_root=track_root,
                    required_skill_digests=required_digests,
                    allowed_skill_refs=allowed_refs,
                )
                metrics["posttask_patch_applied"] = int(patch_result.get("applied", 0))
                patch_rejections = patch_result.get("rejection_counts", {})
                if isinstance(patch_rejections, dict):
                    for reason, count in patch_rejections.items():
                        reason_key = str(reason)
                        metrics["posttask_rejection_counts"][reason_key] = int(
                            metrics["posttask_rejection_counts"].get(reason_key, 0)
                        ) + int(count)
                patch_status = "accepted" if int(patch_result.get("applied", 0) or 0) > 0 else "rejected"
                deps["append_self_edit_gate_event"](
                    sessions_root=sessions_root,
                    run_id=run_id or "",
                    session_id=session_id,
                    task_id=task_id,
                    domain=domain,
                    learn_mode=learning_mode,
                    stage="patch",
                    status=patch_status,
                    reason=str(patch_result.get("skipped_reason", "")).strip() or None,
                    rollback_reason="verification_failed" if bool(patch_result.get("rolled_back", False)) else None,
                    metadata={
                        "applied": int(patch_result.get("applied", 0) or 0),
                        "updated_skill_refs": list(patch_result.get("updated_skill_refs", [])),
                    },
                )
                metrics["self_edit_gate_events"] = int(metrics.get("self_edit_gate_events", 0) or 0) + 1
            elif effective_posttask_mode == "direct":
                patch_result = deps["apply_skill_updates"](
                    entries=skill_manifest_entries,
                    updates=proposed_updates,
                    confidence=confidence,
                    skills_root=skills_root,
                    manifest_path=manifest_path,
                    required_skill_digests=required_digests,
                    allowed_skill_refs=allowed_refs,
                )
                metrics["posttask_patch_applied"] = int(patch_result.get("applied", 0))
                patch_rejections = patch_result.get("rejection_counts", {})
                if isinstance(patch_rejections, dict):
                    for reason, count in patch_rejections.items():
                        reason_key = str(reason)
                        metrics["posttask_rejection_counts"][reason_key] = int(
                            metrics["posttask_rejection_counts"].get(reason_key, 0)
                        ) + int(count)
            else:
                patch_result = deps["queue_skill_update_candidates"](
                    queue_path=queue_path,
                    updates=proposed_updates,
                    confidence=confidence,
                    session_id=session_id,
                    task_id=task_id,
                    required_skill_digests=required_digests,
                    allowed_skill_refs=allowed_refs,
                    evaluation=eval_result,
                )
                metrics["posttask_candidates_queued"] = int(patch_result.get("queued", 0))
                queue_rejections = patch_result.get("rejection_counts", {})
                if isinstance(queue_rejections, dict):
                    for reason, count in queue_rejections.items():
                        reason_key = str(reason)
                        metrics["posttask_rejection_counts"][reason_key] = int(
                            metrics["posttask_rejection_counts"].get(reason_key, 0)
                        ) + int(count)

            deps["write_event"](
                paths.events_path,
                {
                    "step": int(metrics["steps"]) + 1,
                    "tool": "posttask_hook",
                    "tool_input": {"mode": effective_posttask_mode, "critic_model": critic_model_for_run},
                    "ok": True,
                    "error": None,
                    "output": json.dumps(
                        {
                            "confidence": confidence,
                            "update_count": len(proposed_updates),
                            "result": patch_result,
                        },
                        ensure_ascii=True,
                    ),
                },
            )

            if bool(effective_self_edit_mode_active):
                promotion_result = {
                    "attempted": False,
                    "applied": 0,
                    "reason": "self_edit_direct_mode",
                }
                deps["append_self_edit_gate_event"](
                    sessions_root=sessions_root,
                    run_id=run_id or "",
                    session_id=session_id,
                    task_id=task_id,
                    domain=domain,
                    learn_mode=learning_mode,
                    stage="promotion",
                    status="rejected",
                    reason="self_edit_direct_mode",
                    metadata={"posttask_mode": str(posttask_mode)},
                )
                metrics["self_edit_gate_events"] = int(metrics.get("self_edit_gate_events", 0) or 0) + 1
            else:
                promotion_result = deps["auto_promote_queued_candidates"](
                    entries=skill_manifest_entries,
                    queue_path=queue_path,
                    promoted_path=promoted_path,
                    sessions_root=sessions_root,
                    task_id=task_id,
                    skills_root=skills_root,
                    manifest_path=manifest_path,
                    min_runs=promotion_min_runs,
                    min_delta=promotion_min_delta,
                    max_regressions=promotion_max_regressions,
                )
            metrics["auto_promotion_applied"] = int(promotion_result.get("applied", 0))
            metrics["auto_promotion_reason"] = promotion_result.get("reason")
            deps["write_event"](
                paths.events_path,
                {
                    "step": int(metrics["steps"]) + 2,
                    "tool": "promotion_gate",
                    "tool_input": {"task_id": task_id, "min_runs": promotion_min_runs, "min_delta": promotion_min_delta},
                    "ok": True,
                    "error": None,
                    "output": json.dumps(promotion_result, ensure_ascii=True),
                },
            )
    elif posttask_learn and client is None:
        metrics["posttask_skill_patching_skipped_by_mode"] = True
        metrics["posttask_skill_patching_skip_reason"] = "no_llm_client"

    return PosttaskPhaseOutcome(
        critic_no_updates=critic_no_updates,
        repeated_error_signatures=repeated_error_signatures,
        v2_candidate_lessons=v2_candidate_lessons,
        promoted_lesson_ids=promoted_lesson_ids,
        suppressed_lesson_ids=suppressed_lesson_ids,
    )
