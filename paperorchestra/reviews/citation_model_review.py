from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json
from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.reviews.citation_model_cache import (
    _citation_support_cache_dir,
    _citation_support_cache_key,
    _citation_support_provider_identity,
    _reuse_cached_citation_review,
)
from paperorchestra.reviews.citation_model_merge import _merge_model_citation_review
from paperorchestra.reviews.citation_model_prompt import _build_model_citation_review
from paperorchestra.reviews.citation_items import (
    _heuristic_citation_items,
    _summary_from_items,
)
from paperorchestra.reviews.citation_evidence import (
    citation_item_has_valid_supporting_evidence,
)
from paperorchestra.reviews.citation_progress import (
    _append_citation_progress_checkpoint,
    _citation_progress_cite_label,
    _citation_progress_claim_input_sha256,
    _citation_progress_path,
    _citation_progress_provider_identity_sha256,
    _emit_citation_progress,
    _load_citation_progress_checkpoint,
)
from paperorchestra.reviews.citation_web_evidence import (
    _build_web_evidence_retrieval,
    _citation_support_retrieved_evidence_sha256,
    _retrieved_evidence_file_sha256,
    _retrieved_web_evidence_for_item_ids,
    _retrieved_web_evidence_is_reusable,
)
from paperorchestra.reviews.source_support import (
    build_source_backed_citation_support_review,
    render_citation_support_human_needed_markdown,
)
from paperorchestra.runtime.providers import (
    BaseProvider,
)


def _build_model_citation_review_with_progress(
    *,
    provider: BaseProvider,
    items: list[dict[str, Any]],
    web_search_required: bool,
    evidence_mode: str,
    manuscript_sha256: str,
    citation_map_sha256: str | None,
    provider_identity: dict[str, Any],
    retrieved_web_evidence: dict[str, Any] | None = None,
    retrieved_web_evidence_sha256: str | None = None,
    progress_stream: Any = None,
    progress_checkpoint_path: Path | None = None,
) -> dict[str, Any]:
    completed = _load_citation_progress_checkpoint(
        progress_checkpoint_path,
        manuscript_sha256=manuscript_sha256,
        citation_map_sha256=citation_map_sha256,
        evidence_mode=evidence_mode,
        provider_identity=provider_identity,
        retrieved_web_evidence_sha256=retrieved_web_evidence_sha256,
        items=items,
    )
    provider_identity_sha256 = _citation_progress_provider_identity_sha256(provider_identity)
    merged_items: list[dict[str, Any]] = []
    research_notes: list[str] = []
    claim_traces: list[dict[str, Any]] = []
    reused_claims = 0
    claim_count = len(items)
    for index, item in enumerate(items, start=1):
        claim_id = str(item.get("id"))
        cite_label = _citation_progress_cite_label(item)
        cached_item = completed.get(claim_id)
        if cached_item is not None:
            reused_claims += 1
            _emit_citation_progress(progress_stream, f"reusing {index}/{claim_count} cite={cite_label} id={claim_id}")
            merged_items.append(cached_item)
            continue

        _emit_citation_progress(progress_stream, f"checking {index}/{claim_count} cite={cite_label} id={claim_id}")
        item_retrieved_web_evidence = _retrieved_web_evidence_for_item_ids(retrieved_web_evidence, {claim_id})
        model_payload = _build_model_citation_review(
            provider=provider,
            items=[item],
            web_search_required=web_search_required,
            retrieved_web_evidence=item_retrieved_web_evidence if web_search_required else None,
        )
        trace = model_payload.pop("_trace", None)
        if isinstance(trace, dict):
            trace = dict(trace)
            trace["claim_id"] = claim_id
            trace["claim_index"] = index
            claim_traces.append(trace)
        if isinstance(model_payload.get("research_notes"), list):
            research_notes.extend(str(note) for note in model_payload.get("research_notes", []))
        merged = _merge_model_citation_review([item], model_payload)
        merged_item = merged[0] if merged else dict(item)
        merged_items.append(merged_item)
        _append_citation_progress_checkpoint(
            progress_checkpoint_path,
            {
                "schema_version": "citation-support-progress-checkpoint/1",
                "event": "checked",
                "manuscript_sha256": manuscript_sha256,
                "citation_map_sha256": citation_map_sha256,
                "evidence_mode": evidence_mode,
                "provider_identity_sha256": provider_identity_sha256,
                "retrieved_web_evidence_sha256": retrieved_web_evidence_sha256,
                "claim_id": claim_id,
                "claim_index": index,
                "claim_count": claim_count,
                "citation_keys": item.get("citation_keys") or [],
                "claim_input_sha256": _citation_progress_claim_input_sha256(item),
                "item": merged_item,
            },
        )
        _emit_citation_progress(progress_stream, f"checked {index}/{claim_count} cite={cite_label} id={claim_id}")

    return {
        "items": merged_items,
        "research_notes": research_notes,
        "_trace": {
            "schema_version": "citation-support-trace/1",
            "chunked": True,
            "claim_count": claim_count,
            "reused_claims": reused_claims,
            "checked_claims": claim_count - reused_claims,
            "web_search_required": web_search_required,
            "claim_traces": claim_traces,
            "progress_checkpoint_path": str(progress_checkpoint_path) if progress_checkpoint_path is not None else None,
        },
    }


