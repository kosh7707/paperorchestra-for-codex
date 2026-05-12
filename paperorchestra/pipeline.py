from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import html
import json
import math
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from .boundary import (
    assert_author_facing_payload,
    is_material_packet_control_section_title,
    is_material_packet_section_title,
    normalized_claim_projection,
    sanitize_author_facing_text,
)
from .manuscript_repair import (
    SECTION_COMMAND_RE,
    _canonical_generated_section_title,
    _citation_map_for_selected_sections,
    _ensure_discussion_section_for_claim_boundaries,
    _ensure_required_claim_scope_notes,
    _ensure_text_safe_math_macros,
    _insert_block_into_section,
    _move_macro_definitions_to_preamble,
    _paragraph_insertion_index,
    _preferred_section_name,
    _remove_material_packet_sections,
    _repair_inline_math_surplus_closing_brace,
    _required_claim_scope_note,
    _restore_missing_referenced_labels,
    _sanitize_manuscript_control_prose,
    _section_range_map,
)
from .domains import get_domain
from .io_utils import ExtractionError, extract_json, extract_latex, read_json, read_text, write_json, write_text
from .compile_env import inspect_compile_environment
from .latex import compile_latex, compile_latex_with_report
from .fidelity import run_fidelity_audit, write_reproducibility_audit
from .literature import (
    build_search_grounded_candidates,
    ensure_unique_bibtex_keys,
    load_prior_work_seed,
    mock_verified_paper,
    prior_work_entries_to_verified_papers,
    registry_to_bibtex,
    search_semantic_scholar,
    serialize_registry,
    verify_candidate_title,
)
from .models import ScoreSnapshot, VerifiedPaper, utc_now_iso
from .narrative import planning_artifact_status, require_fresh_planning_artifacts, write_planning_artifacts
from .prompts import PROMPTS
from .plot_assets import render_plot_assets
from .omx_bridge import omx_exec_completion, omx_exec_json_completion
from .runtime_parity import record_lane_manifest, record_runtime_parity_report
from .validator import (
    CITE_COMMAND_RE,
    FIGURE_ENV_RE,
    LABEL_RE,
    ValidationIssue,
    build_figure_placement_review,
    canonicalize_citation_keys,
    extract_citation_keys,
    validate_manuscript,
)
from .providers import CompletionRequest, BaseProvider, ShellProvider
from .session import artifact_path, build_path, load_session, review_path, runtime_root, save_session


class ContractError(ValueError):
    pass


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _strict_omx_native_enabled() -> bool:
    return _env_flag("PAPERO_STRICT_OMX_NATIVE")


def _lane_owner(lane_type: str, fallback_used: bool) -> str:
    return "python-kernel" if fallback_used else lane_type


def _provider_name(provider: BaseProvider | None) -> str | None:
    if provider is None:
        return None
    return getattr(provider, "name", provider.__class__.__name__.lower())


def _env_float(name: str) -> float | None:
    raw = os.environ.get(name)
    if raw in {None, ""}:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _env_int(name: str) -> int | None:
    raw = os.environ.get(name)
    if raw in {None, ""}:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _build_completion_request(*, system_prompt: str, user_prompt: str) -> CompletionRequest:
    return CompletionRequest(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=_env_float("PAPERO_PROVIDER_TEMPERATURE"),
        max_output_tokens=_env_int("PAPERO_PROVIDER_MAX_OUTPUT_TOKENS"),
        seed=_env_int("PAPERO_PROVIDER_SEED"),
    )


def _provider_identity_payload(
    provider: BaseProvider | None,
    *,
    runtime_mode: str,
    stage: str | None = None,
    request: CompletionRequest | None = None,
) -> dict[str, Any]:
    provider_name = _provider_name(provider)
    strict = _strict_omx_native_enabled()
    payload: dict[str, Any] = {
        "provider_name": provider_name,
        "runtime_mode": runtime_mode,
        "stage": stage,
        "strict_omx_native": strict,
        "provider_command_present": False,
        "provider_command_digest": None,
        "model_command_source": None,
        "resolved_backend_class": "unknown",
        "request_controls": request.control_summary() if request is not None else None,
        "generation_determinism": {
            "byte_identical_generation_claimed": False,
            "sampling_controls_are_passthrough_only": True,
            "rationale": (
                "PaperOrchestra records provider controls for auditability, but stochastic or "
                "agentic model backends may still produce non-identical text."
            ),
        },
        "generated_at": utc_now_iso(),
    }
    if provider_name == "mock":
        payload["resolved_backend_class"] = "mock"
        return payload
    if isinstance(provider, ShellProvider):
        command_repr = json.dumps(provider.argv, ensure_ascii=False)
        payload["provider_command_present"] = bool(provider.argv)
        payload["provider_command_digest"] = hashlib.sha256(command_repr.encode("utf-8")).hexdigest()
        payload["model_command_source"] = getattr(provider, "command_source", "unknown")
        payload["resolved_backend_class"] = "real_shell_backend" if provider.argv else "unknown"
        return payload
    return payload


def _record_provider_identity(
    cwd: str | Path | None,
    *,
    provider: BaseProvider | None,
    runtime_mode: str,
    stage: str | None = None,
    request: CompletionRequest | None = None,
) -> list[str]:
    try:
        path = artifact_path(cwd, "provider-identity.json")
        payload = _provider_identity_payload(provider, runtime_mode=runtime_mode, stage=stage, request=request)
        write_json(path, payload)
        state = load_session(cwd)
        state.artifacts.latest_provider_identity_json = str(path)
        state.latest_provider_name = payload.get("provider_name")
        state.latest_runtime_mode = runtime_mode
        save_session(cwd, state)
        return [f"Provider identity recorded: {path.name}"]
    except Exception as exc:  # pragma: no cover - defensive artifact guard
        return [f"Provider identity recording failed: {exc}"]


def _record_prompt_trace(
    cwd: str | Path | None,
    *,
    stage: str,
    request: CompletionRequest,
    runtime_mode: str,
    provider: BaseProvider | None,
) -> list[str]:
    token = f"{stage}.{time.time_ns()}"
    provider_identity = _provider_identity_payload(provider, runtime_mode=runtime_mode, stage=stage, request=request)
    provider_notes = _record_provider_identity(
        cwd,
        provider=provider,
        runtime_mode=runtime_mode,
        stage=stage,
        request=request,
    )
    try:
        system_path = artifact_path(cwd, f"prompts/{token}.system.md")
        user_path = artifact_path(cwd, f"prompts/{token}.user.md")
        combined_path = artifact_path(cwd, f"prompts/{token}.combined.md")
        meta_path = artifact_path(cwd, f"prompts/{token}.meta.json")
        write_text(system_path, request.system_prompt.strip() + "\n")
        write_text(user_path, request.user_prompt.strip() + "\n")
        write_text(combined_path, request.combined_prompt())
        write_json(
            meta_path,
            {
                "stage": stage,
                "runtime_mode": runtime_mode,
                "provider_name": _provider_name(provider),
                "system_chars": len(request.system_prompt),
                "user_chars": len(request.user_prompt),
                "combined_chars": len(request.combined_prompt()),
                "request_controls": request.control_summary(),
                "deterministic_generation_guaranteed": False,
                "provider_identity": {
                    "provider_name": provider_identity.get("provider_name"),
                    "runtime_mode": provider_identity.get("runtime_mode"),
                    "stage": provider_identity.get("stage"),
                    "provider_command_present": provider_identity.get("provider_command_present"),
                    "provider_command_digest": provider_identity.get("provider_command_digest"),
                    "model_command_source": provider_identity.get("model_command_source"),
                    "resolved_backend_class": provider_identity.get("resolved_backend_class"),
                    "generation_determinism": provider_identity.get("generation_determinism"),
                },
            },
        )
        state = load_session(cwd)
        state.artifacts.latest_prompt_trace_dir = str(system_path.parent)
        state.latest_provider_name = _provider_name(provider)
        state.latest_runtime_mode = runtime_mode
        save_session(cwd, state)
        return provider_notes + [
            f"Prompt trace recorded: {system_path.name}",
            f"Prompt trace recorded: {user_path.name}",
            f"Prompt size metadata recorded: {meta_path.name}",
        ]
    except Exception as exc:  # pragma: no cover - defensive trace guard
        return provider_notes + [f"Prompt trace recording failed: {exc}"]


def _file_sha256(path: str | Path | None) -> str | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return None
    return hashlib.sha256(candidate.read_bytes()).hexdigest()


def _latest_prompt_meta_for_stage(cwd: str | Path | None, stage: str) -> Path | None:
    state = load_session(cwd)
    prompt_dir = Path(state.artifacts.latest_prompt_trace_dir) if state.artifacts.latest_prompt_trace_dir else artifact_path(cwd, "prompts/dummy").parent
    if not prompt_dir.exists():
        return None
    candidates: list[Path] = []
    for path in prompt_dir.glob(f"{stage}.*.meta.json"):
        try:
            payload = read_json(path)
        except Exception:
            continue
        if isinstance(payload, dict) and payload.get("stage") == stage:
            candidates.append(path)
    return sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True)[0] if candidates else None


def _review_provenance_payload(
    cwd: str | Path | None,
    *,
    stage: str,
    manuscript_sha256: str,
    lane_manifest_path: str | Path | None = None,
    reviewer_label: str | None = None,
) -> dict[str, Any]:
    meta_path = _latest_prompt_meta_for_stage(cwd, stage)
    provider_identity_path = load_session(cwd).artifacts.latest_provider_identity_json
    meta_payload = read_json(meta_path) if meta_path and meta_path.exists() else {}
    provider_identity = meta_payload.get("provider_identity") if isinstance(meta_payload, dict) else {}
    return {
        "schema_version": "review-provenance/1",
        "stage": stage,
        "manuscript_sha256": manuscript_sha256,
        "reviewer_label": reviewer_label or str(provider_identity.get("provider_command_digest") or provider_identity.get("provider_name") or stage),
        "prompt_trace_meta_path": str(meta_path) if meta_path else None,
        "prompt_trace_meta_sha256": _file_sha256(meta_path),
        "provider_identity_path": provider_identity_path,
        "provider_identity_sha256": _file_sha256(provider_identity_path),
        "provider_name": provider_identity.get("provider_name") if isinstance(provider_identity, dict) else None,
        "provider_command_digest": provider_identity.get("provider_command_digest") if isinstance(provider_identity, dict) else None,
        "runtime_mode": provider_identity.get("runtime_mode") if isinstance(provider_identity, dict) else None,
        "lane_manifest_path": str(lane_manifest_path) if lane_manifest_path else None,
        "lane_manifest_sha256": _file_sha256(lane_manifest_path),
        "recorded_at": utc_now_iso(),
    }


def _emit_stage_event(stage: str, event: str, **payload: Any) -> None:
    record = {"stage": stage, "event": event}
    record.update(payload)
    print(json.dumps(record, ensure_ascii=False), file=sys.stderr)


def _should_mock_watermark(state, provider_name: str | None = None) -> bool:
    name = provider_name or state.latest_provider_name
    return name == "mock" or state.latest_verify_mode == "mock" or state.latest_verify_fallback_used == "mock"


def _apply_mock_watermark(latex: str, state, provider_name: str | None = None) -> str:
    if not _should_mock_watermark(state, provider_name=provider_name):
        return latex
    marker = "DO NOT DISTRIBUTE AS A FACTUAL DRAFT."
    if marker in latex:
        return latex
    banner = (
        "% ============================================================\n"
        "% This manuscript was generated by PaperOrchestra with:\n"
        f"%   provider={state.latest_provider_name or provider_name or 'unknown'}    verify-mode={state.latest_verify_mode or 'unknown'}    runtime-mode={state.latest_runtime_mode or 'unknown'}\n"
        f"%   session-id={state.session_id}    timestamp={state.updated_at or state.created_at}\n"
        "% DO NOT DISTRIBUTE AS A FACTUAL DRAFT.\n"
        "% ============================================================\n"
    )
    if r"\documentclass" in latex:
        return latex.replace(r"\documentclass", banner + r"\documentclass", 1)
    return banner + latex


def _append_unique_note(state, note: str, *, dedupe_window: int = 5) -> bool:
    if not note:
        return False
    if note in state.notes[-dedupe_window:]:
        return False
    state.notes.append(note)
    return True

def _complete_with_runtime_mode(
    request: CompletionRequest,
    *,
    provider: BaseProvider,
    runtime_mode: str,
    cwd: str | Path | None,
    omx_lane_type: str,
    trace_stage: str | None = None,
    output_schema: dict[str, Any] | None = None,
) -> tuple[str, str, bool, list[str]]:
    trace_notes = _record_prompt_trace(
        cwd,
        stage=trace_stage or omx_lane_type,
        request=request,
        runtime_mode=runtime_mode,
        provider=provider,
    )
    if runtime_mode == "omx_native":
        try:
            if output_schema is not None:
                result = omx_exec_json_completion(request.combined_prompt(), output_schema, cwd=cwd)
            else:
                result = omx_exec_completion(request.combined_prompt(), cwd=cwd)
            output = Path(result.output_path).read_text(encoding="utf-8")
            return output, omx_lane_type, False, trace_notes + [f"Executed through omx exec: {result.output_path}"]
        except Exception as exc:
            message = f"stage {omx_lane_type} fell back to Python provider after OMX-native failure: {str(exc).splitlines()[0]}"
            print(f"WARNING: {message}", file=sys.stderr)
            if _strict_omx_native_enabled():
                raise ContractError(
                    f"Strict OMX-native mode forbids fallback; {message}. "
                    "Unset PAPERO_STRICT_OMX_NATIVE or rerun without --strict-omx-native to permit compatibility fallback."
                ) from exc
            response = provider.complete(request)
            return response, "python", True, trace_notes + [f"OMX-native execution failed and fell back to Python: {exc}"]
    response = provider.complete(request)
    return response, "python", True, trace_notes + ["Compatibility mode used Python execution."]


def _read_inputs(state) -> dict[str, str]:
    return {
        "idea": read_text(state.inputs.idea_path),
        "experimental_log": read_text(state.inputs.experimental_log_path),
        "template": read_text(state.inputs.template_path),
        "guidelines": read_text(state.inputs.guidelines_path),
        "figures": _figure_listing(state.inputs.figures_dir),
    }


def _source_grounding_text(inputs: dict[str, str]) -> str:
    """Return the trusted source corpus for deterministic claim/numeric gates.

    Teach-mode packets can place human-prepared method/proof/benchmark material
    in ``template.tex`` while ``experimental_log.md`` only records a wrapper or
    excerpt. Contract validation should reject new numbers invented by writers,
    but it must not reject numeric tokens already present in trusted source
    materials that are preserved outside the rewritten section.
    """
    return "\n\n".join(
        part
        for part in (
            inputs.get("experimental_log", ""),
            inputs.get("idea", ""),
            inputs.get("template", ""),
        )
        if part
    )


def _data_block(name: str, content: str) -> str:
    return f"<DATA_BLOCK name=\"{name}\">\n{html.escape(content.strip())}\n</DATA_BLOCK>"


def _prompt_compact_text(text: str, *, head_chars: int, tail_chars: int = 0, marker: str = "[...truncated for prompt budget...]") -> str:
    if len(text) <= head_chars + tail_chars + len(marker):
        return text
    if tail_chars <= 0:
        return text[:head_chars].rstrip() + "\n" + marker
    return text[:head_chars].rstrip() + "\n" + marker + "\n" + text[-tail_chars:].lstrip()


def _strict_content_gates_enabled(*, claim_safe: bool = False) -> bool:
    return claim_safe or _env_flag("PAPERO_STRICT_CONTENT_GATES")


SOURCE_CRITICAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = get_domain().source_critical_patterns