def build_citation_support_review(
    cwd: str | Path | None,
    *,
    provider: BaseProvider | None = None,
    evidence_mode: str = "heuristic",
    retrieved_web_evidence: dict[str, Any] | None = None,
    retrieved_web_evidence_sha256: str | None = None,
    retrieved_web_evidence_path: str | None = None,
    progress_stream: Any = None,
    progress_checkpoint_path: str | Path | None = None,
) -> dict[str, Any]:
    if evidence_mode not in {"heuristic", "model", "web", "source"}:
        raise ValueError(f"Unsupported citation evidence mode: {evidence_mode}")
    if evidence_mode == "source":
        return build_source_backed_citation_support_review(cwd, mode=evidence_mode)
    state = load_session(cwd)
    if not state.artifacts.paper_full_tex:
        raise ValueError("Need paper.full.tex before citation support review.")
    latex = Path(state.artifacts.paper_full_tex).read_text(encoding="utf-8")
    manuscript_sha256 = hashlib.sha256(Path(state.artifacts.paper_full_tex).read_bytes()).hexdigest()
    citation_map = read_json(state.artifacts.citation_map_json) if state.artifacts.citation_map_json else {}
    citation_map_sha256 = None
    if state.artifacts.citation_map_json and Path(state.artifacts.citation_map_json).exists():
        citation_map_sha256 = hashlib.sha256(Path(state.artifacts.citation_map_json).read_bytes()).hexdigest()
    items = _heuristic_citation_items(latex, citation_map)
    model_payload: dict[str, Any] | None = None
    model_trace: dict[str, Any] | None = None
    provider_identity = _citation_support_provider_identity(provider)
    if evidence_mode in {"model", "web"}:
        if provider is None:
            raise ValueError(f"evidence_mode={evidence_mode!r} requires a provider.")
        if progress_stream is not None or progress_checkpoint_path is not None:
            model_payload = _build_model_citation_review_with_progress(
                provider=provider,
                items=items,
                web_search_required=evidence_mode == "web",
                evidence_mode=evidence_mode,
                manuscript_sha256=manuscript_sha256,
                citation_map_sha256=citation_map_sha256,
                provider_identity=provider_identity,
                retrieved_web_evidence=retrieved_web_evidence if evidence_mode == "web" else None,
                retrieved_web_evidence_sha256=retrieved_web_evidence_sha256 if evidence_mode == "web" else None,
                progress_stream=progress_stream,
                progress_checkpoint_path=Path(progress_checkpoint_path).resolve() if progress_checkpoint_path is not None else None,
            )
            model_trace = model_payload.pop("_trace", None)
            items = model_payload.get("items") if isinstance(model_payload.get("items"), list) else items
        else:
            model_payload = _build_model_citation_review(
                provider=provider,
                items=items,
                web_search_required=evidence_mode == "web",
                retrieved_web_evidence=retrieved_web_evidence if evidence_mode == "web" else None,
            )
            model_trace = model_payload.pop("_trace", None)
            items = _merge_model_citation_review(items, model_payload)
    summary = _summary_from_items(items)
    provider_command_digest = provider_identity.get("provider_command_digest")
    web_search_capable = bool(provider_identity.get("web_search_capable"))
    research_notes = model_payload.get("research_notes", []) if isinstance(model_payload, dict) else []
    if evidence_mode == "web" and not retrieved_web_evidence_sha256:
        retrieved_web_evidence_sha256 = _citation_support_retrieved_evidence_sha256(items, research_notes)
    return {
        "schema_version": "citation-support-review/2",
        "session_id": state.session_id,
        "manuscript_sha256": manuscript_sha256,
        "citation_map_sha256": citation_map_sha256,
        "review_mode": evidence_mode,
        "evidence_provenance": {
            "mode": evidence_mode,
            "semantic_scholar_required": False,
            "web_search_required": evidence_mode == "web",
            "model_review_used": evidence_mode in {"model", "web"},
            "provider_name": getattr(provider, "name", None) if provider is not None else None,
            "provider_command_digest": provider_command_digest,
            "provider_class": provider_identity.get("provider_class"),
            "provider_argv": provider_identity.get("provider_argv"),
            "provider_capability_proof": provider_identity.get("provider_capability_proof"),
            "provider_contract_path": provider_identity.get("provider_contract_path"),
            "provider_contract_sha256": provider_identity.get("provider_contract_sha256"),
            "provider_wrapper_path": provider_identity.get("provider_wrapper_path"),
            "provider_wrapper_sha256": provider_identity.get("provider_wrapper_sha256"),
            "provider_wrapper_mode": provider_identity.get("provider_wrapper_mode"),
            "provider_wrapper_exec_argv_prefix": provider_identity.get("provider_wrapper_exec_argv_prefix"),
            "web_search_capable": web_search_capable,
            "claim_support_not_metadata_lookup": True,
            "retrieved_web_evidence_sha256": retrieved_web_evidence_sha256,
            "retrieved_web_evidence_path": retrieved_web_evidence_path,
        },
        "claims_checked": len(items),
        "summary": summary,
        "items": items,
        "research_notes": research_notes,
        "_trace": model_trace,
    }


def write_citation_support_review(
    cwd: str | Path | None,
    output_path: str | Path | None = None,
    *,
    provider: BaseProvider | None = None,
    evidence_mode: str = "heuristic",
    progress_stream: Any = None,
    progress_checkpoint_path: str | Path | None = None,
) -> Path:
    state = load_session(cwd)
    path = Path(output_path).resolve() if output_path else artifact_path(cwd, "citation_support_review.json")
    checkpoint_path = (
        Path(progress_checkpoint_path).resolve()
        if progress_checkpoint_path is not None
        else (_citation_progress_path(path) if (progress_stream is not None and evidence_mode in {"model", "web"}) else None)
    )
    cache_key = None
    cache_payload_path: Path | None = None
    cache_trace_path: Path | None = None
    retrieved_web_evidence: dict[str, Any] | None = None
    retrieved_web_evidence_path: Path | None = None
    retrieved_web_evidence_sha256: str | None = None
    citation_review_cacheable = True
    if evidence_mode in {"model", "web"} and provider is not None:
        request_cache_key = _citation_support_cache_key(state, provider, evidence_mode)
        cache_dir = _citation_support_cache_dir(cwd)
        cache_dir.mkdir(parents=True, exist_ok=True)
        request_meta_path = cache_dir / f"{request_cache_key}.request.json"
        request_meta = read_json(request_meta_path) if request_meta_path.exists() else {}
        if request_meta_path.exists():
            if isinstance(request_meta, dict) and request_meta.get("cache_key_sha256"):
                cache_key = str(request_meta.get("cache_key_sha256"))
        else:
            cache_key = request_cache_key
        cache_payload_path = cache_dir / f"{cache_key}.json"
        cache_trace_path = cache_dir / f"{cache_key}.trace.json"
        cache_hit_allowed = True
        if evidence_mode == "web":
            retrieved_web_evidence_path = cache_dir / f"{request_cache_key}.retrieved-evidence.json"
            meta_evidence_path = request_meta.get("retrieved_web_evidence_path") if isinstance(request_meta, dict) else None
            if isinstance(meta_evidence_path, str):
                retrieved_web_evidence_path = Path(meta_evidence_path)
            meta_evidence_sha = str(request_meta.get("retrieved_web_evidence_sha256") or "") if isinstance(request_meta, dict) else ""
            actual_evidence_sha = _retrieved_evidence_file_sha256(retrieved_web_evidence_path)
            cache_hit_allowed = bool(meta_evidence_sha and actual_evidence_sha and meta_evidence_sha == actual_evidence_sha)
            if cache_hit_allowed and retrieved_web_evidence_path.exists():
                existing_evidence = read_json(retrieved_web_evidence_path)
                if not _retrieved_web_evidence_is_reusable(existing_evidence):
                    retrieved_web_evidence_path.unlink(missing_ok=True)
                    cache_hit_allowed = False
                    citation_review_cacheable = False
        if cache_hit_allowed:
            cached = _reuse_cached_citation_review(
                cwd=cwd,
                state=state,
                output_path=path,
                cache_payload_path=cache_payload_path,
                cache_trace_path=cache_trace_path,
                evidence_mode=evidence_mode,
            )
            if cached is not None:
                return cached
        if evidence_mode == "web":
            assert retrieved_web_evidence_path is not None
            if retrieved_web_evidence_path.exists():
                retrieved_web_evidence = read_json(retrieved_web_evidence_path)
                if not _retrieved_web_evidence_is_reusable(retrieved_web_evidence):
                    retrieved_web_evidence_path.unlink(missing_ok=True)
                    retrieved_web_evidence = None
                    cache_hit_allowed = False
                    citation_review_cacheable = False
            if retrieved_web_evidence is None:
                latex = Path(state.artifacts.paper_full_tex).read_text(encoding="utf-8")
                citation_map = read_json(state.artifacts.citation_map_json) if state.artifacts.citation_map_json else {}
                retrieval_items = _heuristic_citation_items(latex, citation_map)
                retrieved_web_evidence = _build_web_evidence_retrieval(
                    provider=provider,
                    items=retrieval_items,
                    progress_stream=progress_stream,
                )
                retrieved_web_evidence_path.write_text(
                    json.dumps(retrieved_web_evidence, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                citation_review_cacheable = _retrieved_web_evidence_is_reusable(retrieved_web_evidence)
            retrieved_web_evidence_sha256 = _retrieved_evidence_file_sha256(retrieved_web_evidence_path)
            cache_key = _citation_support_cache_key(
                state,
                provider,
                evidence_mode,
                retrieved_web_evidence_sha256=retrieved_web_evidence_sha256,
            )
            cache_payload_path = cache_dir / f"{cache_key}.json"
            cache_trace_path = cache_dir / f"{cache_key}.trace.json"
            if citation_review_cacheable:
                cached = _reuse_cached_citation_review(
                    cwd=cwd,
                    state=state,
                    output_path=path,
                    cache_payload_path=cache_payload_path,
                    cache_trace_path=cache_trace_path,
                    evidence_mode=evidence_mode,
                    note_suffix="retrieved-evidence cache",
                )
                if cached is not None:
                    return cached
    payload = build_citation_support_review(
        cwd,
        provider=provider,
        evidence_mode=evidence_mode,
        retrieved_web_evidence=retrieved_web_evidence,
        retrieved_web_evidence_sha256=retrieved_web_evidence_sha256,
        retrieved_web_evidence_path=str(retrieved_web_evidence_path) if retrieved_web_evidence_path is not None else None,
        progress_stream=progress_stream,
        progress_checkpoint_path=checkpoint_path,
    )
    if checkpoint_path is not None:
        provenance = payload.setdefault("evidence_provenance", {})
        provenance["progress_checkpoint_path"] = str(checkpoint_path)
        if checkpoint_path.exists():
            provenance["progress_checkpoint_sha256"] = hashlib.sha256(checkpoint_path.read_bytes()).hexdigest()
    if cache_key and citation_review_cacheable:
        provenance = payload.setdefault("evidence_provenance", {})
        evidence_sha = provenance.get("retrieved_web_evidence_sha256") if evidence_mode == "web" else None
        if evidence_mode == "web":
            cache_key = _citation_support_cache_key(
                state,
                provider,
                evidence_mode,
                retrieved_web_evidence_sha256=str(evidence_sha) if evidence_sha else None,
            )
        cache_payload_path = _citation_support_cache_dir(cwd) / f"{cache_key}.json"
        cache_trace_path = _citation_support_cache_dir(cwd) / f"{cache_key}.trace.json"
        provenance["cache_key_sha256"] = cache_key
        provenance["cache_scope"] = "session_id"
        provenance["evidence_identity_source"] = "pre_review_retrieved_evidence_artifact" if evidence_sha else "not_applicable"
    trace_payload = payload.pop("_trace", None)
    if isinstance(trace_payload, dict):
        trace_payload = dict(trace_payload)
        trace_payload.update(
            {
                "manuscript_sha256": payload.get("manuscript_sha256"),
                "citation_map_sha256": payload.get("citation_map_sha256"),
                "review_mode": payload.get("review_mode"),
                "provider_command_digest": (payload.get("evidence_provenance") or {}).get("provider_command_digest"),
                "provider_capability_proof": (payload.get("evidence_provenance") or {}).get("provider_capability_proof"),
                "provider_contract_path": (payload.get("evidence_provenance") or {}).get("provider_contract_path"),
                "provider_contract_sha256": (payload.get("evidence_provenance") or {}).get("provider_contract_sha256"),
                "provider_wrapper_path": (payload.get("evidence_provenance") or {}).get("provider_wrapper_path"),
                "provider_wrapper_sha256": (payload.get("evidence_provenance") or {}).get("provider_wrapper_sha256"),
                "provider_wrapper_mode": (payload.get("evidence_provenance") or {}).get("provider_wrapper_mode"),
                "web_search_capable": (payload.get("evidence_provenance") or {}).get("web_search_capable"),
                "review_items_sha256": hashlib.sha256(
                    json.dumps(payload.get("items") or [], sort_keys=True, ensure_ascii=False).encode("utf-8")
                ).hexdigest(),
            }
        )
        trace_path = path.with_name(path.stem + ".trace.json")
        trace_text = json.dumps(trace_payload, indent=2, ensure_ascii=False) + "\n"
        trace_path.write_text(trace_text, encoding="utf-8")
        trace_sha = hashlib.sha256(trace_text.encode("utf-8")).hexdigest()
        payload.setdefault("evidence_provenance", {})["review_trace_path"] = str(trace_path)
        payload.setdefault("evidence_provenance", {})["review_trace_sha256"] = trace_sha
    path.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    human_needed_markdown = render_citation_support_human_needed_markdown(payload)
    human_needed_markdown_path = path.with_name("citation_support_human_needed.md")
    if human_needed_markdown:
        human_needed_markdown_path.write_text(human_needed_markdown, encoding="utf-8")
    else:
        human_needed_markdown_path.unlink(missing_ok=True)
    if cache_payload_path is not None:
        cache_payload_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        if evidence_mode in {"model", "web"} and provider is not None:
            request_cache_key = _citation_support_cache_key(state, provider, evidence_mode)
            request_meta_path = _citation_support_cache_dir(cwd) / f"{request_cache_key}.request.json"
            request_meta_path.write_text(
                json.dumps(
                    {
                        "schema_version": "citation-support-cache-request/1",
                        "cache_scope": "session_id",
                        "cache_key_sha256": cache_key,
                        "retrieved_web_evidence_sha256": (payload.get("evidence_provenance") or {}).get("retrieved_web_evidence_sha256"),
                        "retrieved_web_evidence_path": (payload.get("evidence_provenance") or {}).get("retrieved_web_evidence_path"),
                    },
                    indent=2,
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
        trace_path_value = (payload.get("evidence_provenance") or {}).get("review_trace_path")
        if cache_trace_path is not None and isinstance(trace_path_value, str) and Path(trace_path_value).exists():
            shutil.copy2(trace_path_value, cache_trace_path)
    state.notes.append(f"Citation-support critic artifact recorded: {path.name} (mode={evidence_mode})")
    save_session(cwd, state)
    return path