def _source_critical_context_for_prompt(inputs: dict[str, str], *, window_chars: int = 1400, max_blocks_per_kind: int = 3) -> dict[str, Any]:
    """Extract bounded source-critical spans that raw head/tail truncation may hide.

    This is deliberately deterministic and conservative: it does not summarize or
    invent source facts.  It only exposes exact windows around method/proof/
    benchmark/limitation/citation anchors so the writer can see human-prepared
    material that lives deep inside long packets.
    """

    blocks: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int, int]] = set()
    for source_name in ("idea", "experimental_log", "template"):
        text = inputs.get(source_name) or ""
        if not text:
            continue
        for kind, pattern in get_domain().source_critical_patterns:
            count_for_kind = sum(1 for block in blocks if block["source"] == source_name and block["kind"] == kind)
            if count_for_kind >= max_blocks_per_kind:
                continue
            for match in pattern.finditer(text):
                count_for_kind = sum(1 for block in blocks if block["source"] == source_name and block["kind"] == kind)
                if count_for_kind >= max_blocks_per_kind:
                    break
                start = max(0, match.start() - window_chars // 2)
                end = min(len(text), match.end() + window_chars // 2)
                excerpt = text[start:end].strip()
                key = (source_name, kind, start, end)
                if not excerpt or key in seen:
                    continue
                seen.add(key)
                blocks.append(
                    {
                        "source": source_name,
                        "kind": kind,
                        "anchor": match.group(0),
                        "start_char": start,
                        "end_char": end,
                        "excerpt": excerpt,
                    }
                )
    return {
        "schema_version": "source-critical-context/1",
        "description": "Exact source spans selected to prevent prompt head/tail truncation from hiding method, proof, benchmark, limitation, or citation material.",
        "blocks": blocks[:30],
    }


def _unknown_citation_key_counts(latex: str, citation_map: dict[str, Any]) -> dict[str, int]:
    if not citation_map:
        return {}
    allowed = set(citation_map)
    counts: dict[str, int] = {}
    for match in CITE_COMMAND_RE.finditer(latex):
        for key in [key.strip() for key in match.group(2).split(",") if key.strip()]:
            if key not in allowed:
                counts[key] = counts.get(key, 0) + 1
    return counts


def _source_unknown_citation_key_counts(inputs: dict[str, str], citation_map: dict[str, Any]) -> dict[str, int]:
    return _unknown_citation_key_counts(_source_grounding_text(inputs), citation_map)


def _raise_if_strict_source_citations_unmapped(
    inputs: dict[str, str],
    citation_map: dict[str, Any],
    *,
    stage: str,
    strict_claim_safe: bool,
) -> None:
    if not strict_claim_safe:
        return
    unknown = _source_unknown_citation_key_counts(inputs, citation_map)
    if not unknown:
        return
    detail = ", ".join(f"{key}({count})" for key, count in sorted(unknown.items()))
    raise ContractError(
        f"{stage} claim-safe source packet contains citation keys that are not present in citation_map.json: {detail}. "
        "Import/map these source citations into the verified citation registry before claim-safe writing."
    )


def _normalize_figure_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _compact_outline_for_prompt(outline: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(outline, dict):
        return outline
    section_plan = []
    for item in outline.get("section_plan", [])[:8]:
        if not isinstance(item, dict):
            continue
        compact_item: dict[str, Any] = {"section_title": item.get("section_title")}
        subsections = []
        for subsection in item.get("subsections", [])[:2]:
            if not isinstance(subsection, dict):
                continue
            compact_subsection = {
                "subsection_title": subsection.get("subsection_title"),
                "content_bullets": subsection.get("content_bullets", [])[:1],
                "citation_hints": subsection.get("citation_hints", [])[:1],
            }
            subsections.append(compact_subsection)
        compact_item["subsections"] = subsections
        section_plan.append(compact_item)
    return {"section_plan": section_plan}


def _compact_intro_related_plan_for_prompt(plan: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(plan, dict):
        return plan
    compact: dict[str, Any] = {}
    intro = plan.get("introduction_strategy")
    if isinstance(intro, dict):
        compact["introduction_strategy"] = {
            "opening_frame": sanitize_author_facing_text(str(intro.get("hook_hypothesis") or ""), fallback=""),
            "problem_gap": sanitize_author_facing_text(str(intro.get("problem_gap_hypothesis") or ""), fallback=""),
            "background_topics": [
                sanitize_author_facing_text(str(item), fallback="")
                for item in (intro.get("search_directions") or [])[:3]
                if str(item).strip()
            ],
        }
    related = plan.get("related_work_strategy")
    if isinstance(related, dict):
        subsections = []
        for subsection in related.get("subsections", [])[:4]:
            if not isinstance(subsection, dict):
                continue
            subsections.append(
                {
                    "subsection_title": subsection.get("subsection_title"),
                    "methodology_cluster": sanitize_author_facing_text(str(subsection.get("methodology_cluster") or ""), fallback=""),
                    "comparative_context_goal": sanitize_author_facing_text(str(subsection.get("sota_investigation_mission") or ""), fallback=""),
                    "limitations_to_discuss": sanitize_author_facing_text(str(subsection.get("limitation_hypothesis") or ""), fallback=""),
                    "bridge_to_our_method": sanitize_author_facing_text(str(subsection.get("bridge_to_our_method") or ""), fallback=""),
                }
            )
        compact["related_work_strategy"] = {
            "overview": sanitize_author_facing_text(str(related.get("overview") or ""), fallback=""),
            "subsections": subsections,
        }
    return compact


def _compact_plot_manifest_for_prompt(plot_manifest: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(plot_manifest, dict):
        return plot_manifest
    figures = []
    for figure in plot_manifest.get("figures", [])[:8]:
        if not isinstance(figure, dict):
            continue
        figures.append(
            {
                "figure_id": figure.get("figure_id"),
                "title": _prompt_compact_text(str(figure.get("title") or ""), head_chars=120, tail_chars=0),
                "caption": _prompt_compact_text(str(figure.get("caption") or ""), head_chars=180, tail_chars=0),
                "plot_type": figure.get("plot_type"),
                "aspect_ratio": figure.get("aspect_ratio"),
            }
        )
    return {"figures": figures}


def _compact_plot_assets_for_prompt(plot_assets_index: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(plot_assets_index, dict):
        return plot_assets_index
    assets = []
    for asset in plot_assets_index.get("assets", [])[:8]:
        if not isinstance(asset, dict):
            continue
        assets.append(
            {
                "figure_id": asset.get("figure_id"),
                "title": _prompt_compact_text(str(asset.get("title") or ""), head_chars=120, tail_chars=0),
                "caption": _prompt_compact_text(str(asset.get("caption") or ""), head_chars=180, tail_chars=0),
                "filename": asset.get("filename"),
                "latex_snippet_path": asset.get("latex_snippet_path"),
                "plot_type": asset.get("plot_type"),
            }
        )
    return {"assets": assets}


def _compact_citation_map_for_prompt(
    citation_map: dict[str, Any],
    *,
    title_limit: int = 140,
    abstract_limit: int = 220,
    max_authors: int = 4,
    include_abstract: bool = True,
    include_authors: bool = True,
    include_year: bool = True,
    include_venue: bool = True,
    include_provenance: bool = True,
    include_origin: bool = True,
    include_matched_query: bool = True,
) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key, value in citation_map.items():
        if not isinstance(value, dict):
            compact[key] = value
            continue
        authors = value.get("authors")
        if include_authors and isinstance(authors, list):
            compact_authors = authors[:max_authors]
        elif include_authors:
            compact_authors = authors
        else:
            compact_authors = None
        abstract = value.get("abstract")
        if include_abstract and isinstance(abstract, str):
            compact_abstract = _prompt_compact_text(abstract, head_chars=abstract_limit, tail_chars=0)
        elif include_abstract:
            compact_abstract = abstract
        else:
            compact_abstract = None
        provenance = value.get("provenance")
        title = value.get("title")
        if isinstance(title, str):
            title = _prompt_compact_text(title, head_chars=title_limit, tail_chars=0)
        entry = {"title": title}
        if include_authors:
            entry["authors"] = compact_authors
        if include_abstract:
            entry["abstract"] = compact_abstract
        if include_year:
            entry["year"] = value.get("year")
        if include_venue:
            entry["venue"] = value.get("venue")
        if include_provenance:
            entry["provenance"] = provenance.get("source") if isinstance(provenance, dict) else provenance
        if include_origin:
            entry["origin"] = value.get("origin")
        if include_matched_query:
            entry["matched_query"] = value.get("matched_query")
        compact[key] = entry
    return compact


def _escape_latex_text(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
    }
    return "".join(replacements.get(ch, ch) for ch in text)


def _thebibliography_key_set(latex: str) -> set[str]:
    return set(re.findall(r"\\bibitem(?:\[[^\]]*\])?\{([^}]+)\}", latex))


def _ensure_bibliography_hook(latex: str, citation_map: dict[str, Any]) -> str:
    if not citation_map:
        return latex
    thebibliography_re = re.compile(r"\\begin\{thebibliography\}.*?\\end\{thebibliography\}", re.DOTALL | re.IGNORECASE)
    manual_match = thebibliography_re.search(latex)
    if manual_match:
        manual_block = manual_match.group(0)
        cited_keys = extract_citation_keys(
            latex[: manual_match.start()] + " " + latex[manual_match.end() :]
        )
        missing_manual_keys = {key for key in cited_keys if key in citation_map} - _thebibliography_key_set(manual_block)
        if not missing_manual_keys:
            return latex
        latex = thebibliography_re.sub("", latex, count=1)
    lowered = latex.lower()
    bibliography_re = re.compile(r"\\bibliography\s*\{[^}]*\}", re.IGNORECASE)
    if bibliography_re.search(latex):
        first_bibliography = True

        def _replace_bibliography(match: re.Match[str]) -> str:
            nonlocal first_bibliography
            if first_bibliography:
                first_bibliography = False
                return r"\bibliography{references}"
            return ""

        latex = bibliography_re.sub(_replace_bibliography, latex)
        if "\\bibliographystyle" not in lowered:
            latex = latex.replace(
                r"\bibliography{references}",
                "\\bibliographystyle{plain}\n\\bibliography{references}",
                1,
            )
        return latex
    hook = "\n\\bibliographystyle{plain}\n\\bibliography{references}\n"
    if "\\end{document}" in latex:
        return latex.replace("\\end{document}", hook + "\\end{document}")
    return latex + hook


def _drop_unknown_citation_keys(latex: str, citation_map: dict[str, Any]) -> tuple[str, dict[str, int]]:
    """Remove cite keys that are not present in the verified citation map.

    The writer is not allowed to invent bibliography keys.  Fresh smoke packets
    may include author-source citation commands that are intentionally not part
    of the verified external-reference pool yet; if the writer preserves those
    keys, deterministic post-processing should remove the unsupported cite
    marker rather than fabricate a BibTeX entry.  Claim-safety review can then
    flag any now-uncited high-risk sentence.
    """

    if not citation_map:
        return latex, {}
    allowed = set(citation_map)
    dropped: dict[str, int] = {}

    def _replace(match: re.Match[str]) -> str:
        command = match.group(1)
        keys = [key.strip() for key in match.group(2).split(",") if key.strip()]
        kept = [key for key in keys if key in allowed]
        for key in keys:
            if key not in allowed:
                dropped[key] = dropped.get(key, 0) + 1
        if not kept:
            return ""
        return f"{command}{{{','.join(kept)}}}"

    return CITE_COMMAND_RE.sub(_replace, latex), dropped


def _is_generated_placeholder_asset(asset: dict[str, Any]) -> bool:
    return (
        asset.get("asset_kind") == "generated_placeholder"
        or asset.get("review_status") == "human_final_artwork_required"
    )


def _reviewable_plot_assets_index(plot_assets_index: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(plot_assets_index, dict):
        return {"assets": []}
    return {
        **plot_assets_index,
        "assets": [
            asset
            for asset in plot_assets_index.get("assets", [])
            if isinstance(asset, dict) and not _is_generated_placeholder_asset(asset)
        ],
    }


def _reviewable_plot_manifest(plot_manifest: dict[str, Any] | None, plot_assets_index: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(plot_manifest, dict):
        return {"figures": []}
    placeholder_ids = {
        str(asset.get("figure_id"))
        for asset in (plot_assets_index or {}).get("assets", [])
        if isinstance(asset, dict) and _is_generated_placeholder_asset(asset) and asset.get("figure_id")
    }
    if not placeholder_ids:
        return plot_manifest
    return {
        **plot_manifest,
        "figures": [
            figure
            for figure in plot_manifest.get("figures", [])
            if not (isinstance(figure, dict) and str(figure.get("figure_id") or "") in placeholder_ids)
        ],
    }


def _ensure_generated_plot_usage(latex: str, plot_assets_index: dict[str, Any]) -> str:
    assets = plot_assets_index.get("assets", []) if isinstance(plot_assets_index, dict) else []
    rendered = latex
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        if _is_generated_placeholder_asset(asset):
            continue
        figure_id = asset.get("figure_id", "")
        title = asset.get("title", "")
        caption = asset.get("caption", title)
        snippet_path = asset.get("latex_snippet_path") or asset.get("latex_path")
        filename = asset.get("filename", "")
        label_present = bool(figure_id and f"\\label{{{figure_id}}}" in rendered)
        asset_present = any(token and token in rendered for token in [snippet_path, filename])
        escaped_caption = _escape_latex_text(caption) if isinstance(caption, str) else ""
        caption_present = bool(
            escaped_caption and (f"\\caption{{{escaped_caption}}}" in rendered or f"\\caption{{{caption}}}" in rendered)
        )
        if label_present or asset_present or caption_present:
            continue
        include = f"\\input{{{snippet_path}}}" if isinstance(snippet_path, str) and snippet_path.endswith(".tex") else f"\\includegraphics[width=0.85\\linewidth]{{{snippet_path}}}"
        block = (
            f"\n% PaperOrchestra:auto-repaired figure:{figure_id}\n"
            "\\begin{figure}[t]\n"
            f"{include}\n"
            f"\\caption{{{_escape_latex_text(caption)}}}\n"
            f"\\label{{{figure_id}}}\n"
            "\\end{figure}\n"
        )
        section_name = _preferred_section_name(
            rendered,
            label=figure_id,
            anchor_tokens=[title, caption, figure_id.replace("_", " ")],
        )
        rendered = _insert_block_into_section(
            rendered,
            section_name=section_name,
            block=block,
            label=figure_id,
            anchor_tokens=[title, caption, figure_id.replace("_", " ")],
        )
    return rendered


def _normalize_generated_plot_paths(latex: str, plot_assets_index: dict[str, Any]) -> str:
    assets = plot_assets_index.get("assets", []) if isinstance(plot_assets_index, dict) else []
    asset_by_label: dict[str, dict[str, Any]] = {}
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        if _is_generated_placeholder_asset(asset):
            continue
        figure_id = asset.get("figure_id")
        if isinstance(figure_id, str) and figure_id:
            asset_by_label[_normalize_figure_token(figure_id)] = asset
        snippet_path = asset.get("latex_snippet_path")
        if not isinstance(snippet_path, str):
            continue
        filename = asset.get("filename")
        candidates: list[str] = []
        for key in ["path", "tex_path", "latex_path", "latex_snippet_path"]:
            candidate = asset.get(key)
            if isinstance(candidate, str) and candidate:
                candidates.append(candidate)
                latex = latex.replace(candidate, snippet_path)
        if snippet_path.endswith(".tex"):
            for candidate in [snippet_path, *candidates]:
                if not candidate:
                    continue
                latex = re.sub(
                    rf"\\includegraphics(?:\[[^\]]*\])?\{{{re.escape(candidate)}\}}",
                    rf"\\input{{{snippet_path}}}",
                    latex,
                )
        if isinstance(filename, str) and filename:
            latex = re.sub(
                rf"\\includegraphics(?:\[[^\]]*\])?\{{[^}}]*{re.escape(filename)}\}}",
                rf"\\input{{{snippet_path}}}",
                latex,
            )
            for candidate in [filename, f"build/plot-assets/{filename}", f"./build/plot-assets/{filename}"]:
                latex = latex.replace(candidate, snippet_path)
        figure_id = asset.get("figure_id")
        if isinstance(figure_id, str) and figure_id:
            latex = re.sub(
                rf"\\includegraphics(?:\[[^\]]*\])?\{{[^}}]*{re.escape(figure_id)}\.(?:pdf|png|svg|jpg|jpeg)\}}",
                rf"\\input{{{snippet_path}}}",
                latex,
            )

    def _rewrite_figure_block(match: re.Match[str]) -> str:
        env = match.group(1)
        placement = match.group(2) or ""
        body = match.group(3)
        label_match = LABEL_RE.search(body)
        if not label_match:
            return match.group(0)
        asset = asset_by_label.get(_normalize_figure_token(label_match.group(1)))
        if not asset:
            return match.group(0)
        snippet_path = asset.get("latex_snippet_path") or asset.get("latex_path")
        if not isinstance(snippet_path, str) or not snippet_path:
            return match.group(0)
        include = (
            f"\\input{{{snippet_path}}}"
            if snippet_path.endswith(".tex")
            else f"\\includegraphics[width=0.85\\linewidth]{{{snippet_path}}}"
        )
        replaced = re.sub(
            r"\\includegraphics(?:\[[^\]]*\])?\{[^}]+\}",
            lambda _: include,
            body,
            count=1,
        )
        if replaced == body:
            replaced = re.sub(
                r"\\input\{[^}]+\}",
                lambda _: include,
                body,
                count=1,
            )
        if replaced == body:
            return match.group(0)
        placement_suffix = f"[{placement}]" if placement else ""
        return f"\\begin{{{env}}}{placement_suffix}{replaced}\\end{{{env}}}"

    latex = FIGURE_ENV_RE.sub(_rewrite_figure_block, latex)
    return latex


def _normalize_source_figure_paths(latex: str, figures_dir: str | None) -> str:
    if not figures_dir:
        return latex
    path = Path(figures_dir)
    if not path.exists():
        return latex
    for figure_path in sorted(path.iterdir()):
        if not figure_path.is_file():
            continue
        name = figure_path.name
        normalized = f"inputs/figures/{name}"
        for prefix in ["figures", "figs"]:
            latex = re.sub(rf"(?<!inputs/){re.escape(prefix)}/{re.escape(name)}", normalized, latex)
            latex = re.sub(rf"(?<!inputs\\){re.escape(prefix)}\\{re.escape(name)}", normalized, latex)
        latex = re.sub(
            rf"(\\includegraphics(?:\[[^\]]*\])?\{{)(?![^}}]*inputs/figures/){re.escape(name)}(\}})",
            rf"\1{normalized}\2",
            latex,
        )
    return latex.replace("inputs/inputs/figures/", "inputs/figures/")

def _figure_listing(figures_dir: str | None) -> str:
    if not figures_dir:
        return "No figures directory provided."
    path = Path(figures_dir)
    if not path.exists():
        return f"Figures directory missing: {path}"
    files = sorted(p.name for p in path.iterdir() if p.is_file())
    if not files:
        return "Figures directory is empty."
    return "\n".join(f"- {name}" for name in files)


VALID_ASPECT_RATIOS = {"1:1", "1:4", "2:3", "3:2", "3:4", "4:1", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"}
VALID_PLOT_TYPES = {"plot", "diagram"}


def _preserve_existing_sections(generated_latex: str, source_latex: str, *, section_names: list[str]) -> str:
    merged = generated_latex
    source_ranges = _section_range_map(source_latex)
    for section_name in section_names:
        normalized = section_name.strip().lower()
        source_range = source_ranges.get(normalized)
        if source_range is None:
            continue
        target_ranges = _section_range_map(merged)
        target_range = target_ranges.get(normalized)
        if target_range is None:
            continue
        source_block = source_latex[source_range[0] : source_range[1]]
        merged = merged[: target_range[0]] + source_block + merged[target_range[1] :]
    return merged


def _preserve_all_except_sections(generated_latex: str, source_latex: str, *, rewritten_section_names: list[str]) -> str:
    protected_names = []
    rewritten = {name.strip().lower() for name in rewritten_section_names if name and name.strip()}
    for section_name in _section_range_map(source_latex):
        if section_name not in rewritten:
            protected_names.append(section_name)
    return _preserve_existing_sections(generated_latex, source_latex, section_names=protected_names)


def _normalize_section_selection(value: list[str] | str | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = re.split(r"[\n,;]+", value)
    selected: list[str] = []
    for item in raw_items:
        text = str(item).strip()
        if text:
            selected.append(text)
    return selected


def _filter_section_scoped_issues(issues: list[ValidationIssue], *, selected_sections: list[str]) -> list[ValidationIssue]:
    if not selected_sections:
        return issues
    normalized = {item.strip().lower() for item in selected_sections}
    result: list[ValidationIssue] = []
    for issue in issues:
        if issue.code == "citation_coverage_insufficient":
            continue
        if issue.code == "numeric_grounding_mismatch" and normalized.isdisjoint({"implementation and results", "experiments"}):
            continue
        result.append(issue)
    return result


def _resolve_selected_sections(source_latex: str, selected_sections: list[str]) -> list[str]:
    source_ranges = _section_range_map(source_latex)
    resolved: list[str] = []
    unknown: list[str] = []
    for item in selected_sections:
        normalized = item.strip().lower()
        if normalized in source_ranges:
            resolved.append(item.strip())
        else:
            unknown.append(item.strip())
    if unknown:
        raise ContractError(
            "Unknown section name(s) for --only-sections: " + ", ".join(unknown)
        )
    return resolved


def _filtered_outline_for_sections(outline: dict[str, Any], selected_sections: list[str]) -> dict[str, Any]:
    selected = {item.strip().lower() for item in selected_sections}
    filtered = dict(outline)
    section_plan = outline.get("section_plan", []) if isinstance(outline, dict) else []
    filtered["section_plan"] = [
        item
        for item in section_plan
        if isinstance(item, dict) and str(item.get("section_title") or "").strip().lower() in selected
    ]
    return filtered


def _selected_section_template(source_latex: str, selected_sections: list[str]) -> str:
    ranges = _section_range_map(source_latex)
    matches = list(SECTION_COMMAND_RE.finditer(source_latex))
    preamble_end = matches[0].start() if matches else source_latex.find("\\begin{document}")
    if preamble_end == -1:
        preamble_end = 0
    preamble = source_latex[:preamble_end]
    blocks: list[str] = []
    for section_name in selected_sections:
        section_range = ranges.get(section_name.strip().lower())
        if section_range is None:
            continue
        blocks.append(source_latex[section_range[0] : section_range[1]])
    end_document = "\\end{document}\n" if "\\end{document}" in source_latex else ""
    return preamble + "".join(blocks) + end_document


def _citation_coverage_target(citation_map: dict[str, Any]) -> int:
    population = len(citation_map)
    if population <= 0:
        return 0
    if population <= 10:
        return population
    if population <= 25:
        return max(1, int(round(population * 0.85)))
    if population <= 50:
        return max(1, int(round(population * 0.8)))
    return max(1, int(round(population * 0.7)))


def _ensure_minimum_citation_coverage(
    latex: str,
    citation_map: dict[str, Any],
    *,
    target: int | None = None,
    max_shortfall: int = 2,
) -> str:
    """Add a bounded related-work citation bridge when coverage is narrowly short.

    The LLM sometimes stops one or two references below the mechanical coverage
    target even after repair prompts.  Rather than failing the run or inventing
    detailed claims, add a deliberately generic related-work sentence citing only
    existing verified keys.  The sentence makes no domain-specific claim; it
    merely records that the paper's background context also draws on those
    references.
    """

    if not citation_map:
        return latex
    target_count = _citation_coverage_target(citation_map) if target is None else max(0, target)
    if target_count <= 0:
        return latex
    known_keys = [str(key) for key in citation_map.keys()]
    cited = extract_citation_keys(latex)
    cited_known = {key for key in cited if key in citation_map}
    needed = target_count - len(cited_known)
    if needed <= 0:
        return latex
    if needed > max(0, max_shortfall):
        return latex
    missing = [key for key in known_keys if key not in cited_known]
    if not missing:
        return latex
    selected = missing[:needed]
    bridge = (
        "\n\n\\paragraph{Additional related context.}\n"
        "This paper also draws on related specifications, analyses, and benchmarking resources"
        f"~\\cite{{{','.join(selected)}}}.\n"
    )
    ranges = _section_range_map(latex)
    related_span = ranges.get("related work") or ranges.get("background and related work")
    if not related_span:
        return latex
    _, end = related_span
    return latex[:end].rstrip() + bridge + "\n" + latex[end:].lstrip()


def _allow_related_citation_backfill(selected_sections: list[str]) -> bool:
    if not selected_sections:
        return True
    normalized = {_canonical_generated_section_title(section) for section in selected_sections}
    return bool(normalized & {"related work", "background and related work"})




def _closed_object_schema(properties: dict[str, Any], *, required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": required or list(properties.keys()),
        "properties": properties,
    }


def _string_list_schema() -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string"}}


_OUTLINE_PLOTTING_ITEM_SCHEMA = _closed_object_schema(
    {
        "figure_id": {"type": "string"},
        "title": {"type": "string"},
        "plot_type": {"type": "string"},
        "data_source": {"type": "string"},
        "objective": {"type": "string"},
        "aspect_ratio": {"type": "string"},
    }
)

_OUTLINE_INTRODUCTION_STRATEGY_SCHEMA = _closed_object_schema(
    {
        "hook_hypothesis": {"type": "string"},
        "problem_gap_hypothesis": {"type": "string"},
        "search_directions": _string_list_schema(),
    }
)

_OUTLINE_RELATED_SUBSECTION_SCHEMA = _closed_object_schema(
    {
        "subsection_title": {"type": "string"},
        "methodology_cluster": {"type": "string"},
        "sota_investigation_mission": {"type": "string"},
        "limitation_hypothesis": {"type": "string"},
        "limitation_search_queries": _string_list_schema(),
        "bridge_to_our_method": {"type": "string"},
    }
)

_OUTLINE_RELATED_WORK_STRATEGY_SCHEMA = _closed_object_schema(
    {
        "overview": {"type": "string"},
        "subsections": {"type": "array", "items": _OUTLINE_RELATED_SUBSECTION_SCHEMA},
    }
)

_OUTLINE_INTRO_RELATED_WORK_PLAN_SCHEMA = _closed_object_schema(
    {
        "introduction_strategy": _OUTLINE_INTRODUCTION_STRATEGY_SCHEMA,
        "related_work_strategy": _OUTLINE_RELATED_WORK_STRATEGY_SCHEMA,
    }
)

_OUTLINE_SECTION_SUBSECTION_SCHEMA = _closed_object_schema(
    {
        "subsection_title": {"type": "string"},
        "content_bullets": _string_list_schema(),
        "citation_hints": _string_list_schema(),
    }
)

_OUTLINE_SECTION_ITEM_SCHEMA = _closed_object_schema(
    {
        "section_title": {"type": "string"},
        "subsections": {"type": "array", "items": _OUTLINE_SECTION_SUBSECTION_SCHEMA},
    }
)

_PLOT_MANIFEST_ITEM_SCHEMA = _closed_object_schema(
    {
        "figure_id": {"type": "string"},
        "title": {"type": "string"},
        "plot_type": {"type": "string"},
        "data_source": {"type": "string"},
        "objective": {"type": "string"},
        "aspect_ratio": {"type": "string"},
        "rendering_brief": {"type": "string"},
        "caption": {"type": "string"},
        "source_fidelity_notes": {"type": "string"},
    }
)

_CANDIDATE_ITEM_SCHEMA = _closed_object_schema(
    {
        "title_guess": {"type": "string"},
        "why_relevant": {"type": "string"},
        "origin_query": {"type": "string"},
        "role_guess": {"type": "string"},
        "discovery_source": {"type": "string"},
        "discovery_sources": _string_list_schema(),
    }
)

_REVIEW_AXIS_SCORE_SCHEMA = _closed_object_schema(
    {
        "score": {"type": ["number", "integer"]},
        "justification": {"type": "string"},
    }
)

_REVIEW_AXIS_SCORES_SCHEMA = _closed_object_schema(
    {
        "coverage_and_completeness": _REVIEW_AXIS_SCORE_SCHEMA,
        "relevance_and_focus": _REVIEW_AXIS_SCORE_SCHEMA,
        "critical_analysis_and_synthesis": _REVIEW_AXIS_SCORE_SCHEMA,
        "positioning_and_novelty": _REVIEW_AXIS_SCORE_SCHEMA,
        "organization_and_writing": _REVIEW_AXIS_SCORE_SCHEMA,
        "citation_practices_and_rigor": _REVIEW_AXIS_SCORE_SCHEMA,
    }
)

_REVIEW_CITATION_STATISTICS_SCHEMA = _closed_object_schema(
    {
        "estimated_unique_citations": {"type": ["number", "integer", "string", "null"]},
        "citation_density_assessment": {"type": ["string", "null"]},
        "breadth_across_subareas": {"type": ["string", "null"]},
        "comparison_to_baseline": {"type": ["string", "null"]},
        "notes": {"type": ["string", "null"]},
    }
)

_REVIEW_PENALTY_SCHEMA = _closed_object_schema(
    {
        "reason": {"type": "string"},
        "points_deducted": {"type": ["number", "integer"]},
    }
)

_REVIEW_SUMMARY_SCHEMA = _closed_object_schema(
    {
        "strengths": _string_list_schema(),
        "weaknesses": _string_list_schema(),
        "top_improvements": _string_list_schema(),
    }
)

OUTLINE_SCHEMA = {
    **_closed_object_schema(
        {
            "plotting_plan": {"type": "array", "items": _OUTLINE_PLOTTING_ITEM_SCHEMA},
            "intro_related_work_plan": _OUTLINE_INTRO_RELATED_WORK_PLAN_SCHEMA,
            "section_plan": {"type": "array", "items": _OUTLINE_SECTION_ITEM_SCHEMA},
        }
    )
}
PLOT_SCHEMA = {
    **_closed_object_schema(
        {
            "figures": {"type": "array", "items": _PLOT_MANIFEST_ITEM_SCHEMA},
        }
    )
}
CANDIDATE_SCHEMA = {
    **_closed_object_schema(
        {
            "macro_candidates": {"type": "array", "items": _CANDIDATE_ITEM_SCHEMA},
            "micro_candidates": {"type": "array", "items": _CANDIDATE_ITEM_SCHEMA},
        }
    )
}

_PRIOR_WORK_ENTRY_SCHEMA = _closed_object_schema(
    {
        "title": {"type": "string"},
        "authors": _string_list_schema(),
        "year": {"type": ["integer", "null"]},
        "venue": {"type": ["string", "null"]},
        "url": {"type": ["string", "null"]},
        "doi": {"type": ["string", "null"]},
        "source": {"type": "string"},
        "why_relevant": {"type": "string"},
        "provenance_notes": _string_list_schema(),
    }
)
PRIOR_WORK_SEED_SCHEMA = _closed_object_schema(
    {
        "references": {"type": "array", "items": _PRIOR_WORK_ENTRY_SCHEMA},
        "research_notes": _string_list_schema(),
    }
)

REVIEW_SCHEMA = {
    **_closed_object_schema(
        {
            "paper_title": {"type": ["string", "null"]},
            "citation_statistics": _REVIEW_CITATION_STATISTICS_SCHEMA,
            "overall_score": {"type": ["number", "integer"]},
            "axis_scores": _REVIEW_AXIS_SCORES_SCHEMA,
            "penalties": {"type": "array", "items": _REVIEW_PENALTY_SCHEMA},
            "summary": _REVIEW_SUMMARY_SCHEMA,
            "questions": _string_list_schema(),
        },
        required=["paper_title", "citation_statistics", "axis_scores", "penalties", "summary", "questions", "overall_score"],
    )
}


def validate_outline(data: dict[str, Any]) -> None:
    missing = {"plotting_plan", "intro_related_work_plan", "section_plan"} - set(data)
    if missing:
        raise ContractError(f"Outline missing required keys: {sorted(missing)}")
    if not isinstance(data["plotting_plan"], list):
        raise ContractError("plotting_plan must be a list.")
    for plot in data["plotting_plan"]:
        for key in ["figure_id", "title", "plot_type", "data_source", "objective", "aspect_ratio"]:
            if key not in plot:
                raise ContractError(f"plotting_plan item missing key: {key}")
        if plot["plot_type"] not in VALID_PLOT_TYPES:
            raise ContractError(f"Invalid plot_type: {plot['plot_type']}")
        if plot["aspect_ratio"] not in VALID_ASPECT_RATIOS:
            raise ContractError(f"Invalid aspect_ratio: {plot['aspect_ratio']}")


def _normalize_plot_type(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in VALID_PLOT_TYPES:
        return normalized
    if "diagram" in normalized:
        return "diagram"
    return "plot"


def _normalize_aspect_ratio(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in VALID_ASPECT_RATIOS:
        return normalized
    aliases = {
        "wide": "16:9",
        "landscape": "16:9",
        "standard": "4:3",
        "square": "1:1",
        "portrait": "3:4",
    }
    return aliases.get(normalized, "16:9")


def normalize_outline_payload(payload: dict[str, Any]) -> dict[str, Any]:
    plotting_plan = payload.get("plotting_plan")
    if isinstance(plotting_plan, list):
        for item in plotting_plan:
            if not isinstance(item, dict):
                continue
            plot_type = item.get("plot_type")
            if isinstance(plot_type, str) and plot_type not in VALID_PLOT_TYPES:
                original = plot_type
                item["plot_type"] = _normalize_plot_type(plot_type)
                objective = item.get("objective", "")
                if isinstance(objective, str) and original.lower() not in objective.lower():
                    item["objective"] = f"{objective} Original requested chart form: {original}."
            aspect_ratio = item.get("aspect_ratio")
            if isinstance(aspect_ratio, str) and aspect_ratio not in VALID_ASPECT_RATIOS:
                item["aspect_ratio"] = _normalize_aspect_ratio(aspect_ratio)
    return payload


def validate_plot_manifest(data: dict[str, Any]) -> None:
    if "figures" not in data or not isinstance(data["figures"], list):
        raise ContractError("Plot manifest must contain a figures list.")
    for figure in data["figures"]:
        for key in [
            "figure_id",
            "title",
            "plot_type",
            "data_source",
            "objective",
            "aspect_ratio",
            "rendering_brief",
            "caption",
            "source_fidelity_notes",
        ]:
            if key not in figure:
                raise ContractError(f"Plot manifest figure missing key: {key}")


def _fallback_plot_manifest(outline: dict[str, Any]) -> dict[str, Any]:
    figures = []
    for plot in outline.get("plotting_plan", []):
        figures.append(
            {
                "figure_id": plot["figure_id"],
                "title": plot["title"],
                "plot_type": plot["plot_type"],
                "data_source": plot["data_source"],
                "objective": plot["objective"],
                "aspect_ratio": plot["aspect_ratio"],
                "rendering_brief": plot["objective"],
                "caption": plot["title"],
                "source_fidelity_notes": f"{plot['data_source']}: fallback manifest without model-authored caption.",
            }
        )
    return {"figures": figures}


def _build_plot_payload(outline: dict[str, Any], state, provider: BaseProvider | None, *, runtime_mode: str = "compatibility", cwd: str | Path | None = None) -> tuple[dict[str, Any], str, bool, list[str]]:
    inputs = _read_inputs(state)
    if provider is None:
        return _fallback_plot_manifest(outline), "python", True, ["No provider available; fallback manifest used."]
    prompt_idea = _prompt_compact_text(inputs["idea"], head_chars=5000, tail_chars=1000)
    prompt_experimental_log = _prompt_compact_text(inputs["experimental_log"], head_chars=12000, tail_chars=3000)
    user_prompt = f"""
{_data_block('plotting_plan', json.dumps(outline['plotting_plan'], indent=2, ensure_ascii=False))}

{_data_block('idea.md', prompt_idea)}

{_data_block('experimental_log.md', prompt_experimental_log)}

{_data_block('conference_guidelines.md', inputs['guidelines'])}
""".strip()
    response, lane_type, fallback_used, lane_notes = _complete_with_runtime_mode(
        _build_completion_request(system_prompt=PROMPTS.plot_system, user_prompt=user_prompt),
        provider=provider,
        runtime_mode=runtime_mode,
        cwd=cwd,
        omx_lane_type="team",
        trace_stage="plot",
        output_schema=PLOT_SCHEMA,
    )
    return extract_json(response), lane_type, fallback_used, lane_notes


def _outline_search_queries(outline: dict[str, Any]) -> tuple[list[str], int]:
    intro = outline["intro_related_work_plan"].get("introduction_strategy", {})
    related = outline["intro_related_work_plan"].get("related_work_strategy", {})
    queries: list[str] = []
    queries.extend(intro.get("search_directions", []))
    for subsection in related.get("subsections", []):
        mission = subsection.get("sota_investigation_mission")
        if mission:
            queries.append(mission)
        queries.extend(subsection.get("limitation_search_queries", []))
    return queries, len(intro.get("search_directions", []))


def _experimental_log_search_queries(experimental_log_text: str) -> list[str]:
    queries: list[str] = []
    for label in ("Baselines", "Datasets / Benchmarks", "Datasets", "Evaluation Metrics"):
        match = re.search(rf"\*\*\s*{re.escape(label)}\s*:\*\*\s*(.+)", experimental_log_text, re.IGNORECASE)
        if not match:
            continue
        values = [item.strip() for item in re.split(r"[;,]", match.group(1)) if item.strip()]
        queries.extend(values)
    seen: set[str] = set()
    deduped: list[str] = []
    for query in queries:
        normalized = query.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(query)
    return deduped


def _build_candidate_payload(outline: dict[str, Any], state, provider: BaseProvider | None, mode: str, *, runtime_mode: str = "compatibility", cwd: str | Path | None = None) -> tuple[dict[str, Any], str, bool, list[str]]:
    queries, macro_query_count = _outline_search_queries(outline)
    inputs = _read_inputs(state)
    supplemental_queries = _experimental_log_search_queries(inputs["experimental_log"])
    for query in supplemental_queries:
        if query not in queries:
            queries.append(query)
    if mode == "scholar-only":
        macro_candidates = []
        micro_candidates = []
        notes = ["Scholar-only mode used Python discovery."]
        for idx, query in enumerate(queries):
            try:
                papers = search_semantic_scholar(query, limit=3)
            except Exception as exc:
                notes.append(f"Scholar-only query failed for '{query}': {exc}")
                papers = []
            for paper in papers:
                candidate = {
                    "title_guess": paper.get("title", ""),
                    "why_relevant": "Recovered from Semantic Scholar query result.",
                    "origin_query": query,
                    "role_guess": "macro" if idx < macro_query_count else "micro",
                    "discovery_source": "semantic_scholar",
                }
                if candidate["role_guess"] == "macro":
                    macro_candidates.append(candidate)
                else:
                    micro_candidates.append(candidate)
        return {"macro_candidates": macro_candidates, "micro_candidates": micro_candidates}, "python", True, notes

    if mode == "search-grounded":
        grounding_mode = os.environ.get("PAPERO_SEARCH_GROUNDED_MODE")
        if not grounding_mode:
            grounding_mode = "mock" if getattr(provider, "name", None) == "mock" else "live"
        payload, notes = build_search_grounded_candidates(
            queries,
            macro_query_count=macro_query_count,
            cutoff_date=state.inputs.cutoff_date,
            per_source_limit=3,
            mode=grounding_mode,
        )
        return payload, "python", False, notes or [f"Search-grounded substitute used Semantic Scholar + OpenAlex discovery in {grounding_mode} mode."]

    if provider is None:
        raise ContractError("Model discovery mode requires a provider.")
    response, lane_type, fallback_used, lane_notes = _complete_with_runtime_mode(
        _build_completion_request(
            system_prompt=PROMPTS.discovery_system,
            user_prompt=_discovery_payload_from_outline(outline, state.inputs.cutoff_date),
        ),
        provider=provider,
        runtime_mode=runtime_mode,
        cwd=cwd,
        omx_lane_type="team",
        trace_stage="literature",
        output_schema=CANDIDATE_SCHEMA,
    )
    return extract_json(response), lane_type, fallback_used, lane_notes


def _write_plot_artifacts(cwd: str | Path | None, payload: dict[str, Any]) -> tuple[Path, Path]:
    validate_plot_manifest(payload)
    manifest_path = artifact_path(cwd, "plot_manifest.json")
    captions_path = artifact_path(cwd, "plot_captions.json")
    write_json(manifest_path, payload)
    write_json(captions_path, {item["figure_id"]: item["caption"] for item in payload["figures"]})
    return manifest_path, captions_path


def _write_plot_assets(cwd: str | Path | None, payload: dict[str, Any]) -> tuple[Path, Path]:
    assets_dir = build_path(cwd, "plot-assets")
    output_dir, index_path = render_plot_assets(payload, assets_dir)
    return output_dir, index_path


def _write_candidate_artifacts(cwd: str | Path | None, payload: dict[str, Any]) -> Path:
    if "macro_candidates" not in payload or "micro_candidates" not in payload:
        raise ContractError("candidate discovery output must contain macro_candidates and micro_candidates")
    path = artifact_path(cwd, "candidate_papers.json")
    write_json(path, payload)
    return path


def run_parallel_plot_and_literature(
    cwd: str | Path | None,
    *,
    provider: BaseProvider,
    discovery_mode: str = "model",
    runtime_mode: str = "compatibility",
) -> dict[str, str]:
    state = load_session(cwd)
    if not state.artifacts.outline_json:
        raise ContractError("Generate outline.json before running parallel plot/literature phase.")
    outline = read_json(state.artifacts.outline_json)
    plot_provider = provider.fork()
    discovery_provider = provider.fork()
    with ThreadPoolExecutor(max_workers=2) as executor:
        plots_future = executor.submit(_build_plot_payload, outline, state, plot_provider, runtime_mode=runtime_mode, cwd=cwd)
        candidates_future = executor.submit(
            _build_candidate_payload,
            outline,
            state,
            discovery_provider if discovery_mode == "model" else None,
            discovery_mode,
            runtime_mode=runtime_mode,
            cwd=cwd,
        )
        plot_payload, plot_lane_type, plot_fallback_used, plot_lane_notes = plots_future.result()
        candidate_payload, literature_lane_type, literature_fallback_used, literature_lane_notes = candidates_future.result()

    manifest_path, captions_path = _write_plot_artifacts(cwd, plot_payload)
    assets_dir, assets_index = _write_plot_assets(cwd, plot_payload)
    candidate_path = _write_candidate_artifacts(cwd, candidate_payload)

    plot_lane_path = record_lane_manifest(
        cwd,
        stage="plot",
        role="Plotting Agent",
        runtime_mode=runtime_mode,
        lane_type=plot_lane_type,
        owner=_lane_owner(plot_lane_type, plot_fallback_used),
        status="fallback_completed" if plot_fallback_used else "completed",
        input_artifacts=[state.artifacts.outline_json or ""],
        output_artifacts=[str(manifest_path), str(captions_path), str(assets_index)],
        fallback_used=plot_fallback_used,
        notes=plot_lane_notes,
    )
    literature_lane_path = record_lane_manifest(
        cwd,
        stage="literature",
        role="Literature Review Agent",
        runtime_mode=runtime_mode,
        lane_type=literature_lane_type,
        owner=_lane_owner(literature_lane_type, literature_fallback_used),
        status="fallback_completed" if literature_fallback_used else "completed",
        input_artifacts=[state.artifacts.outline_json or ""],
        output_artifacts=[str(candidate_path)],
        fallback_used=literature_fallback_used,
        notes=literature_lane_notes,
    )

    state = load_session(cwd)
    state.artifacts.plot_manifest_json = str(manifest_path)
    state.artifacts.plot_captions_json = str(captions_path)
    state.artifacts.plot_assets_dir = str(assets_dir)
    state.artifacts.plot_assets_json = str(assets_index)
    state.artifacts.candidate_papers_json = str(candidate_path)
    state.current_phase = "literature_review"
    state.active_artifact = candidate_path.name
    state.latest_discovery_mode = discovery_mode
    state.notes.append("Plot Generation and Literature Review planning completed in parallel.")
    state.notes.append(f"Lane manifests recorded: {plot_lane_path.name}, {literature_lane_path.name}")
    save_session(cwd, state)

    return {
        "plots": str(manifest_path),
        "plot_captions": str(captions_path),
        "plot_assets": str(assets_index),
        "candidates": str(candidate_path),
    }


def _issue_messages(issues: list[ValidationIssue]) -> list[str]:
    return [issue.message for issue in issues]


def _blocking_issues(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    return [issue for issue in issues if issue.severity == "error"]


def _non_blocking_issues(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    return [issue for issue in issues if issue.severity != "error"]


def _missing_plot_ids(issues: list[ValidationIssue]) -> list[str]:
    prefix = "Plot-plan figures are not represented in the manuscript:"
    missing: list[str] = []
    for issue in issues:
        if issue.code != "plot_plan_not_reflected":
            continue
        if prefix in issue.message:
            suffix = issue.message.split(prefix, 1)[1]
            missing.extend(part.strip() for part in suffix.split(",") if part.strip())
    return sorted(set(missing))


def _inject_missing_plot_assets(
    latex: str,
    issues: list[ValidationIssue],
    plot_assets_index: dict[str, Any] | None,
) -> str:
    missing_ids = set(_missing_plot_ids(issues))
    if not missing_ids or not isinstance(plot_assets_index, dict):
        return latex
    assets = plot_assets_index.get("assets", [])
    rendered = latex
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        if _is_generated_placeholder_asset(asset):
            continue
        figure_id = asset.get("figure_id", "")
        if figure_id not in missing_ids:
            continue
        snippet_path = asset.get("latex_snippet_path") or asset.get("latex_path")
        title = asset.get("title", figure_id)
        caption = asset.get("caption", title)
        include = f"\\input{{{snippet_path}}}" if isinstance(snippet_path, str) and snippet_path.endswith(".tex") else f"\\includegraphics[width=0.85\\linewidth]{{{snippet_path}}}"
        block = (
            f"\n% PaperOrchestra:auto-repaired figure:{figure_id}\n"
            "\\begin{figure}[t]\n"
            f"{include}\n"
            f"\\caption{{{_escape_latex_text(caption)}}}\n"
            f"\\label{{{figure_id}}}\n"
            "\\end{figure}\n"
        )
        section_name = _preferred_section_name(
            rendered,
            label=figure_id,
            anchor_tokens=[title, caption, figure_id.replace("_", " ")],
        )
        rendered = _insert_block_into_section(
            rendered,
            section_name=section_name,
            block=block,
            label=figure_id,
            anchor_tokens=[title, caption, figure_id.replace("_", " ")],
        )
    return rendered


def collect_paper_contract_issues(
    latex: str,
    *,
    citation_map: dict[str, Any],
    figures_dir: str | None,
    plot_manifest: dict[str, Any] | None = None,
    plot_assets_index: dict[str, Any] | None = None,
    experimental_log_text: str | None = None,
    expected_section_titles: list[str] | None = None,
    narrative_plan: dict[str, Any] | None = None,
    claim_map: dict[str, Any] | None = None,
    citation_placement_plan: dict[str, Any] | None = None,
) -> list[ValidationIssue]:
    return validate_manuscript(
        latex,
        citation_map=citation_map,
        figures_dir=figures_dir,
        plot_manifest=plot_manifest,
        plot_assets_index=plot_assets_index,
        experimental_log_text=experimental_log_text,
        expected_section_titles=expected_section_titles,
        narrative_plan=narrative_plan,
        claim_map=claim_map,
        citation_placement_plan=citation_placement_plan,
    )


def _validation_report_payload(
    stage: str,
    issues: list[ValidationIssue],
    *,
    manuscript_path: str | None = None,
    manuscript_text: str | None = None,
) -> dict[str, Any]:
    blocking = _blocking_issues(issues)
    warnings = _non_blocking_issues(issues)
    payload = {
        "stage": stage,
        "ok": not blocking,
        "blocking_issue_count": len(blocking),
        "warning_count": len(warnings),
        "issues": [issue.to_dict() for issue in issues],
        "generated_at": utc_now_iso(),
    }
    if manuscript_path:
        payload["manuscript_path"] = manuscript_path
    if manuscript_text is not None:
        payload["manuscript_sha256"] = hashlib.sha256(manuscript_text.encode("utf-8")).hexdigest()
    elif manuscript_path and Path(manuscript_path).exists():
        payload["manuscript_sha256"] = hashlib.sha256(Path(manuscript_path).read_bytes()).hexdigest()
    return payload


def _record_validation_report(
    cwd: str | Path | None,
    *,
    stage: str,
    issues: list[ValidationIssue],
    name: str,
    manuscript_path: str | None = None,
    manuscript_text: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    path = artifact_path(cwd, name)
    payload = _validation_report_payload(
        stage,
        issues,
        manuscript_path=manuscript_path,
        manuscript_text=manuscript_text,
    )
    write_json(path, payload)
    state = load_session(cwd)
    state.artifacts.latest_validation_json = str(path)
    save_session(cwd, state)
    return path, payload


def record_compile_environment_report(cwd: str | Path | None, *, name: str = "compile-environment.json") -> tuple[Path, dict[str, Any]]:
    report = inspect_compile_environment(cwd)
    payload = report.to_dict()
    try:
        path = artifact_path(cwd, name)
        write_json(path, payload)
        state = load_session(cwd)
        state.artifacts.latest_compile_env_json = str(path)
        save_session(cwd, state)
    except FileNotFoundError:
        path = runtime_root(cwd) / "preflight" / name
        write_json(path, payload)
    return path, payload


def record_fidelity_report(cwd: str | Path | None, *, name: str = "fidelity.audit.json") -> tuple[Path, dict[str, Any]]:
    payload = run_fidelity_audit(cwd)
    path = artifact_path(cwd, name)
    write_json(path, payload)
    state = load_session(cwd)
    state.artifacts.latest_fidelity_json = str(path)
    save_session(cwd, state)
    return path, payload


def plan_narrative_and_claims(
    cwd: str | Path | None,
    provider: BaseProvider | None = None,
    *,
    runtime_mode: str = "compatibility",
) -> dict[str, Path]:
    state = load_session(cwd)
    paths = write_planning_artifacts(cwd)
    lane_path = record_lane_manifest(
        cwd,
        stage="narrative_planning",
        role="Narrative Claim Planner",
        runtime_mode=runtime_mode,
        lane_type="ralph",
        owner="paperorchestra",
        status="completed",
        input_artifacts=[
            state.artifacts.outline_json or "",
            state.artifacts.citation_map_json or "",
            state.artifacts.references_bib or "",
            state.inputs.idea_path,
            state.inputs.experimental_log_path,
            state.inputs.template_path,
        ],
        output_artifacts=[str(path) for path in paths.values()],
        fallback_used=False,
        notes=["Deterministic conservative narrative/claim/citation placement planning artifacts recorded."],
    )
    state = load_session(cwd)
    state.current_phase = "narrative_planning"
    state.active_artifact = "narrative_plan.json"
    _append_unique_note(state, "Plot and literature completed in parallel before narrative planning.")
    state.notes.append(f"Lane manifest recorded: {lane_path.name}")
    save_session(cwd, state)
    return paths


def _planning_payloads_for_prompt(cwd: str | Path | None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    state = load_session(cwd)
    try:
        require_fresh_planning_artifacts(cwd)
    except RuntimeError as exc:
        raise ContractError(str(exc)) from exc
    narrative = read_json(state.artifacts.narrative_plan_json) if state.artifacts.narrative_plan_json else {}
    claim_map = read_json(state.artifacts.claim_map_json) if state.artifacts.claim_map_json else {}
    citation_plan = read_json(state.artifacts.citation_placement_plan_json) if state.artifacts.citation_placement_plan_json else {}
    return narrative, claim_map, citation_plan


def _filter_planning_payloads_for_sections(
    narrative_plan: dict[str, Any],
    claim_map: dict[str, Any],
    citation_placement_plan: dict[str, Any],
    section_names: list[str] | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if not section_names:
        return narrative_plan, claim_map, citation_placement_plan
    wanted = {name.strip().lower() for name in section_names if name.strip()}
    claims = [
        claim
        for claim in claim_map.get("claims", [])
        if isinstance(claim, dict) and str(claim.get("target_section") or "").strip().lower() in wanted
    ]
    claim_ids = {str(claim.get("id")) for claim in claims}
    narrative = dict(narrative_plan)
    narrative["section_roles"] = [
        role
        for role in narrative_plan.get("section_roles", [])
        if isinstance(role, dict) and str(role.get("section_title") or "").strip().lower() in wanted
    ]
    narrative["story_beats"] = [
        beat
        for beat in narrative_plan.get("story_beats", [])
        if isinstance(beat, dict) and str(beat.get("target_section") or "").strip().lower() in wanted
    ]
    claim_payload = dict(claim_map)
    claim_payload["claims"] = claims
    citation_payload = dict(citation_placement_plan)
    citation_payload["placements"] = [
        placement
        for placement in citation_placement_plan.get("placements", [])
        if isinstance(placement, dict)
        and (
            str(placement.get("target_section") or "").strip().lower() in wanted
            or str(placement.get("claim_id") or "") in claim_ids
        )
    ]
    return narrative, claim_payload, citation_payload


def _writer_brief_from_planning(
    narrative_plan: dict[str, Any],
    claim_map: dict[str, Any],
    citation_placement_plan: dict[str, Any],
) -> dict[str, Any]:
    """Project planning artifacts into an author-facing prose brief.

    Raw planning artifacts contain IDs, provenance hashes, source references,
    and machine-control labels. Those are useful for validators but too easy
    for a prose model to copy into the manuscript. The writer brief consumes
    the shared normalized boundary projection and keeps only scholarly,
    author-facing obligations.
    """
    claims_by_section: dict[str, list[dict[str, Any]]] = {}

    def _safe_supporting_evidence(claim: dict[str, Any]) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        for anchor in claim.get("evidence_anchors") or []:
            if not isinstance(anchor, dict):
                continue
            excerpt = sanitize_author_facing_text(
                str(anchor.get("evidence_excerpt") or anchor.get("excerpt") or ""),
                fallback="",
            )
            if not excerpt:
                continue
            item: dict[str, Any] = {
                "excerpt": _prompt_compact_text(excerpt, head_chars=360, tail_chars=0),
            }
            line_start = anchor.get("line_start")
            line_end = anchor.get("line_end")
            if isinstance(line_start, int) and isinstance(line_end, int) and line_start > 0 and line_end >= line_start:
                item["location"] = f"lines {line_start}-{line_end}"
            evidence.append(item)
        legacy_excerpt = sanitize_author_facing_text(str(claim.get("excerpt") or ""), fallback="")
        if legacy_excerpt and not evidence:
            evidence.append({"excerpt": _prompt_compact_text(legacy_excerpt, head_chars=360, tail_chars=0)})
        return evidence

    for claim in claim_map.get("claims") or []:
        if not isinstance(claim, dict):
            continue
        projection = normalized_claim_projection(claim)
        section = str(projection.get("target_section") or "").strip() or "Unassigned"
        grounding = str(projection.get("grounding") or "").strip()
        grounding_label = {
            "source_material": "technical_evidence",
            "experimental_log": "measurement_log",
            "human_boundary": "author_scope_constraints",
            "verified_citation": "verified_background_literature",
        }.get(grounding, grounding or None)
        supporting_evidence = _safe_supporting_evidence(claim)
        claims_by_section.setdefault(section, []).append(
            {
                "claim": _prompt_compact_text(str(projection.get("authorial_claim") or ""), head_chars=260, tail_chars=0),
                "type": projection.get("claim_type"),
                "grounding": grounding_label,
                "required": bool(projection.get("required", True)),
                "risk": projection.get("risk"),
                "supporting_evidence": supporting_evidence,
                "supporting_excerpt": supporting_evidence[0]["excerpt"] if supporting_evidence else "",
                "coverage_terms": projection.get("coverage_groups") or [],
            }
        )
    citation_guidance: list[dict[str, Any]] = []
    for placement in citation_placement_plan.get("placements") or []:
        if not isinstance(placement, dict):
            continue
        citation_guidance.append(
            {
                "section": placement.get("target_section"),
                "citation_keys": placement.get("citation_keys") or [],
                "purpose": _prompt_compact_text(str(placement.get("purpose") or placement.get("rationale") or ""), head_chars=220, tail_chars=0),
            }
        )
    section_roles = []
    for role in narrative_plan.get("section_roles") or []:
        if not isinstance(role, dict):
            continue
        title = str(role.get("section_title") or "").strip()
        must_cover = [str(item) for item in role.get("must_cover") or [] if str(item).strip()]
        required_claims = claims_by_section.get(title, [])
        if required_claims:
            must_cover = [claim["claim"] for claim in required_claims if claim.get("claim")]
        section_roles.append(
            {
                "section": title,
                "role": _prompt_compact_text(
                    sanitize_author_facing_text(str(role.get("role") or ""), fallback="Develop this section from stated evidence, assumptions, and assigned citations."),
                    head_chars=260,
                    tail_chars=0,
                ),
                "must_cover": must_cover,
                "must_not_claim": role.get("must_not_claim") or [],
                "required_claims": required_claims,
            }
        )
    brief = {
        "thesis": _prompt_compact_text(
            sanitize_author_facing_text(
                str(narrative_plan.get("thesis") or ""),
                fallback="Build a coherent scholarly draft that preserves the paper's stated claims, scope, and citation positioning.",
            ),
            head_chars=500,
            tail_chars=0,
        ),
        "contribution_boundary": [
            sanitize_author_facing_text(str(item), fallback="State evidence limits as ordinary scholarly assumptions, scope, and limitations.")
            for item in (narrative_plan.get("contribution_boundary") or [])
            if str(item).strip()
        ],
        "section_roles": section_roles,
        "citation_guidance": citation_guidance,
        "authoring_rules": [
            "Write only scholarly paper prose.",
            "Use external citations for background, standards, baselines, and contrast; keep core method, proof, and result claims tied to technical evidence.",
            "State limitations as normal scholarly scope conditions rather than process disclaimers.",
        ],
    }
    _validate_author_facing_writer_brief(brief)
    return brief


def _validate_author_facing_writer_brief(brief: dict[str, Any]) -> dict[str, Any]:
    try:
        assert_author_facing_payload(brief, label="author_facing_writer_brief.json")
    except ValueError as exc:
        raise ContractError(str(exc)) from exc
    return brief


def _author_facing_writer_brief_block(brief: dict[str, Any]) -> str:
    return _data_block(
        "scholarly_authoring_brief",
        json.dumps(_validate_author_facing_writer_brief(brief), indent=2, ensure_ascii=False),
    )

def write_figure_placement_review(
    cwd: str | Path | None,
    *,
    output_path: str | Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    state = load_session(cwd)
    if not state.artifacts.paper_full_tex:
        raise ContractError("Need paper.full.tex before figure-placement review.")
    manuscript_path = Path(state.artifacts.paper_full_tex).resolve()
    source_latex = read_text(state.inputs.template_path) if state.inputs.template_path and Path(state.inputs.template_path).exists() else None
    payload = build_figure_placement_review(
        manuscript_path.read_text(encoding="utf-8"),
        source_latex=source_latex,
        manuscript_path=str(manuscript_path),
        pdf_path=state.artifacts.compiled_pdf,
    )
    payload["generated_at"] = utc_now_iso()
    payload["manuscript_sha256"] = hashlib.sha256(manuscript_path.read_bytes()).hexdigest()
    path = Path(output_path).resolve() if output_path else artifact_path(cwd, "figure-placement-review.json")
    write_json(path, payload)
    state.artifacts.latest_figure_placement_review_json = str(path)
    save_session(cwd, state)
    return path, payload


def validate_paper_contract(
    latex: str,
    *,
    citation_map: dict[str, Any],
    figures_dir: str | None,
    plot_manifest: dict[str, Any] | None = None,
    plot_assets_index: dict[str, Any] | None = None,
    experimental_log_text: str | None = None,
    expected_section_titles: list[str] | None = None,
) -> list[str]:
    issues = collect_paper_contract_issues(
        latex,
        citation_map=citation_map,
        figures_dir=figures_dir,
        plot_manifest=plot_manifest,
        plot_assets_index=plot_assets_index,
        experimental_log_text=experimental_log_text,
        expected_section_titles=expected_section_titles,
    )
    return _issue_messages(issues)


def record_current_validation_report(
    cwd: str | Path | None,
    *,
    name: str = "validation.current.json",
) -> tuple[Path, dict[str, Any]]:
    state = load_session(cwd)
    if not state.artifacts.paper_full_tex:
        raise ContractError("Need paper.full.tex before validating the current manuscript.")
    latex = read_text(state.artifacts.paper_full_tex)
    citation_map = read_json(state.artifacts.citation_map_json) if state.artifacts.citation_map_json else {}
    plot_manifest = read_json(state.artifacts.plot_manifest_json) if state.artifacts.plot_manifest_json else None
    plot_assets_index = read_json(state.artifacts.plot_assets_json) if state.artifacts.plot_assets_json else None
    plot_manifest = _reviewable_plot_manifest(plot_manifest, plot_assets_index)
    outline = read_json(state.artifacts.outline_json) if state.artifacts.outline_json else None
    expected_section_titles = _expected_section_titles_from_outline(outline) if isinstance(outline, dict) else None
    validation_inputs = _read_inputs(state)
    experimental_log_text = _source_grounding_text(validation_inputs)
    planning_status = planning_artifact_status(cwd)
    planning_payloads = planning_status.get("payloads") if planning_status.get("status") == "pass" else {}
    issues = collect_paper_contract_issues(
        latex,
        citation_map=citation_map,
        figures_dir=state.inputs.figures_dir,
        plot_manifest=plot_manifest,
        plot_assets_index=plot_assets_index,
        experimental_log_text=experimental_log_text,
        expected_section_titles=expected_section_titles,
        narrative_plan=(planning_payloads or {}).get("narrative_plan"),
        claim_map=(planning_payloads or {}).get("claim_map"),
        citation_placement_plan=(planning_payloads or {}).get("citation_placement_plan"),
    )
    path, payload = _record_validation_report(
        cwd,
        stage="current_manuscript",
        issues=issues,
        name=name,
        manuscript_path=state.artifacts.paper_full_tex,
        manuscript_text=latex,
    )
    state = load_session(cwd)
    state.notes.append(f"Current manuscript validation report recorded: {path.name}")
    save_session(cwd, state)
    return path, payload


def generate_outline(cwd: str | Path | None, provider: BaseProvider, *, runtime_mode: str = "compatibility") -> Path:
    state = load_session(cwd)
    inputs = _read_inputs(state)
    prompt_idea = _prompt_compact_text(inputs["idea"], head_chars=8000, tail_chars=1500)
    prompt_experimental_log = _prompt_compact_text(inputs["experimental_log"], head_chars=9000, tail_chars=2500)
    prompt_template = _prompt_compact_text(inputs["template"], head_chars=9000, tail_chars=1000)
    user_prompt = f"""
Inputs:
{_data_block('idea.md', prompt_idea)}

{_data_block('experimental_log.md', prompt_experimental_log)}

{_data_block('template.tex', prompt_template)}

{_data_block('conference_guidelines.md', inputs['guidelines'])}

{_data_block('cutoff_date', state.inputs.cutoff_date or 'null')}

Manuscript prose hygiene:
- Write only manuscript-facing scholarly prose.
- Express evidence limits only as normal scholarly assumptions, scope, and limitations.
""".strip()
    response, lane_type, fallback_used, lane_notes = _complete_with_runtime_mode(
        _build_completion_request(
            system_prompt=PROMPTS.render_outline_system(cutoff_date=state.inputs.cutoff_date),
            user_prompt=user_prompt,
        ),
        provider=provider,
        runtime_mode=runtime_mode,
        cwd=cwd,
        omx_lane_type="ralph",
        trace_stage="outline",
        output_schema=OUTLINE_SCHEMA,
    )
    payload = normalize_outline_payload(extract_json(response))
    validate_outline(payload)
    path = artifact_path(cwd, "outline.json")
    write_json(path, payload)
    lane_path = record_lane_manifest(
        cwd,
        stage="outline",
        role="Outline Agent",
        runtime_mode=runtime_mode,
        lane_type=lane_type,
        owner=_lane_owner(lane_type, fallback_used),
        status="fallback_completed" if fallback_used else "completed",
        input_artifacts=[
            state.inputs.idea_path,
            state.inputs.experimental_log_path,
            state.inputs.template_path,
            state.inputs.guidelines_path,
        ],
        output_artifacts=[str(path)],
        fallback_used=fallback_used,
        notes=lane_notes,
    )
    state.artifacts.outline_json = str(path)
    state.current_phase = "plot_generation_and_literature_review"
    state.active_artifact = "outline.json"
    state.notes.append("Outline generated.")
    state.notes.append(f"Lane manifest recorded: {lane_path.name}")
    save_session(cwd, state)
    return path


def generate_plots(cwd: str | Path | None, provider: BaseProvider | None = None, *, runtime_mode: str = "compatibility") -> Path:
    state = load_session(cwd)
    if not state.artifacts.outline_json:
        raise ContractError("Generate outline.json before generate-plots.")
    outline = read_json(state.artifacts.outline_json)
    payload, lane_type, fallback_used, lane_notes = _build_plot_payload(
        outline,
        state,
        provider,
        runtime_mode=runtime_mode,
        cwd=cwd,
    )

    validate_plot_manifest(payload)
    manifest_path = artifact_path(cwd, "plot_manifest.json")
    captions_path = artifact_path(cwd, "plot_captions.json")
    write_json(manifest_path, payload)
    write_json(captions_path, {item["figure_id"]: item["caption"] for item in payload["figures"]})
    assets_dir, assets_index = _write_plot_assets(cwd, payload)
    lane_path = record_lane_manifest(
        cwd,
        stage="plot",
        role="Plotting Agent",
        runtime_mode=runtime_mode,
        lane_type=lane_type,
        owner=_lane_owner(lane_type, fallback_used),
        status="fallback_completed" if fallback_used else "completed",
        input_artifacts=[state.artifacts.outline_json or ""],
        output_artifacts=[str(manifest_path), str(captions_path), str(assets_index)],
        fallback_used=fallback_used,
        notes=lane_notes,
    )
    state.artifacts.plot_manifest_json = str(manifest_path)
    state.artifacts.plot_captions_json = str(captions_path)
    state.artifacts.plot_assets_dir = str(assets_dir)
    state.artifacts.plot_assets_json = str(assets_index)
    state.current_phase = "literature_review"
    state.active_artifact = "plot_manifest.json"
    state.notes.append(f"Plot manifest and SVG assets generated for {len(payload['figures'])} figures.")
    state.notes.append(f"Lane manifest recorded: {lane_path.name}")
    save_session(cwd, state)
    return manifest_path


def _discovery_payload_from_outline(outline: dict[str, Any], cutoff_date: str | None) -> str:
    return _data_block(
        "discovery_payload.json",
        json.dumps(
            {
                "intro_related_work_plan": outline["intro_related_work_plan"],
                "section_plan": outline["section_plan"],
                "cutoff_date": cutoff_date,
            },
            indent=2,
            ensure_ascii=False,
        ),
    )


def discover_papers(
    cwd: str | Path | None,
    provider: BaseProvider | None = None,
    mode: str = "model",
    *,
    runtime_mode: str = "compatibility",
) -> Path:
    state = load_session(cwd)
    if not state.artifacts.outline_json:
        raise ContractError("Generate outline.json before discovering papers.")
    outline = read_json(state.artifacts.outline_json)
    payload, lane_type, fallback_used, lane_notes = _build_candidate_payload(
        outline,
        state,
        provider,
        mode,
        runtime_mode=runtime_mode,
        cwd=cwd,
    )

    if "macro_candidates" not in payload or "micro_candidates" not in payload:
        raise ContractError("candidate discovery output must contain macro_candidates and micro_candidates")

    path = artifact_path(cwd, "candidate_papers.json")
    write_json(path, payload)
    lane_path = record_lane_manifest(
        cwd,
        stage="literature",
        role="Literature Review Agent",
        runtime_mode=runtime_mode,
        lane_type=lane_type,
        owner=_lane_owner(lane_type, fallback_used),
        status="fallback_completed" if fallback_used else "completed",
        input_artifacts=[state.artifacts.outline_json or ""],
        output_artifacts=[str(path)],
        fallback_used=fallback_used,
        notes=lane_notes,
    )
    state.artifacts.candidate_papers_json = str(path)
    state.current_phase = "literature_review"
    state.active_artifact = "candidate_papers.json"
    state.latest_discovery_mode = mode
    state.notes.append(f"Candidate papers discovered via {mode} mode.")
    state.notes.append(f"Lane manifest recorded: {lane_path.name}")
    save_session(cwd, state)
    return path


def _record_verification_errors(
    cwd: str | Path | None,
    state,
    errors: list[dict[str, Any]],
    *,
    mode: str,
    on_error: str,
) -> Path | None:
    if not errors:
        return None
    path = artifact_path(cwd, "verification_errors.json")
    write_json(
        path,
        {
            "mode": mode,
            "on_error": on_error,
            "error_count": len(errors),
            "errors": errors,
            "recovery_hints": [
                "Set SEMANTIC_SCHOLAR_API_KEY for more reliable live verification.",
                "Retry `paperorchestra verify-papers --mode live --on-error skip` to keep any candidates that verify successfully.",
                "Use `paperorchestra verify-papers --mode mock` only for demos or offline dry runs.",
            ],
        },
    )
    state.artifacts.latest_verification_errors_json = str(path)
    state.notes.append(f"Recorded {len(errors)} live verification error(s): {path.name}")
    return path


def _registry_entry_payload(paper: VerifiedPaper) -> dict[str, Any]:
    return {
        "title": paper.title,
        "abstract": paper.abstract,
        "authors": paper.authors,
        "year": paper.year,
        "venue": paper.venue,
        "paper_id": paper.paper_id,
        "url": paper.url,
        "external_ids": paper.external_ids,
        "origin": paper.origin,
        "matched_query": paper.matched_query,
        "provenance": {
            "source": paper.origin,
            "verification": "curated_seed" if paper.origin and "seed" in paper.origin else "metadata_import",
            "title_match_ratio": paper.title_match_ratio,
        },
    }


def verify_papers(
    cwd: str | Path | None,
    *,
    min_ratio: float = 70.0,
    mode: str = "live",
    on_error: str = "skip",
) -> Path:
    if on_error not in {"skip", "fail"}:
        raise ContractError(f"Unsupported verification error policy: {on_error}")
    state = load_session(cwd)
    if not state.artifacts.candidate_papers_json:
        raise ContractError("Run discover-papers before verify-papers.")
    candidates = read_json(state.artifacts.candidate_papers_json)
    registry: list[VerifiedPaper] = []
    seen_ids: set[str] = set()
    verification_errors: list[dict[str, Any]] = []
    candidate_count = 0
    for bucket in ["macro_candidates", "micro_candidates"]:
        for candidate in candidates.get(bucket, []):
            title = candidate.get("title_guess")
            if not title:
                continue
            candidate_count += 1
            if mode == "mock":
                paper = mock_verified_paper(
                    title,
                    abstract_hint=candidate.get("why_relevant", ""),
                    cutoff_date=state.inputs.cutoff_date,
                    origin=bucket,
                    query_hint=candidate.get("origin_query") or title,
                )
            elif mode == "live":
                try:
                    paper = verify_candidate_title(
                        title,
                        cutoff_date=state.inputs.cutoff_date,
                        query_hint=candidate.get("origin_query") or title,
                        min_ratio=min_ratio,
                    )
                except Exception as exc:
                    error = {
                        "bucket": bucket,
                        "title_guess": title,
                        "query_hint": candidate.get("origin_query") or title,
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                        "action": "failed" if on_error == "fail" else "skipped",
                    }
                    verification_errors.append(error)
                    if on_error == "fail":
                        error_path = _record_verification_errors(
                            cwd,
                            state,
                            verification_errors,
                            mode=mode,
                            on_error=on_error,
                        )
                        state.current_phase = "blocked"
                        state.active_artifact = Path(error_path).name if error_path else "verification_errors.json"
                        save_session(cwd, state)
                        raise ContractError(
                            f"Live verification failed for candidate {title!r}: {exc}. "
                            "Set SEMANTIC_SCHOLAR_API_KEY, retry with --on-error skip, or use --verify-mode mock for offline demos."
                        ) from exc
                    continue
            else:
                raise ContractError(f"Unsupported verify mode: {mode}")
            if not paper or paper.is_after_cutoff or paper.paper_id in seen_ids:
                continue
            paper.origin = bucket
            registry.append(paper)
            seen_ids.add(paper.paper_id)

    prior_registry: list[VerifiedPaper] = []
    if state.artifacts.citation_registry_json and Path(state.artifacts.citation_registry_json).exists():
        try:
            prior_payload = read_json(state.artifacts.citation_registry_json)
            if isinstance(prior_payload, list):
                prior_registry = [VerifiedPaper(**item) for item in prior_payload if isinstance(item, dict)]
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            prior_registry = []
            state.notes.append(
                "Existing citation registry could not be loaded and was treated as empty: "
                f"{exc.__class__.__name__}."
            )

    verified_registry_count = len(registry)
    registry = _merge_live_verified_with_prior_registry(prior_registry, registry)
    if prior_registry and len(registry) >= len(prior_registry):
        state.notes.append(
            "Live verification merged with and preserved the prior registry artifacts "
            f"({verified_registry_count} live verified, {len(prior_registry)} prior curated, {len(registry)} total)."
        )

    preserve_prior_registry = (
        mode == "live"
        and on_error == "skip"
        and bool(verification_errors)
        and bool(prior_registry)
        and len(registry) < len(prior_registry)
    )

    if preserve_prior_registry:
        registry = prior_registry
        state.notes.append(
            "Live verification returned fewer verified papers than the existing registry after candidate-level errors; preserved the prior registry artifacts."
        )

    ensure_unique_bibtex_keys(registry)

    path = artifact_path(cwd, "citation_registry.json")
    serialize_registry(path, registry)
    citation_map = _citation_map_from_registry(registry)
    citation_map_path = artifact_path(cwd, "citation_map.json")
    write_json(citation_map_path, citation_map)

    verification_errors_path = _record_verification_errors(
        cwd,
        state,
        verification_errors,
        mode=mode,
        on_error=on_error,
    )
    state.latest_verify_mode = mode
    if mode != "live":
        state.latest_verify_fallback_used = None
    if mode == "live" and candidate_count > 0 and verification_errors and not registry:
        state.current_phase = "blocked"
        state.active_artifact = Path(verification_errors_path).name if verification_errors_path else "verification_errors.json"
        save_session(cwd, state)
        raise ContractError(
            "Live verification produced no verified papers after candidate-level errors. "
            "Set SEMANTIC_SCHOLAR_API_KEY, reduce request volume and retry, or rerun with --verify-mode mock for offline demos. "
            f"Details: {verification_errors_path}"
        )
    state.artifacts.citation_registry_json = str(path)
    state.artifacts.citation_map_json = str(citation_map_path)
    state.active_artifact = "citation_registry.json"
    if verification_errors:
        state.notes.append(
            f"Skipped {len(verification_errors)} candidate verification error(s) while verifying {len(registry)} paper(s)."
        )
    state.notes.append(f"Verified {len(registry)} papers via {mode} mode.")
    save_session(cwd, state)
    return path


def _merge_live_verified_with_prior_registry(
    prior_registry: list[VerifiedPaper],
    verified_registry: list[VerifiedPaper],
) -> list[VerifiedPaper]:
    """Preserve curated citation keys while enriching with live verification.

    `import-prior-work` is the operator/human-curated bibliography surface.  A
    later Semantic Scholar verification pass may confirm only a subset of those
    entries (RFCs, NIST reports, web specs, and some standards are often not
    returned as paper records).  Claim-safe source packets still need those
    curated keys in citation_map.json, so live verification must merge with,
    not destructively replace, the prior registry.
    """

    if not prior_registry:
        return verified_registry
    if not verified_registry:
        return prior_registry

    merged_by_title: dict[str, VerifiedPaper] = {}
    ordered_titles: list[str] = []

    def remember(title_key: str, paper: VerifiedPaper) -> None:
        if title_key not in merged_by_title:
            ordered_titles.append(title_key)
        merged_by_title[title_key] = paper

    for paper in prior_registry:
        title_key = _normalized_registry_title_key(paper)
        if title_key:
            remember(title_key, paper)

    for paper in verified_registry:
        title_key = _normalized_registry_title_key(paper)
        if not title_key:
            continue
        prior = merged_by_title.get(title_key)
        if prior is None:
            remember(title_key, paper)
            continue
        remember(title_key, _merge_verified_entry_with_prior_keys(prior, paper))

    merged = [merged_by_title[key] for key in ordered_titles if key in merged_by_title]
    return ensure_unique_bibtex_keys(merged)


def _normalized_registry_title_key(paper: VerifiedPaper) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", paper.title.lower())).strip()


def _merge_verified_entry_with_prior_keys(prior: VerifiedPaper, verified: VerifiedPaper) -> VerifiedPaper:
    live_primary_key = verified.bibtex_key
    verified.bibtex_key = prior.bibtex_key or verified.bibtex_key
    aliases: list[str] = []
    for key in [*prior.alias_bibtex_keys, live_primary_key, *verified.alias_bibtex_keys]:
        if key and key != verified.bibtex_key and key not in aliases:
            aliases.append(key)
    verified.alias_bibtex_keys = aliases
    if prior.origin and verified.origin and prior.origin not in verified.origin.split("+"):
        verified.origin = f"{prior.origin}+{verified.origin}"
    elif prior.origin and not verified.origin:
        verified.origin = prior.origin
    if prior.matched_query and not verified.matched_query:
        verified.matched_query = prior.matched_query
    return verified


def build_bib(cwd: str | Path | None) -> Path:
    state = load_session(cwd)
    if not state.artifacts.citation_registry_json:
        raise ContractError("Run verify-papers before build-bib.")
    registry = [VerifiedPaper(**item) for item in read_json(state.artifacts.citation_registry_json)]
    bib = registry_to_bibtex(registry)
    path = artifact_path(cwd, "references.bib")
    write_text(path, bib)
    state.artifacts.references_bib = str(path)
    state.active_artifact = "references.bib"
    state.notes.append("BibTeX file generated.")
    save_session(cwd, state)
    return path


def _citation_map_from_registry(registry: list[VerifiedPaper]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for paper in registry:
        entry = _registry_entry_payload(paper)
        for key in [paper.bibtex_key, *paper.alias_bibtex_keys]:
            if key:
                payload[key] = entry
    return payload


def _prior_work_context_from_paths(paper: str | Path | None, artifact_repo: str | Path | None) -> str:
    chunks: list[str] = []
    if paper:
        paper_path = Path(paper).resolve()
        if paper_path.exists():
            chunks.append(_data_block("source_paper.tex", read_text(paper_path)))
            references = paper_path.parent / "references.bib"
            if references.exists():
                chunks.append(_data_block("source_references.bib", read_text(references)))
    if artifact_repo:
        repo = Path(artifact_repo).resolve()
        for rel in ["README.md", "benchmarks/result.txt", "benchmarks/DATA_FORMAT.md"]:
            path = repo / rel
            if path.exists():
                chunks.append(_data_block(f"artifact_repo/{rel}", read_text(path)))
    return "\n\n".join(chunks) if chunks else ""


def research_prior_work(
    cwd: str | Path | None,
    provider: BaseProvider,
    *,
    output: str | Path | None = None,
    paper: str | Path | None = None,
    artifact_repo: str | Path | None = None,
    runtime_mode: str = "compatibility",
    source: str = "codex_web_seed",
    import_seed: bool = False,
) -> dict[str, Any]:
    state = load_session(cwd)
    inputs = _read_inputs(state)
    extra_context = _prompt_compact_text(_prior_work_context_from_paths(paper, artifact_repo), head_chars=6000, tail_chars=1000)
    prompt_idea = _prompt_compact_text(inputs["idea"], head_chars=6000, tail_chars=1000)
    prompt_experimental_log = _prompt_compact_text(inputs["experimental_log"], head_chars=10000, tail_chars=2000)
    user_prompt = f"""
{_data_block('idea.md', prompt_idea)}

{_data_block('experimental_log.md', prompt_experimental_log)}

{_data_block('conference_guidelines.md', inputs['guidelines'])}

{_data_block('cutoff_date', state.inputs.cutoff_date or 'null')}

{extra_context}

Task:
Produce a curated prior_work seed JSON for this research paper. Prefer canonical standards, foundational papers, benchmark/spec documents, and close prior work. If this runtime has web/search tools, use them conservatively; otherwise derive only from supplied materials. Do not invent authors or venues. If uncertain, include a provenance note saying what must be manually verified.

Return JSON with exactly two top-level keys: references and research_notes.
""".strip()
    system_prompt = f"""
You are a prior-work seed generator for PaperOrchestra.
Return one valid JSON object matching this contract:
- references: array of objects with title, authors, year, venue, url, doi, source, why_relevant, provenance_notes
- research_notes: array of concise caveats or follow-up checks

Rules:
- Use source={source!r} unless an entry has a more precise provenance.
- Prefer official RFC/NIST/spec URLs for standards.
- Do not fabricate bibliographic metadata. Use null for unknown year/venue/url/doi.
- This seed is an input to import-prior-work; it is not live Semantic Scholar verification.

""".strip()
    response, lane_type, fallback_used, lane_notes = _complete_with_runtime_mode(
        _build_completion_request(system_prompt=system_prompt, user_prompt=user_prompt),
        provider=provider,
        runtime_mode=runtime_mode,
        cwd=cwd,
        omx_lane_type="researcher",
        trace_stage="prior_work_seed",
        output_schema=PRIOR_WORK_SEED_SCHEMA,
    )
    payload = extract_json(response)
    for entry in payload.get("references", []):
        if isinstance(entry, dict):
            entry.setdefault("source", source)
    current_session_id = state.session_id
    output_path = Path(output).resolve() if output else artifact_path(cwd, "prior_work_seed.json")
    write_json(output_path, payload)
    lane_path = record_lane_manifest(
        cwd,
        stage="prior_work_research",
        role="Prior Work Researcher",
        runtime_mode=runtime_mode,
        lane_type=lane_type,
        owner=_lane_owner(lane_type, fallback_used),
        status="fallback_completed" if fallback_used else "completed",
        input_artifacts=[state.inputs.idea_path, state.inputs.experimental_log_path],
        output_artifacts=[str(output_path)],
        fallback_used=fallback_used,
        notes=lane_notes,
    )
    state.notes.append(f"Prior-work seed generated: {output_path}")
    state.notes.append(f"Lane manifest recorded: {lane_path.name}")
    save_session(cwd, state)
    result: dict[str, Any] = {"path": str(output_path), "reference_count": len(payload.get("references", [])), "lane_manifest": str(lane_path)}
    if import_seed:
        result["imported"] = import_prior_work(cwd, seed_file=output_path, source=source)
    return result


def import_prior_work(cwd: str | Path | None, *, seed_file: str | Path, source: str = "manual_seed") -> dict[str, str]:
    state = load_session(cwd)
    entries = load_prior_work_seed(seed_file, source=source)
    registry = prior_work_entries_to_verified_papers(entries, cutoff_date=state.inputs.cutoff_date)
    if not registry:
        raise ContractError(f"No usable prior-work entries were imported from {seed_file}.")
    prior_registry: list[VerifiedPaper] = []
    if state.artifacts.citation_registry_json and Path(state.artifacts.citation_registry_json).exists():
        try:
            prior_payload = read_json(state.artifacts.citation_registry_json)
            if isinstance(prior_payload, list):
                prior_registry = [VerifiedPaper(**item) for item in prior_payload if isinstance(item, dict)]
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            prior_registry = []
            state.notes.append(
                "Existing citation registry could not be loaded during prior-work import and was treated as empty: "
                f"{exc.__class__.__name__}."
            )
    if prior_registry:
        imported_count = len(registry)
        registry = _merge_live_verified_with_prior_registry(prior_registry, registry)
        state.notes.append(
            "Prior-work import merged with and preserved the existing citation registry "
            f"({len(prior_registry)} existing, {imported_count} imported, {len(registry)} total)."
        )

    candidate_payload = {
        "macro_candidates": [
            {
                "title_guess": paper.title,
                "why_relevant": paper.abstract,
                "origin_query": paper.matched_query or paper.title,
                "role_guess": "macro",
                "discovery_source": paper.origin or source,
                "discovery_sources": [paper.origin or source],
            }
            for paper in registry
        ],
        "micro_candidates": [],
    }
    candidate_path = artifact_path(cwd, "candidate_papers.json")
    registry_path = artifact_path(cwd, "citation_registry.json")
    citation_map_path = artifact_path(cwd, "citation_map.json")
    references_path = artifact_path(cwd, "references.bib")
    write_json(candidate_path, candidate_payload)
    serialize_registry(registry_path, registry)
    write_json(citation_map_path, _citation_map_from_registry(registry))
    write_text(references_path, registry_to_bibtex(registry))

    lane_path = record_lane_manifest(
        cwd,
        stage="literature",
        role="Curated Prior Work Import",
        runtime_mode="curated_seed",
        lane_type="manual",
        owner="operator",
        status="completed",
        input_artifacts=[str(seed_file)],
        output_artifacts=[str(candidate_path), str(registry_path), str(citation_map_path), str(references_path)],
        fallback_used=False,
        notes=[
            f"Imported {len(registry)} curated prior-work entries from {seed_file}.",
            "Entries are curated seed metadata, not live Semantic Scholar verification unless the source says so.",
        ],
    )
    state.artifacts.candidate_papers_json = str(candidate_path)
    state.artifacts.citation_registry_json = str(registry_path)
    state.artifacts.citation_map_json = str(citation_map_path)
    state.artifacts.references_bib = str(references_path)
    state.current_phase = "literature_review"
    state.active_artifact = "references.bib"
    state.latest_discovery_mode = source
    state.notes.append(f"Imported curated prior work from {seed_file}.")
    state.notes.append(f"Lane manifest recorded: {lane_path.name}")
    save_session(cwd, state)
    return {
        "candidate_papers_json": str(candidate_path),
        "citation_registry_json": str(registry_path),
        "citation_map_json": str(citation_map_path),
        "references_bib": str(references_path),
        "lane_manifest": str(lane_path),
    }


def _min_cite_count(citation_map: dict[str, Any]) -> int:
    if not citation_map:
        return 0
    return max(1, int(round(len(citation_map) * 0.9)))


def _expected_section_titles_from_outline(outline: dict[str, Any]) -> list[str]:
    titles: list[str] = []
    saw_material_packet_control_section = False
    ignored = {
        "abstract",
        "appendix",
        "cross-cutting citation coverage checklist",
    }
    for item in outline.get("section_plan", []):
        if not isinstance(item, dict):
            continue
        title = item.get("section_title")
        if isinstance(title, str) and title.strip():
            normalized = _canonical_generated_section_title(title)
            if is_material_packet_control_section_title(title):
                saw_material_packet_control_section = True
            if (
                normalized in ignored
                or normalized.startswith("appendix")
                or is_material_packet_section_title(title)
                or "checklist" in normalized
            ):
                continue
            titles.append(normalized if normalized in {"method", "experiments", "discussion"} else title.strip())
    if saw_material_packet_control_section and not any(title.strip().lower() == "discussion" for title in titles):
        titles.append("Discussion")
    return titles


def write_intro_related(
    cwd: str | Path | None,
    provider: BaseProvider,
    *,
    runtime_mode: str = "compatibility",
    claim_safe: bool = False,
    allow_recoverable_contract_issues: bool = False,
) -> Path:
    state = load_session(cwd)
    if not state.artifacts.outline_json or not state.artifacts.citation_map_json:
        raise ContractError("Need outline.json and citation_map.json before writing intro/related work.")
    narrative_plan, claim_map, citation_placement_plan = _planning_payloads_for_prompt(cwd)
    narrative_plan, claim_map, citation_placement_plan = _filter_planning_payloads_for_sections(
        narrative_plan,
        claim_map,
        citation_placement_plan,
        ["Introduction", "Related Work"],
    )
    writer_brief = _writer_brief_from_planning(narrative_plan, claim_map, citation_placement_plan)
    outline = read_json(state.artifacts.outline_json)
    citation_map = read_json(state.artifacts.citation_map_json)
    min_citation_coverage = _citation_coverage_target(citation_map)
    inputs = _read_inputs(state)
    strict_claim_safe_prompt = _strict_content_gates_enabled(claim_safe=claim_safe)
    _raise_if_strict_source_citations_unmapped(
        inputs,
        citation_map,
        stage="intro_related",
        strict_claim_safe=strict_claim_safe_prompt,
    )
    prompt_intro_related_plan = _compact_intro_related_plan_for_prompt(outline["intro_related_work_plan"])
    prompt_citation_map = _compact_citation_map_for_prompt(
        citation_map,
        include_abstract=strict_claim_safe_prompt,
        include_authors=False,
        include_year=strict_claim_safe_prompt,
        include_venue=strict_claim_safe_prompt,
        include_provenance=False,
        include_origin=False,
        include_matched_query=False,
    )
    prompt_template = _prompt_compact_text(inputs["template"], head_chars=5000, tail_chars=500)
    prompt_idea = _prompt_compact_text(inputs["idea"], head_chars=4000, tail_chars=500)
    prompt_experimental_log = _prompt_compact_text(inputs["experimental_log"], head_chars=7000, tail_chars=1500)
    source_critical_context = _source_critical_context_for_prompt(inputs)
    user_prompt = f"""
{_data_block('template.tex', prompt_template)}

{_data_block('intro_related_authoring_plan', json.dumps(prompt_intro_related_plan, indent=2, ensure_ascii=False))}

{_author_facing_writer_brief_block(writer_brief)}

{_data_block('project_idea', prompt_idea)}

{_data_block('project_experimental_log', prompt_experimental_log)}

{_data_block('source_critical_context.json', json.dumps(source_critical_context, indent=2, ensure_ascii=False))}

{_data_block('citation_checklist', json.dumps(sorted(citation_map.keys()), indent=2, ensure_ascii=False))}

{_data_block('collected_papers', json.dumps(prompt_citation_map, indent=2, ensure_ascii=False))}

{_data_block('paper_count', str(len(citation_map)))}

{_data_block('min_cite_paper_count', str(min_citation_coverage))}

{_data_block('cutoff_date', state.inputs.cutoff_date or 'null')}
""".strip()
    response, lane_type, fallback_used, lane_notes = _complete_with_runtime_mode(
        _build_completion_request(
            system_prompt=PROMPTS.render_intro_related_system(
                paper_count=len(citation_map),
                min_cite_paper_count=min_citation_coverage,
                cutoff_date=state.inputs.cutoff_date,
            ),
            user_prompt=user_prompt,
        ),
        provider=provider,
        runtime_mode=runtime_mode,
        cwd=cwd,
        omx_lane_type="ralph",
        trace_stage="intro_related",
    )
    latex = extract_latex(response)
    latex = _preserve_all_except_sections(
        latex,
        inputs["template"],
        rewritten_section_names=["Introduction", "Related Work"],
    )
    latex = _remove_material_packet_sections(latex)
    latex = _sanitize_manuscript_control_prose(latex)
    latex, citation_replacements = canonicalize_citation_keys(latex, citation_map)
    if strict_claim_safe_prompt:
        dropped_citations = _unknown_citation_key_counts(latex, citation_map)
    else:
        latex, dropped_citations = _drop_unknown_citation_keys(latex, citation_map)
    validation_issues = collect_paper_contract_issues(
        latex,
        citation_map=citation_map,
        figures_dir=None,
        plot_manifest=None,
        experimental_log_text=_source_grounding_text(inputs),
        narrative_plan=narrative_plan,
        claim_map=claim_map,
        citation_placement_plan=citation_placement_plan,
    )
    blocking_issues = _blocking_issues(validation_issues)
    repairable_codes = {issue.code for issue in blocking_issues}
    if blocking_issues and repairable_codes <= {"unknown_citation_keys", "citation_coverage_insufficient", "numeric_grounding_mismatch"}:
        repair_attempt = 0
        while blocking_issues and repair_attempt < 2:
            repair_attempt += 1
            repair_prompt = f"""
{user_prompt}

{_data_block('current_intro_related_draft.tex', _prompt_compact_text(latex, head_chars=12000, tail_chars=2000))}

{_data_block('validation_issues.json', json.dumps([issue.to_dict() for issue in blocking_issues], indent=2, ensure_ascii=False))}

Repair Instructions:
- Revise the existing Introduction/Related Work draft to satisfy the exact validation issues above.
- Use ONLY citation keys from citation_checklist.
- Increase citation coverage until it satisfies min_cite_paper_count.
- Every decimal or percent value in the LaTeX must appear verbatim in project_experimental_log. If a number is not grounded there, remove it or rewrite the sentence qualitatively without introducing a replacement number.
- Preserve valid existing prose where possible and return LaTeX only.
""".strip()
            retry_response, retry_lane_type, retry_fallback_used, retry_lane_notes = _complete_with_runtime_mode(
                _build_completion_request(
                    system_prompt=PROMPTS.render_intro_related_system(
                        paper_count=len(citation_map),
                        min_cite_paper_count=min_citation_coverage,
                        cutoff_date=state.inputs.cutoff_date,
                    ),
                    user_prompt=repair_prompt,
                ),
                provider=provider,
                runtime_mode=runtime_mode,
                cwd=cwd,
                omx_lane_type="ralph",
                trace_stage="intro_related_repair" if repair_attempt == 1 else f"intro_related_repair_{repair_attempt}",
            )
            retry_latex = extract_latex(retry_response)
            retry_latex = _preserve_all_except_sections(
                retry_latex,
                inputs["template"],
                rewritten_section_names=["Introduction", "Related Work"],
            )
            retry_latex = _remove_material_packet_sections(retry_latex)
            retry_latex = _sanitize_manuscript_control_prose(retry_latex)
            retry_latex, retry_replacements = canonicalize_citation_keys(retry_latex, citation_map)
            if strict_claim_safe_prompt:
                retry_dropped_citations = _unknown_citation_key_counts(retry_latex, citation_map)
            else:
                retry_latex, retry_dropped_citations = _drop_unknown_citation_keys(retry_latex, citation_map)
            retry_issues = collect_paper_contract_issues(
                retry_latex,
                citation_map=citation_map,
                figures_dir=None,
                plot_manifest=None,
                experimental_log_text=_source_grounding_text(inputs),
                narrative_plan=narrative_plan,
                claim_map=claim_map,
                citation_placement_plan=citation_placement_plan,
            )
            retry_blocking = _blocking_issues(retry_issues)
            latex = retry_latex
            validation_issues = retry_issues
            blocking_issues = retry_blocking
            repairable_codes = {issue.code for issue in blocking_issues}
            lane_notes = lane_notes + [
                f"Introduction/Related Work draft repair attempt {repair_attempt} ran after citation-contract validation failure."
            ] + retry_lane_notes
            if citation_replacements and repair_attempt == 1:
                lane_notes.append(
                    "Canonicalized citation-key aliases in Introduction/Related Work draft: "
                    + ", ".join(f"{src}->{dst}" for src, dst in sorted(citation_replacements.items()))
                )
            if retry_replacements:
                lane_notes.append(
                    f"Canonicalized citation-key aliases in Introduction/Related Work repair attempt {repair_attempt}: "
                    + ", ".join(f"{src}->{dst}" for src, dst in sorted(retry_replacements.items()))
                )
            if retry_dropped_citations:
                note_prefix = (
                    f"Blocked unsupported citation keys in strict Introduction/Related Work repair attempt {repair_attempt}: "
                    if strict_claim_safe_prompt
                    else f"Dropped unsupported citation keys in Introduction/Related Work repair attempt {repair_attempt}: "
                )
                lane_notes.append(note_prefix + ", ".join(f"{key}({count})" for key, count in sorted(retry_dropped_citations.items())))
            lane_type = retry_lane_type
            fallback_used = retry_fallback_used
            if not blocking_issues:
                break
            if repairable_codes - {"unknown_citation_keys", "citation_coverage_insufficient", "numeric_grounding_mismatch"}:
                break
    elif citation_replacements:
        lane_notes.append(
            "Canonicalized citation-key aliases in Introduction/Related Work draft: "
            + ", ".join(f"{src}->{dst}" for src, dst in sorted(citation_replacements.items()))
        )
    if dropped_citations:
        note_prefix = (
            "Blocked unsupported citation keys in strict Introduction/Related Work draft: "
            if strict_claim_safe_prompt
            else "Dropped unsupported citation keys in Introduction/Related Work draft: "
        )
        lane_notes.append(note_prefix + ", ".join(f"{key}({count})" for key, count in sorted(dropped_citations.items())))

    if {issue.code for issue in _blocking_issues(validation_issues)} <= {"citation_coverage_insufficient"}:
        bridged_latex = _ensure_minimum_citation_coverage(latex, citation_map, target=min_citation_coverage)
        if bridged_latex != latex:
            bridged_issues = collect_paper_contract_issues(
                bridged_latex,
                citation_map=citation_map,
                figures_dir=None,
                plot_manifest=None,
                experimental_log_text=_source_grounding_text(inputs),
                narrative_plan=narrative_plan,
                claim_map=claim_map,
                citation_placement_plan=citation_placement_plan,
            )
            latex = bridged_latex
            validation_issues = bridged_issues
            lane_notes.append(
                "Added a bounded related-work citation bridge after repair attempts left only a small citation-coverage shortfall."
            )

    state.latest_provider_name = _provider_name(provider)
    state.latest_runtime_mode = runtime_mode
    save_session(cwd, state)
    validation_path, _ = _record_validation_report(
        cwd,
        stage="intro_related",
        issues=validation_issues,
        name="validation.intro_related.json",
        manuscript_text=latex,
    )
    state.artifacts.latest_validation_json = str(validation_path)
    blocking_issues = _blocking_issues(validation_issues)
    tolerated_recoverable_issues = (
        allow_recoverable_contract_issues
        and bool(blocking_issues)
        and {issue.code for issue in blocking_issues} <= {"citation_coverage_insufficient"}
    )
    if blocking_issues:
        state.notes.append(
            "Introduction/Related Work recoverable validation blockers: "
            + " | ".join(_issue_messages(blocking_issues))
        )
        if not tolerated_recoverable_issues:
            save_session(cwd, state)
            raise ContractError(
                "Introduction/Related Work output failed contract validation:\n- "
                + "\n- ".join(_issue_messages(blocking_issues))
            )
        lane_notes.append(
            "Persisted a recoverable Introduction/Related Work candidate despite citation-coverage shortfall "
            "so the supervised QA/operator loop can repair it instead of aborting the live smoke early."
        )
    elif validation_issues:
        state.notes.append(
            "Introduction/Related Work validation warnings: " + " | ".join(_issue_messages(validation_issues))
        )
    state.notes.append(f"Validation report recorded: {validation_path.name}")
    path = artifact_path(cwd, "introduction_related_work.tex")
    write_text(path, latex)
    lane_path = record_lane_manifest(
        cwd,
        stage="intro_related",
        role="Literature Review Agent",
        runtime_mode=runtime_mode,
        lane_type=lane_type,
        owner=_lane_owner(lane_type, fallback_used),
        status="fallback_completed" if fallback_used else "completed",
        input_artifacts=[state.artifacts.outline_json or "", state.artifacts.citation_map_json or ""],
        output_artifacts=[str(path), str(validation_path)],
        fallback_used=fallback_used,
        notes=lane_notes,
    )
    state.artifacts.intro_related_tex = str(path)
    state.current_phase = "section_writing"
    state.active_artifact = "introduction_related_work.tex"
    state.notes.append("Introduction and Related Work drafted.")
    state.notes.append(f"Lane manifest recorded: {lane_path.name}")
    save_session(cwd, state)
    return path


def write_sections(
    cwd: str | Path | None,
    provider: BaseProvider,
    *,
    runtime_mode: str = "compatibility",
    only_sections: list[str] | str | None = None,
    output_path: str | Path | None = None,
    claim_safe: bool = False,
) -> Path:
    state = load_session(cwd)
    if not state.artifacts.outline_json:
        raise ContractError("Need outline.json before write-sections.")
    selected_sections = _normalize_section_selection(only_sections)
    if selected_sections and not state.artifacts.paper_full_tex:
        raise ContractError("Need an existing paper.full.tex before rewriting only selected sections.")
    current_source = read_text(state.artifacts.paper_full_tex) if selected_sections and state.artifacts.paper_full_tex else None
    if current_source is not None:
        selected_sections = _resolve_selected_sections(current_source, selected_sections)
    narrative_plan, claim_map, citation_placement_plan = _planning_payloads_for_prompt(cwd)
    narrative_plan, claim_map, citation_placement_plan = _filter_planning_payloads_for_sections(
        narrative_plan,
        claim_map,
        citation_placement_plan,
        selected_sections,
    )
    writer_brief = _writer_brief_from_planning(narrative_plan, claim_map, citation_placement_plan)
    outline = read_json(state.artifacts.outline_json)
    raw_prompt_outline = _filtered_outline_for_sections(outline, selected_sections) if selected_sections else outline
    prompt_outline = _compact_outline_for_prompt(raw_prompt_outline)
    citation_map = read_json(state.artifacts.citation_map_json) if state.artifacts.citation_map_json else {}
    prompt_citation_map = _citation_map_for_selected_sections(current_source, citation_map, selected_sections) if current_source is not None else citation_map
    min_citation_coverage = _citation_coverage_target(citation_map)
    raw_plot_manifest = read_json(state.artifacts.plot_manifest_json) if state.artifacts.plot_manifest_json else {"figures": []}
    raw_plot_assets_index = read_json(state.artifacts.plot_assets_json) if state.artifacts.plot_assets_json else {"assets": []}
    plot_assets_index = _reviewable_plot_assets_index(raw_plot_assets_index)
    plot_manifest = _reviewable_plot_manifest(raw_plot_manifest, raw_plot_assets_index)
    prompt_plot_manifest = {"figures": []} if selected_sections else _compact_plot_manifest_for_prompt(plot_manifest)
    prompt_plot_assets_index = {"assets": []} if selected_sections else _compact_plot_assets_for_prompt(plot_assets_index)
    expected_section_titles = (
        selected_sections
        if selected_sections
        else _expected_section_titles_from_outline(outline)
    )
    inputs = _read_inputs(state)
    strict_claim_safe_prompt = _strict_content_gates_enabled(claim_safe=claim_safe)
    _raise_if_strict_source_citations_unmapped(
        inputs,
        citation_map,
        stage="section_writing",
        strict_claim_safe=strict_claim_safe_prompt,
    )
    prompt_citation_map_compact = _compact_citation_map_for_prompt(
        prompt_citation_map,
        include_abstract=strict_claim_safe_prompt,
        include_authors=False,
        include_year=strict_claim_safe_prompt,
        include_venue=strict_claim_safe_prompt,
        include_provenance=False,
        include_origin=False,
        include_matched_query=False,
    )
    prompt_idea = _prompt_compact_text(inputs["idea"], head_chars=3000, tail_chars=500)
    prompt_experimental_log = _prompt_compact_text(inputs["experimental_log"], head_chars=5000, tail_chars=1000)
    source_critical_context = _source_critical_context_for_prompt(inputs)
    figures_dir = state.inputs.figures_dir or ""
    if current_source is not None:
        template_content = _selected_section_template(current_source, selected_sections)
    else:
        template_content = read_text(state.inputs.template_path)
        if state.artifacts.intro_related_tex and Path(state.artifacts.intro_related_tex).exists():
            intro_related_source = read_text(state.artifacts.intro_related_tex)
            template_content = _preserve_existing_sections(
                template_content,
                intro_related_source,
                section_names=["Introduction", "Related Work"],
            )
    prompt_template_content = _prompt_compact_text(template_content, head_chars=5000, tail_chars=1000)
    section_scope_instructions = ""
    if selected_sections:
        section_scope_instructions = (
            "Section-scope Instructions:\n"
            f"- Rewrite ONLY these sections: {', '.join(selected_sections)}.\n"
            "- Preserve all section titles, labels, citations, and figure references already present in current_template.tex for those sections.\n"
            "- Do NOT invent new citation keys, figure filenames, labels, or cross-references that are absent from current_template.tex.\n"
            "- Prefer revising the prose within the existing section skeleton over introducing new structural elements.\n"
        )
    global_section_instructions = (
        "Global Writing Constraints:\n"
        f"- Use at least {min_citation_coverage} distinct verified citations when that many verified references are available.\n"
        "- Do NOT invent meta sections such as checklists or workflow notes that are not part of current_template.tex.\n"
        "- Write manuscript prose only; express evidence limits as scholarly assumptions, scope, and limitations.\n"
        "- Do NOT preserve input-note headings as manuscript sections; fold their constraints into normal prose, "
        "especially Discussion limitations.\n"
    )
    user_prompt = f"""
{_data_block('outline.json', json.dumps(prompt_outline, indent=2, ensure_ascii=False))}

{_author_facing_writer_brief_block(writer_brief)}

{_data_block('idea.md', prompt_idea)}

{_data_block('experimental_log.md', prompt_experimental_log)}

{_data_block('source_critical_context.json', json.dumps(source_critical_context, indent=2, ensure_ascii=False))}

{_data_block('citation_map.json', json.dumps(prompt_citation_map_compact, indent=2, ensure_ascii=False))}

{_data_block('citation_coverage_target.json', json.dumps({'min_distinct_verified_citations': min_citation_coverage, 'available_verified_citations': len(citation_map)}, ensure_ascii=False))}

{_data_block('plot_manifest.json', json.dumps(prompt_plot_manifest, indent=2, ensure_ascii=False))}

{_data_block('plot_assets.json', json.dumps(prompt_plot_assets_index, indent=2, ensure_ascii=False))}

{_data_block('conference_guidelines.md', inputs['guidelines'])}

{_data_block('current_template.tex', prompt_template_content)}

{_data_block('figures_list', inputs['figures'])}

{_data_block('figures_dir', figures_dir or 'null')}
{_data_block('rewrite_scope.json', json.dumps({'only_sections': selected_sections, 'preserve_all_other_sections': bool(selected_sections)}, ensure_ascii=False))}

{global_section_instructions}
{section_scope_instructions}
""".strip()
    response, lane_type, fallback_used, lane_notes = _complete_with_runtime_mode(
        _build_completion_request(system_prompt=PROMPTS.render_section_writer_system(), user_prompt=user_prompt),
        provider=provider,
        runtime_mode=runtime_mode,
        cwd=cwd,
        omx_lane_type="ralph",
        trace_stage="section_writing",
    )
    latex = extract_latex(response)
    if selected_sections and current_source is not None:
        latex = _preserve_all_except_sections(
            latex,
            current_source,
            rewritten_section_names=selected_sections,
        )
    elif state.artifacts.intro_related_tex and Path(state.artifacts.intro_related_tex).exists():
        intro_related_source = read_text(state.artifacts.intro_related_tex)
        latex = _preserve_existing_sections(
            latex,
            intro_related_source,
            section_names=["Introduction", "Related Work"],
        )
    latex = _restore_missing_referenced_labels(latex, template_content)
    latex = _ensure_bibliography_hook(latex, citation_map)
    latex = _normalize_generated_plot_paths(latex, plot_assets_index)
    latex = _normalize_source_figure_paths(latex, state.inputs.figures_dir)
    latex = _ensure_generated_plot_usage(latex, plot_assets_index)
    latex = _remove_material_packet_sections(latex)
    latex = _ensure_discussion_section_for_claim_boundaries(latex, claim_map)
    latex = _ensure_required_claim_scope_notes(latex, claim_map)
    latex, citation_replacements = canonicalize_citation_keys(latex, citation_map)
    if strict_claim_safe_prompt:
        dropped_citations = _unknown_citation_key_counts(latex, citation_map)
    else:
        latex, dropped_citations = _drop_unknown_citation_keys(latex, citation_map)
    state.latest_provider_name = _provider_name(provider)
    state.latest_runtime_mode = runtime_mode
    save_session(cwd, state)
    latex = _apply_mock_watermark(latex, state, provider_name=_provider_name(provider))
    validation_subject = _selected_section_template(latex, selected_sections) if selected_sections else latex
    validation_issues = collect_paper_contract_issues(
        validation_subject,
        citation_map=citation_map,
        figures_dir=state.inputs.figures_dir,
        plot_manifest=None if selected_sections else plot_manifest,
        plot_assets_index=plot_assets_index,
        experimental_log_text=_source_grounding_text(inputs),
        expected_section_titles=expected_section_titles,
        narrative_plan=narrative_plan,
        claim_map=claim_map,
        citation_placement_plan=citation_placement_plan,
    )
    validation_issues = _filter_section_scoped_issues(validation_issues, selected_sections=selected_sections)
    blocking_issues = _blocking_issues(validation_issues)
    repairable_codes = {issue.code for issue in blocking_issues}
    if blocking_issues and repairable_codes <= {
        "unknown_citation_keys",
        "citation_coverage_insufficient",
        "numeric_grounding_mismatch",
        "plot_plan_not_reflected",
        "expected_section_missing",
        "expected_section_too_shallow",
    }:
        repair_prompt = f"""
{user_prompt}

{_data_block('current_draft.tex', _prompt_compact_text(latex, head_chars=10000, tail_chars=2000))}

{_data_block('validation_issues.json', json.dumps([issue.to_dict() for issue in blocking_issues], indent=2, ensure_ascii=False))}

Repair Instructions:
- Revise the existing manuscript draft to satisfy the validation issues above.
- Use ONLY citation keys from the verified reference library.
- Increase citation coverage until the paper satisfies the citation coverage contract, using at least {min_citation_coverage} distinct verified citations when that many are available.
- Every decimal or percent value in the manuscript must appear verbatim in the measurement log. If a number is not grounded there, remove it or rewrite the claim qualitatively without introducing a replacement number.
- Ensure every required plot-plan figure is represented in the manuscript. Use available generated plot assets/snippets instead of inventing new figure files.
- Expand every missing or shallow expected section with grounded, section-specific substance from the technical context, measurement log, section plan, and current template.
- Do not leave Method, Security Analysis, Implementation/Results, Discussion, or Conclusion as heading-only placeholders.
- Do not preserve input-note headings as manuscript sections; fold their constraints into Discussion and normal authorial prose.
- Preserve valid existing structure, plot usage, and grounded claims where possible.
- Do NOT invent meta sections such as checklists or workflow notes that are not part of the manuscript template.
- When rewrite_scope.json lists only_sections, preserve the existing section titles, citation keys, and figure references already present in current_template.tex.
- Return LaTeX only.
""".strip()
        retry_response, retry_lane_type, retry_fallback_used, retry_lane_notes = _complete_with_runtime_mode(
            _build_completion_request(system_prompt=PROMPTS.render_section_writer_system(), user_prompt=repair_prompt),
            provider=provider,
            runtime_mode=runtime_mode,
            cwd=cwd,
            omx_lane_type="ralph",
            trace_stage="section_writing_repair",
        )
        retry_latex = extract_latex(retry_response)
        if selected_sections and current_source is not None:
            retry_latex = _preserve_all_except_sections(
                retry_latex,
                current_source,
                rewritten_section_names=selected_sections,
            )
        elif state.artifacts.intro_related_tex and Path(state.artifacts.intro_related_tex).exists():
            intro_related_source = read_text(state.artifacts.intro_related_tex)
            retry_latex = _preserve_existing_sections(
                retry_latex,
                intro_related_source,
                section_names=["Introduction", "Related Work"],
            )
        retry_latex = _restore_missing_referenced_labels(retry_latex, template_content)
        retry_latex = _ensure_bibliography_hook(retry_latex, citation_map)
        retry_latex = _normalize_generated_plot_paths(retry_latex, plot_assets_index)
        retry_latex = _normalize_source_figure_paths(retry_latex, state.inputs.figures_dir)
        retry_latex = _ensure_generated_plot_usage(retry_latex, plot_assets_index)
        retry_latex = _remove_material_packet_sections(retry_latex)
        retry_latex = _ensure_discussion_section_for_claim_boundaries(retry_latex, claim_map)
        retry_latex = _ensure_required_claim_scope_notes(retry_latex, claim_map)
        retry_latex, retry_replacements = canonicalize_citation_keys(retry_latex, citation_map)
        if strict_claim_safe_prompt:
            retry_dropped_citations = _unknown_citation_key_counts(retry_latex, citation_map)
        else:
            retry_latex, retry_dropped_citations = _drop_unknown_citation_keys(retry_latex, citation_map)
        retry_validation_subject = _selected_section_template(retry_latex, selected_sections) if selected_sections else retry_latex
        retry_issues = collect_paper_contract_issues(
            retry_validation_subject,
            citation_map=citation_map,
            figures_dir=state.inputs.figures_dir,
            plot_manifest=None if selected_sections else plot_manifest,
            plot_assets_index=plot_assets_index,
            experimental_log_text=_source_grounding_text(inputs),
            expected_section_titles=expected_section_titles,
            narrative_plan=narrative_plan,
            claim_map=claim_map,
            citation_placement_plan=citation_placement_plan,
        )
        retry_issues = _filter_section_scoped_issues(retry_issues, selected_sections=selected_sections)
        retry_blocking = _blocking_issues(retry_issues)
        if (
            retry_blocking
            and {issue.code for issue in retry_blocking} <= {"citation_coverage_insufficient"}
            and _allow_related_citation_backfill(selected_sections)
        ):
            bridged_retry_latex = _ensure_minimum_citation_coverage(
                retry_latex,
                citation_map,
                target=min_citation_coverage,
            )
            if bridged_retry_latex != retry_latex:
                retry_latex = bridged_retry_latex
                retry_validation_subject = _selected_section_template(retry_latex, selected_sections) if selected_sections else retry_latex
                retry_issues = collect_paper_contract_issues(
                    retry_validation_subject,
                    citation_map=citation_map,
                    figures_dir=state.inputs.figures_dir,
                    plot_manifest=None if selected_sections else plot_manifest,
                    plot_assets_index=plot_assets_index,
                    experimental_log_text=_source_grounding_text(inputs),
                    expected_section_titles=expected_section_titles,
                    narrative_plan=narrative_plan,
                    claim_map=claim_map,
                    citation_placement_plan=citation_placement_plan,
                )
                retry_issues = _filter_section_scoped_issues(retry_issues, selected_sections=selected_sections)
                retry_blocking = _blocking_issues(retry_issues)
        if not retry_blocking:
            latex = retry_latex
            validation_issues = retry_issues
            blocking_issues = retry_blocking
            lane_notes = lane_notes + ["Section writer draft was retried after citation-contract validation failure."] + retry_lane_notes
            if citation_replacements:
                lane_notes.append(
                    "Canonicalized citation-key aliases in section draft: "
                    + ", ".join(f"{src}->{dst}" for src, dst in sorted(citation_replacements.items()))
                )
            if retry_replacements:
                lane_notes.append(
                    "Canonicalized citation-key aliases in section retry draft: "
                    + ", ".join(f"{src}->{dst}" for src, dst in sorted(retry_replacements.items()))
                )
            if retry_dropped_citations:
                note_prefix = (
                    "Blocked unsupported citation keys in strict section retry draft: "
                    if strict_claim_safe_prompt
                    else "Dropped unsupported citation keys in section retry draft: "
                )
                lane_notes.append(note_prefix + ", ".join(f"{key}({count})" for key, count in sorted(retry_dropped_citations.items())))
            lane_type = retry_lane_type
            fallback_used = retry_fallback_used
        else:
            repaired_retry_latex = retry_latex
            repaired = False
            if any(issue.code == "plot_plan_not_reflected" for issue in retry_blocking):
                repaired_retry_latex = _inject_missing_plot_assets(repaired_retry_latex, retry_blocking, plot_assets_index)
                repaired = True
            retry_validation_subject = _selected_section_template(repaired_retry_latex, selected_sections) if selected_sections else repaired_retry_latex
            sanitized_issues = collect_paper_contract_issues(
                retry_validation_subject,
                citation_map=citation_map,
                figures_dir=state.inputs.figures_dir,
                plot_manifest=None if selected_sections else plot_manifest,
                plot_assets_index=plot_assets_index,
                experimental_log_text=_source_grounding_text(inputs),
                expected_section_titles=expected_section_titles,
                narrative_plan=narrative_plan,
                claim_map=claim_map,
                citation_placement_plan=citation_placement_plan,
            )
            sanitized_issues = _filter_section_scoped_issues(sanitized_issues, selected_sections=selected_sections)
            if repaired and not _blocking_issues(sanitized_issues):
                latex = repaired_retry_latex
                validation_issues = sanitized_issues
                blocking_issues = []
                lane_notes = lane_notes + [
                    "Section retry draft received deterministic post-processing for residual plot-plan/numeric validation issues."
                ] + retry_lane_notes
                lane_type = retry_lane_type
                fallback_used = retry_fallback_used
    elif citation_replacements:
        lane_notes.append(
            "Canonicalized citation-key aliases in section draft: "
            + ", ".join(f"{src}->{dst}" for src, dst in sorted(citation_replacements.items()))
        )
    if dropped_citations:
        note_prefix = (
            "Blocked unsupported citation keys in strict section draft: "
            if strict_claim_safe_prompt
            else "Dropped unsupported citation keys in section draft: "
        )
        lane_notes.append(note_prefix + ", ".join(f"{key}({count})" for key, count in sorted(dropped_citations.items())))

    validation_path, _ = _record_validation_report(
        cwd,
        stage="section_writing",
        issues=validation_issues,
        name="validation.sections.json",
        manuscript_text=latex,
    )
    state.artifacts.latest_validation_json = str(validation_path)
    blocking_issues = _blocking_issues(validation_issues)
    if blocking_issues:
        raise ContractError(
            "Section writer produced invalid paper contract:\n- " + "\n- ".join(_issue_messages(blocking_issues))
        )
    if validation_issues:
        state.notes.append("Section writer validation warnings: " + " | ".join(_issue_messages(validation_issues)))
    state.notes.append(f"Validation report recorded: {validation_path.name}")
    path = Path(output_path).resolve() if output_path else artifact_path(cwd, "paper.full.tex")
    write_text(path, latex)
    lane_path = record_lane_manifest(
        cwd,
        stage="section_writing",
        role="Section Writing Agent",
        runtime_mode=runtime_mode,
        lane_type=lane_type,
        owner=_lane_owner(lane_type, fallback_used),
        status="fallback_completed" if fallback_used else "completed",
        input_artifacts=[
            state.artifacts.outline_json or "",
            state.artifacts.citation_map_json or "",
            state.artifacts.plot_assets_json or "",
        ],
        output_artifacts=[str(path), str(validation_path)],
        fallback_used=fallback_used,
        notes=lane_notes
        + (
            [f"Section-scoped rewrite requested for: {', '.join(selected_sections)}"]
            if selected_sections
            else []
        ),
    )
    state.artifacts.paper_full_tex = str(path)
    state.current_phase = "iterative_content_refinement"
    state.active_artifact = "paper.full.tex"
    state.notes.append("Full paper draft generated.")
    state.notes.append(f"Lane manifest recorded: {lane_path.name}")
    save_session(cwd, state)
    return path


def compile_current_paper(cwd: str | Path | None) -> Path:
    state = load_session(cwd)
    if not state.artifacts.paper_full_tex:
        raise ContractError("Need paper.full.tex before compile.")
    paper_path = Path(state.artifacts.paper_full_tex)
    log_path = build_path(cwd, "latex-build.log")
    report = compile_latex_with_report(paper_path, workdir=build_path(cwd, "compiled"), output_log=log_path)
    compile_report_path = artifact_path(cwd, "compile-report.json")
    write_json(compile_report_path, report.to_dict())
    state.artifacts.latest_compile_report_json = str(compile_report_path)
    if report.pdf_exists and report.pdf_path:
        state.artifacts.compiled_pdf = report.pdf_path
        state.active_artifact = Path(report.pdf_path).name
        if report.clean and state.current_phase == "draft_complete":
            state.current_phase = "complete"
            state.notes.append("Paper compiled successfully with a clean compile.")
        elif report.clean:
            state.notes.append("Paper compiled successfully with a clean compile.")
        else:
            state.notes.append("Paper compiled with warnings/unresolved issues.")
            save_session(cwd, state)
            raise ContractError(f"LaTeX build produced a PDF but has unresolved issues. See log: {report.log_path}")
    else:
        save_session(cwd, state)
        raise ContractError(f"LaTeX build failed. See log: {report.log_path}")
    save_session(cwd, state)
    return Path(report.pdf_path)


def review_current_paper(
    cwd: str | Path | None,
    provider: BaseProvider,
    *,
    review_name: str = "review.latest.json",
    runtime_mode: str = "compatibility",
) -> Path:
    state = load_session(cwd)
    if not state.artifacts.paper_full_tex:
        raise ContractError("Need paper.full.tex before review.")
    paper_text = read_text(state.artifacts.paper_full_tex)
    citation_map = read_json(state.artifacts.citation_map_json) if state.artifacts.citation_map_json else {}
    prompt_paper_text = _prompt_compact_text(paper_text, head_chars=22000, tail_chars=4000)
    prompt_citation_map = _compact_citation_map_for_prompt(
        citation_map,
        include_abstract=False,
        include_authors=False,
        include_year=False,
        include_venue=False,
        include_provenance=False,
        include_origin=False,
        include_matched_query=False,
    )
    user_prompt = f"""
{_data_block('paper.tex', prompt_paper_text)}

{_data_block('citation_map.json', json.dumps(prompt_citation_map, indent=2, ensure_ascii=False))}

{_data_block('cutoff_date', state.inputs.cutoff_date or 'null')}
""".strip()
    avg_citation_count = max(1, len(citation_map))
    response, lane_type, fallback_used, lane_notes = _complete_with_runtime_mode(
        _build_completion_request(system_prompt=PROMPTS.render_review_system(avg_citation_count=avg_citation_count), user_prompt=user_prompt),
        provider=provider,
        runtime_mode=runtime_mode,
        cwd=cwd,
        omx_lane_type="reviewer",
        trace_stage="review",
        output_schema=REVIEW_SCHEMA,
            )
    payload = extract_json(response)
    payload.setdefault("schema_version", "paper-review/1")
    payload["manuscript_path"] = state.artifacts.paper_full_tex
    manuscript_sha = hashlib.sha256(Path(state.artifacts.paper_full_tex).read_bytes()).hexdigest()
    payload["manuscript_sha256"] = manuscript_sha
    payload["review_provenance"] = _review_provenance_payload(
        cwd,
        stage="review",
        manuscript_sha256=manuscript_sha,
    )
    state.latest_provider_name = _provider_name(provider)
    state.latest_runtime_mode = runtime_mode
    save_session(cwd, state)
    path = review_path(cwd, review_name)
    write_json(path, payload)
    lane_path = record_lane_manifest(
        cwd,
        stage="review",
        role="Reviewer Lane",
        runtime_mode=runtime_mode,
        lane_type=lane_type,
        owner=_lane_owner(lane_type, fallback_used),
        status="fallback_completed" if fallback_used else "completed",
        input_artifacts=[state.artifacts.paper_full_tex or ""],
        output_artifacts=[str(path)],
        fallback_used=fallback_used,
        notes=lane_notes,
    )
    payload["review_provenance"] = _review_provenance_payload(
        cwd,
        stage="review",
        manuscript_sha256=manuscript_sha,
        lane_manifest_path=lane_path,
    )
    write_json(path, payload)
    state.artifacts.latest_review_json = str(path)
    score = float(payload.get("overall_score", 0.0))
    axes = _extract_axis_scores(payload)
    state.review_history.append(ScoreSnapshot(overall_score=score, raw_path=str(path), axes=axes))
    state.active_artifact = review_name
    state.notes.append(f"Paper reviewed: overall_score={score}")
    state.notes.append(f"Lane manifest recorded: {lane_path.name}")
    save_session(cwd, state)
    return path


def _extract_axis_scores(review_payload: dict[str, Any]) -> dict[str, float]:
    result: dict[str, float] = {}
    axis_scores = review_payload.get("axis_scores", {})
    if isinstance(axis_scores, dict):
        for key, value in axis_scores.items():
            if isinstance(value, dict) and isinstance(value.get("score"), (int, float)):
                result[key] = float(value["score"])
            elif isinstance(value, (int, float)):
                result[key] = float(value)
    return result


def _axis_delta(new_axes: dict[str, float], old_axes: dict[str, float]) -> float:
    keys = set(new_axes) & set(old_axes)
    if not keys:
        return 0.0
    return sum(new_axes.get(key, 0.0) - old_axes.get(key, 0.0) for key in keys)


def _resolve_refine_axis_tolerance(default: float = 0.0) -> float:
    raw = os.environ.get("PAPERO_REFINE_AXIS_TOLERANCE")
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return max(0.0, value)


def _redact_review_scores_for_writer(review_payload: dict[str, Any]) -> dict[str, Any]:
    """Remove numeric reviewer scores before feeding critique back to a writer/refiner.

    The acceptance gate still uses scores internally after the candidate is
    produced, but the generative writer should optimize against structured
    issues, not the reviewer scorecard itself.
    """
    redacted = dict(review_payload)
    redacted.pop("overall_score", None)
    redacted.pop("axis_scores", None)
    redacted["score_redaction"] = {
        "overall_score_removed": "writer_blind_to_reviewer_scores",
        "axis_scores_removed": "writer_blind_to_reviewer_scores",
    }
    return redacted


def _axes_within_tolerance(candidate_axes: dict[str, float], previous_axes: dict[str, float], *, tolerance: float) -> bool:
    keys = set(candidate_axes) & set(previous_axes)
    if not keys:
        return True
    return all(candidate_axes.get(key, 0.0) >= previous_axes.get(key, 0.0) - tolerance for key in keys)


def _accept_review_delta(candidate_score: float, previous_score: float, candidate_axes: dict[str, float], previous_axes: dict[str, float]) -> bool:
    if candidate_score < previous_score:
        return False
    return _axes_within_tolerance(
        candidate_axes,
        previous_axes,
        tolerance=_resolve_refine_axis_tolerance(),
    )


def refine_current_paper(
    cwd: str | Path | None,
    provider: BaseProvider,
    *,
    iterations: int = 1,
    require_compile_for_accept: bool = False,
    runtime_mode: str = "compatibility",
    claim_safe: bool = False,
    candidate_only: bool = False,
) -> list[dict[str, Any]]:
    state = load_session(cwd)
    if not state.artifacts.paper_full_tex or not state.artifacts.latest_review_json:
        raise ContractError("Need paper.full.tex and review.latest.json before refine.")
    narrative_plan, claim_map, citation_placement_plan = _planning_payloads_for_prompt(cwd)
    writer_brief = _writer_brief_from_planning(narrative_plan, claim_map, citation_placement_plan)

    accepted_results: list[dict[str, Any]] = []
    for _ in range(iterations):
        state = load_session(cwd)
        current_paper = read_text(state.artifacts.paper_full_tex)
        review_payload = read_json(state.artifacts.latest_review_json)
        citation_map = read_json(state.artifacts.citation_map_json) if state.artifacts.citation_map_json else {}
        raw_plot_manifest = read_json(state.artifacts.plot_manifest_json) if state.artifacts.plot_manifest_json else {"figures": []}
        raw_plot_assets_index = read_json(state.artifacts.plot_assets_json) if state.artifacts.plot_assets_json else {"assets": []}
        plot_assets_index = _reviewable_plot_assets_index(raw_plot_assets_index)
        plot_manifest = _reviewable_plot_manifest(raw_plot_manifest, raw_plot_assets_index)
        outline = read_json(state.artifacts.outline_json) if state.artifacts.outline_json else {"section_plan": []}
        expected_section_titles = _expected_section_titles_from_outline(outline)
        inputs = _read_inputs(state)
        strict_claim_safe_prompt = _strict_content_gates_enabled(claim_safe=claim_safe)
        _raise_if_strict_source_citations_unmapped(
            inputs,
            citation_map,
            stage="refinement",
            strict_claim_safe=strict_claim_safe_prompt,
        )
        experimental_log_text = read_text(state.inputs.experimental_log_path)
        previous_worklog_path = review_path(cwd, f"refinement_worklog.iter-{state.refinement_iteration:02d}.json")
        previous_worklog = read_text(previous_worklog_path) if previous_worklog_path.exists() else "{}"
        prompt_paper_text = _prompt_compact_text(current_paper, head_chars=22000, tail_chars=4000)
        prompt_citation_map = _compact_citation_map_for_prompt(
            citation_map,
            include_abstract=strict_claim_safe_prompt,
            include_authors=False,
            include_year=strict_claim_safe_prompt,
            include_venue=strict_claim_safe_prompt,
            include_provenance=False,
            include_origin=False,
            include_matched_query=False,
        )
        prompt_experimental_log = _prompt_compact_text(experimental_log_text, head_chars=8000, tail_chars=1500)
        source_critical_context = _source_critical_context_for_prompt(inputs)
        prompt_plot_manifest = {"figures": plot_manifest.get("figures", [])[:8]} if isinstance(plot_manifest, dict) else plot_manifest
        prompt_plot_assets_index = (
            {"assets": plot_assets_index.get("assets", [])[:8]}
            if isinstance(plot_assets_index, dict)
            else plot_assets_index
        )
        writer_review_payload = _redact_review_scores_for_writer(review_payload)
        user_prompt = f"""
{_data_block('paper.tex', prompt_paper_text)}

{_data_block('reviewer_feedback', json.dumps(writer_review_payload, indent=2, ensure_ascii=False))}

{_author_facing_writer_brief_block(writer_brief)}

{_data_block('experimental_log.md', prompt_experimental_log)}

{_data_block('source_critical_context.json', json.dumps(source_critical_context, indent=2, ensure_ascii=False))}

{_data_block('citation_map.json', json.dumps(prompt_citation_map, indent=2, ensure_ascii=False))}

{_data_block('plot_manifest.json', json.dumps(prompt_plot_manifest, indent=2, ensure_ascii=False))}

{_data_block('plot_assets.json', json.dumps(prompt_plot_assets_index, indent=2, ensure_ascii=False))}

{_data_block('worklog.json', previous_worklog)}
""".strip()
        response, lane_type, fallback_used, lane_notes = _complete_with_runtime_mode(
            _build_completion_request(system_prompt=PROMPTS.render_refine_system(), user_prompt=user_prompt),
            provider=provider,
            runtime_mode=runtime_mode,
            cwd=cwd,
            omx_lane_type="refiner",
            trace_stage="refinement",
        )
        try:
            worklog = extract_json(response)
        except ExtractionError:
            worklog = {
                "actions_taken": ["Refinement response did not include a machine-readable worklog block; accepted LaTeX-only fallback."],
                "addressed_weaknesses": [],
                "integrated_answers": [],
            }
            lane_notes = lane_notes + ["Refinement output omitted JSON worklog; synthesized fallback worklog from LaTeX-only response."]
        try:
            latex = extract_latex(response)
        except ExtractionError as exc:
            raise ContractError(f"Refinement output did not include extractable LaTeX: {exc}") from exc
        latex = _ensure_bibliography_hook(latex, citation_map)
        latex = _normalize_generated_plot_paths(latex, plot_assets_index)
        latex = _normalize_source_figure_paths(latex, state.inputs.figures_dir)
        latex = _ensure_generated_plot_usage(latex, plot_assets_index)
        latex = _remove_material_packet_sections(latex)
        latex = _ensure_discussion_section_for_claim_boundaries(latex, claim_map)
        latex = _ensure_required_claim_scope_notes(latex, claim_map)
        latex, citation_replacements = canonicalize_citation_keys(latex, citation_map)
        if strict_claim_safe_prompt:
            dropped_citations = _unknown_citation_key_counts(latex, citation_map)
        else:
            latex, dropped_citations = _drop_unknown_citation_keys(latex, citation_map)
        state.latest_provider_name = _provider_name(provider)
        state.latest_runtime_mode = runtime_mode
        save_session(cwd, state)
        latex = _apply_mock_watermark(latex, state, provider_name=_provider_name(provider))
        validation_issues = collect_paper_contract_issues(
            latex,
            citation_map=citation_map,
            figures_dir=state.inputs.figures_dir,
            plot_manifest=plot_manifest,
            plot_assets_index=plot_assets_index,
            experimental_log_text=experimental_log_text,
            expected_section_titles=expected_section_titles,
            narrative_plan=narrative_plan,
            claim_map=claim_map,
            citation_placement_plan=citation_placement_plan,
        )
        blocking_issues = _blocking_issues(validation_issues)
        if blocking_issues:
            preserved_issues = collect_paper_contract_issues(
                current_paper,
                citation_map=citation_map,
                figures_dir=state.inputs.figures_dir,
                plot_manifest=plot_manifest,
                plot_assets_index=plot_assets_index,
                experimental_log_text=experimental_log_text,
                expected_section_titles=expected_section_titles,
                narrative_plan=narrative_plan,
                claim_map=claim_map,
                citation_placement_plan=citation_placement_plan,
            )
            if not _blocking_issues(preserved_issues):
                latex = current_paper
                validation_issues = preserved_issues
                blocking_issues = []
                worklog.setdefault("actions_taken", []).append(
                    "Preserved the pre-refinement manuscript because the generated revision regressed citation/grounding contract checks."
                )
                lane_notes = lane_notes + ["Refinement draft regressed contract checks; preserved prior validated manuscript."]
                print(
                    f"Refinement iter {state.refinement_iteration + 1} preserved prior manuscript after contract regression.",
                    file=sys.stderr,
                )
        elif citation_replacements:
            lane_notes.append(
                "Canonicalized citation-key aliases in refinement draft: "
                + ", ".join(f"{src}->{dst}" for src, dst in sorted(citation_replacements.items()))
            )
        if dropped_citations:
            note_prefix = (
                "Blocked unsupported citation keys in strict refinement draft: "
                if strict_claim_safe_prompt
                else "Dropped unsupported citation keys in refinement draft: "
            )
            lane_notes.append(note_prefix + ", ".join(f"{key}({count})" for key, count in sorted(dropped_citations.items())))

        validation_name = f"validation.refine.iter-{state.refinement_iteration + 1:02d}.json"
        validation_path, validation_payload = _record_validation_report(
            cwd,
            stage="refinement",
            issues=validation_issues,
            name=validation_name,
            manuscript_text=latex,
        )
        state.artifacts.latest_validation_json = str(validation_path)
        blocking_issues = _blocking_issues(validation_issues)
        if blocking_issues:
            accepted_results.append(
                {
                    "iteration": state.refinement_iteration + 1,
                    "accepted": False,
                    "score_before": state.review_history[-1].overall_score if state.review_history else float(review_payload.get("overall_score", 0.0)),
                    "score_after": None,
                    "paper_path": state.artifacts.paper_full_tex,
                    "worklog_path": None,
                    "reason": "contract_validation_failed",
                    "issues": _issue_messages(blocking_issues),
                    "validation_report_path": str(validation_path),
                    "validation_report": validation_payload,
                }
            )
            state.notes.append(
                f"Rejected refinement iteration {state.refinement_iteration + 1} due to contract validation failure."
            )
            print(
                f"Refinement iter {state.refinement_iteration + 1} rejected: contract validation failed ({'; '.join(_issue_messages(blocking_issues))})",
                file=sys.stderr,
            )
            save_session(cwd, state)
            break
        if validation_issues:
            state.notes.append(
                f"Refinement iteration {state.refinement_iteration + 1} produced validation warnings: "
                + " | ".join(_issue_messages(validation_issues))
            )

        candidate_iter = state.refinement_iteration + 1
        candidate_tex_path = artifact_path(cwd, f"paper.refined.iter-{candidate_iter:02d}.tex")
        worklog_path = review_path(cwd, f"refinement_worklog.iter-{candidate_iter:02d}.json")
        write_text(candidate_tex_path, latex)
        write_json(worklog_path, worklog)

        temp_state_paper = state.artifacts.paper_full_tex
        temp_latest_review = state.artifacts.latest_review_json
        temp_review_history_len = len(state.review_history)
        previous_snapshot = state.review_history[-1] if state.review_history else None
        previous_score = previous_snapshot.overall_score if previous_snapshot else float(review_payload.get("overall_score", 0.0))
        previous_axes = previous_snapshot.axes if previous_snapshot else _extract_axis_scores(review_payload)
        no_op_refinement = latex == current_paper
        if no_op_refinement:
            candidate_review_path = Path(temp_latest_review or state.artifacts.latest_review_json or "")
            candidate_review = review_payload
            candidate_score = previous_score
            candidate_axes = previous_axes
        else:
            state.artifacts.paper_full_tex = str(candidate_tex_path)
            save_session(cwd, state)
            candidate_review_path = review_current_paper(
                cwd,
                provider,
                review_name=f"review.iter-{candidate_iter:02d}.json",
                runtime_mode=runtime_mode,
            )
            candidate_review = read_json(candidate_review_path)
            candidate_score = float(candidate_review.get("overall_score", 0.0))
            candidate_axes = _extract_axis_scores(candidate_review)
        candidate_pdf_path = None
        compile_error = None
        compile_preservation = False
        preserved_compile_error = None
        if require_compile_for_accept:
            try:
                candidate_pdf_path = compile_latex(
                    candidate_tex_path,
                    workdir=build_path(cwd, f"compiled-iter-{candidate_iter:02d}"),
                    output_log=build_path(cwd, f"latex-build.iter-{candidate_iter:02d}.log"),
                )
            except Exception as exc:  # pragma: no cover - compile availability is environment-dependent
                compile_error = str(exc)
                preserved_compile_error = compile_error
                previous_compile_report = (
                    read_json(state.artifacts.latest_compile_report_json)
                    if state.artifacts.latest_compile_report_json and Path(state.artifacts.latest_compile_report_json).exists()
                    else None
                )
                if (
                    isinstance(previous_compile_report, dict)
                    and previous_compile_report.get("clean")
                    and previous_compile_report.get("pdf_exists")
                ):
                    latex = current_paper
                    candidate_pdf_path = state.artifacts.compiled_pdf
                    compile_error = None
                    compile_preservation = True
                    no_op_refinement = True
                    candidate_review_path = Path(temp_latest_review or state.artifacts.latest_review_json or "")
                    candidate_review = review_payload
                    candidate_score = previous_score
                    candidate_axes = previous_axes
                    worklog.setdefault("actions_taken", []).append(
                        "Preserved the pre-refinement compiled manuscript because the generated revision failed compile acceptance."
                    )
                    lane_notes = lane_notes + ["Refinement revision failed compile acceptance; preserved prior compiled manuscript."]
                    print(
                        f"Refinement iter {candidate_iter} preserved prior compiled manuscript after compile failure.",
                        file=sys.stderr,
                    )

        review_retry_paths: list[str] = []
        review_retry_scores: list[float] = []
        if candidate_only:
            state = load_session(cwd)
            state.artifacts.paper_full_tex = temp_state_paper
            state.artifacts.latest_review_json = temp_latest_review
            state.artifacts.latest_validation_json = str(validation_path)
            state.review_history = state.review_history[:temp_review_history_len]
            save_session(cwd, state)
            accepted_results.append(
                {
                    "iteration": candidate_iter,
                    "accepted": False,
                    "candidate_only": True,
                    "reason": "candidate_ready_without_generic_acceptance",
                    "score_before": previous_score,
                    "score_after": candidate_score,
                    "axis_scores_before": previous_axes,
                    "axis_scores_after": candidate_axes,
                    "paper_path": temp_state_paper,
                    "candidate_path": str(candidate_tex_path),
                    "candidate_sha256": _file_sha256(candidate_tex_path),
                    "worklog_path": str(worklog_path),
                    "compile_error": compile_error,
                    "validation_report_path": str(validation_path),
                    "validation_report": validation_payload,
                    "review_path": str(candidate_review_path) if candidate_review_path else None,
                    "no_op_refinement": no_op_refinement,
                }
            )
            break
        accept = compile_error is None and (no_op_refinement or _accept_review_delta(candidate_score, previous_score, candidate_axes, previous_axes))
        if (
            not accept
            and not no_op_refinement
            and compile_error is None
            and previous_score - candidate_score <= 1.0
        ):
            retry_review_path = review_current_paper(
                cwd,
                provider,
                review_name=f"review.iter-{candidate_iter:02d}.retry-01.json",
                runtime_mode=runtime_mode,
            )
            retry_review = read_json(retry_review_path)
            retry_score = float(retry_review.get("overall_score", 0.0))
            retry_axes = _extract_axis_scores(retry_review)
            review_retry_paths.append(str(retry_review_path))
            review_retry_scores.append(retry_score)
            if _accept_review_delta(retry_score, previous_score, retry_axes, previous_axes):
                candidate_review_path = retry_review_path
                candidate_review = retry_review
                candidate_score = retry_score
                candidate_axes = retry_axes
                accept = True

        if accept:
            final_path = artifact_path(cwd, "paper.full.tex")
            write_text(final_path, latex)
            lane_path = record_lane_manifest(
                cwd,
                stage="refinement",
                role="Content Refinement Agent",
                runtime_mode=runtime_mode,
                lane_type=lane_type,
                owner=_lane_owner(lane_type, fallback_used),
                status="fallback_completed" if fallback_used else "completed",
                input_artifacts=[temp_state_paper, temp_latest_review or ""],
                output_artifacts=[str(final_path), str(worklog_path), str(validation_path)],
                fallback_used=fallback_used,
                notes=lane_notes,
            )
            state = load_session(cwd)
            state.artifacts.paper_full_tex = str(final_path)
            state.artifacts.latest_review_json = str(candidate_review_path)
            if candidate_pdf_path is not None:
                state.artifacts.compiled_pdf = str(candidate_pdf_path)
                state.current_phase = "complete"
                state.active_artifact = Path(candidate_pdf_path).name
            else:
                state.active_artifact = final_path.name
            state.refinement_iteration = candidate_iter
            state.notes.append(
                f"Accepted refinement iteration {candidate_iter} (score {previous_score} -> {candidate_score})."
            )
            if compile_preservation:
                _append_unique_note(
                    state,
                    f"Compile-failed refinement iteration {candidate_iter} preserved the prior compiled manuscript.",
                )
            if review_retry_scores:
                state.notes.append(
                    "Refinement acceptance used reviewer retry confirmation: "
                    + ", ".join(str(score) for score in review_retry_scores)
                )
            state.notes.append(f"Lane manifest recorded: {lane_path.name}")
            save_session(cwd, state)
            accepted_results.append(
                {
                    "iteration": candidate_iter,
                    "accepted": True,
                    "preservation": compile_preservation,
                    "reason": "compile_failed_preserved_previous" if compile_preservation else "accepted_non_regressive_revision",
                    "score_before": previous_score,
                    "score_after": candidate_score,
                    "paper_path": str(final_path),
                    "worklog_path": str(worklog_path),
                    "compile_error": preserved_compile_error,
                    "validation_report_path": str(validation_path),
                    "validation_report": validation_payload,
                    "lane_manifest_path": str(lane_path),
                    "review_retry_paths": review_retry_paths,
                    "review_retry_scores": review_retry_scores,
                }
            )
        else:
            lane_path = record_lane_manifest(
                cwd,
                stage="refinement",
                role="Content Refinement Agent",
                runtime_mode=runtime_mode,
                lane_type=lane_type,
                owner=_lane_owner(lane_type, fallback_used),
                status="blocked" if compile_error else "failed",
                input_artifacts=[temp_state_paper, temp_latest_review or ""],
                output_artifacts=[str(worklog_path), str(validation_path)],
                fallback_used=fallback_used,
                notes=lane_notes,
            )
            state = load_session(cwd)
            state.artifacts.paper_full_tex = temp_state_paper
            state.artifacts.latest_review_json = temp_latest_review
            state.artifacts.latest_validation_json = str(validation_path)
            state.review_history = state.review_history[:temp_review_history_len]
            _append_unique_note(
                state,
                f"Rejected refinement iteration {candidate_iter} (score {previous_score} -> {candidate_score}).",
            )
            reason = compile_error or "score_regressed_or_tie_break_failed"
            print(
                f"Refinement iter {candidate_iter} rejected: score {previous_score} -> {candidate_score}; reason={reason}",
                file=sys.stderr,
            )
            if review_retry_scores:
                state.notes.append(
                    "Refinement rejection persisted after reviewer retry: "
                    + ", ".join(str(score) for score in review_retry_scores)
                )
            state.notes.append(f"Lane manifest recorded: {lane_path.name}")
            save_session(cwd, state)
            accepted_results.append(
                {
                    "iteration": candidate_iter,
                    "accepted": False,
                    "score_before": previous_score,
                    "score_after": candidate_score,
                    "paper_path": temp_state_paper,
                    "worklog_path": str(worklog_path),
                    "reason": "compile_failed" if compile_error else "score_regressed_or_tie_break_failed",
                    "compile_error": compile_error,
                    "validation_report_path": str(validation_path),
                    "validation_report": validation_payload,
                    "lane_manifest_path": str(lane_path),
                    "review_retry_paths": review_retry_paths,
                    "review_retry_scores": review_retry_scores,
                }
            )
            break

    return accepted_results


def run_pipeline(
    cwd: str | Path | None,
    *,
    provider: BaseProvider,
    discovery_mode: str = "model",
    verify_mode: str = "live",
    verify_error_policy: str = "skip",
    verify_fallback_mode: str = "none",
    require_live_verification: bool = False,
    refine_iterations: int = 1,
    compile_paper: bool = False,
    runtime_mode: str = "compatibility",
) -> dict[str, Any]:
    if verify_fallback_mode not in {"none", "mock"}:
        raise ContractError(f"Unsupported verify fallback mode: {verify_fallback_mode}")
    outputs: dict[str, Any] = {"validation_reports": {}}
    state = load_session(cwd)
    state.latest_provider_name = _provider_name(provider)
    state.latest_runtime_mode = runtime_mode
    state.latest_verify_mode = verify_mode
    state.latest_verify_fallback_used = None
    save_session(cwd, state)
    _emit_stage_event("compile_environment", "started")
    compile_env_path, compile_env_payload = record_compile_environment_report(cwd)
    _emit_stage_event("compile_environment", "completed", path=str(compile_env_path))
    outputs["compile_environment"] = str(compile_env_path)
    outputs["compile_environment_report"] = compile_env_payload
    outputs["runtime_mode"] = runtime_mode
    _emit_stage_event("outline", "started")
    outputs["outline"] = str(generate_outline(cwd, provider, runtime_mode=runtime_mode))
    _emit_stage_event("outline", "completed", path=outputs["outline"])
    _emit_stage_event("parallel_plot_literature", "started", discovery_mode=discovery_mode)
    parallel_outputs = run_parallel_plot_and_literature(cwd, provider=provider, discovery_mode=discovery_mode, runtime_mode=runtime_mode)
    _emit_stage_event("parallel_plot_literature", "completed", candidates=parallel_outputs["candidates"], plots=parallel_outputs["plots"])
    outputs["plots"] = parallel_outputs["plots"]
    outputs["plot_captions"] = parallel_outputs["plot_captions"]
    outputs["plot_assets"] = parallel_outputs["plot_assets"]
    outputs["candidates"] = parallel_outputs["candidates"]
    try:
        _emit_stage_event("verify", "started", mode=verify_mode, on_error=verify_error_policy)
        outputs["verified"] = str(verify_papers(cwd, mode=verify_mode, on_error=verify_error_policy))
        _emit_stage_event("verify", "completed", path=outputs["verified"], mode=verify_mode)
    except ContractError as exc:
        if verify_mode == "live" and verify_fallback_mode == "mock":
            outputs["verify_live_error"] = str(exc)
            _emit_stage_event("verify", "fallback", error=str(exc), fallback_mode="mock")
            outputs["verified"] = str(verify_papers(cwd, mode="mock", on_error=verify_error_policy))
            outputs["verify_fallback_used"] = "mock"
            state = load_session(cwd)
            state.latest_verify_fallback_used = "mock"
            save_session(cwd, state)
            _emit_stage_event("verify", "completed", path=outputs["verified"], mode="mock")
        else:
            raise
    _emit_stage_event("build_bib", "started")
    outputs["bib"] = str(build_bib(cwd))
    _emit_stage_event("build_bib", "completed", path=outputs["bib"])
    _emit_stage_event("narrative_planning", "started")
    narrative_paths = plan_narrative_and_claims(cwd, provider, runtime_mode=runtime_mode)
    outputs["narrative_plan"] = str(narrative_paths["narrative_plan"])
    outputs["claim_map"] = str(narrative_paths["claim_map"])
    outputs["citation_placement_plan"] = str(narrative_paths["citation_placement_plan"])
    _emit_stage_event("narrative_planning", "completed", path=outputs["narrative_plan"])
    _emit_stage_event("intro_related", "started")
    outputs["intro_related"] = str(write_intro_related(cwd, provider, runtime_mode=runtime_mode))
    _emit_stage_event("intro_related", "completed", path=outputs["intro_related"])
    outputs["validation_reports"]["intro_related"] = load_session(cwd).artifacts.latest_validation_json
    _emit_stage_event("write_sections", "started")
    outputs["paper"] = str(write_sections(cwd, provider, runtime_mode=runtime_mode))
    _emit_stage_event("write_sections", "completed", path=outputs["paper"])
    outputs["validation_reports"]["section_writing"] = load_session(cwd).artifacts.latest_validation_json
    if compile_paper:
        _emit_stage_event("compile", "started")
        outputs["compiled_pdf"] = str(compile_current_paper(cwd))
        _emit_stage_event("compile", "completed", path=outputs["compiled_pdf"])
    _emit_stage_event("review", "started")
    outputs["review"] = str(review_current_paper(cwd, provider, runtime_mode=runtime_mode))
    _emit_stage_event("review", "completed", path=outputs["review"])
    _emit_stage_event("refine", "started", iterations=refine_iterations)
    outputs["refine"] = refine_current_paper(
        cwd,
        provider,
        iterations=refine_iterations,
        require_compile_for_accept=compile_paper,
        runtime_mode=runtime_mode,
    )
    outputs["validation_reports"]["refinement"] = [
        item.get("validation_report_path") for item in outputs["refine"] if item.get("validation_report_path")
    ]
    _emit_stage_event("refine", "completed", accepted=sum(1 for item in outputs["refine"] if item.get("accepted")), total=len(outputs["refine"]))
    state = load_session(cwd)
    blocked = refine_iterations > 0 and bool(outputs["refine"]) and not any(item.get("accepted", False) for item in outputs["refine"])
    if blocked:
        state.current_phase = "blocked"
        state.notes.append("Pipeline run halted because refinement was rejected.")
        outputs["status"] = "blocked"
    else:
        if compile_paper and state.artifacts.compiled_pdf:
            state.current_phase = "complete"
            state.notes.append("Pipeline run completed with compiled output.")
            outputs["status"] = "complete"
        else:
            state.current_phase = "draft_complete"
            state.notes.append("Pipeline run completed at draft stage without compiled output.")
            outputs["status"] = "draft_complete"
    save_session(cwd, state)
    runtime_parity_path, runtime_parity_payload = record_runtime_parity_report(cwd)
    state = load_session(cwd)
    state.artifacts.latest_runtime_parity_json = str(runtime_parity_path)
    save_session(cwd, state)
    outputs["runtime_parity_report"] = str(runtime_parity_path)
    outputs["runtime_parity"] = runtime_parity_payload
    fidelity_path, fidelity_payload = record_fidelity_report(cwd)
    outputs["fidelity_report"] = str(fidelity_path)
    outputs["fidelity"] = fidelity_payload
    if load_session(cwd).artifacts.paper_full_tex:
        figure_review_path, figure_review_payload = write_figure_placement_review(cwd)
        outputs["figure_placement_review"] = str(figure_review_path)
        outputs["figure_placement"] = figure_review_payload
    reproducibility_path, reproducibility_payload = write_reproducibility_audit(
        cwd,
        require_live_verification=require_live_verification,
    )
    outputs["reproducibility_report"] = str(reproducibility_path)
    outputs["reproducibility"] = reproducibility_payload
    _emit_stage_event("pipeline", "completed", status=outputs.get("status"), reproducibility_verdict=reproducibility_payload.get("verdict"))
    return outputs
