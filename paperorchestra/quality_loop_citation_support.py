from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .critics import citation_item_has_valid_supporting_evidence, extract_cited_sentences
from .providers import ShellProvider, get_citation_support_provider
from .quality_loop_policy import CITATION_SUPPORT_STATUSES
from .quality_loop_utils import _file_sha256, _read_json_if_exists
from .session import artifact_path


def _citation_support_path(cwd: str | Path | None, state) -> Path:
    if state.artifacts.paper_full_tex:
        return Path(state.artifacts.paper_full_tex).resolve().parent / "citation_support_review.json"
    return artifact_path(cwd, "citation_support_review.json")

def _provider_proof_is_trusted(provenance: dict[str, Any], expected_direct_digest: str | None) -> bool:
    if provenance.get("web_search_capable") is not True or not provenance.get("provider_command_digest"):
        return False
    proof = provenance.get("provider_capability_proof")
    if proof == "direct-codex-search/1" or proof is None:
        return bool(expected_direct_digest and provenance.get("provider_command_digest") == expected_direct_digest)
    if proof != "provider-wrapper-contract/1":
        return False
    contract_path = provenance.get("provider_contract_path")
    wrapper_path = provenance.get("provider_wrapper_path")
    if not isinstance(contract_path, str) or not isinstance(wrapper_path, str):
        return False
    contract = Path(contract_path)
    wrapper = Path(wrapper_path)
    if not contract.exists() or not wrapper.exists():
        return False
    if _file_sha256(contract) != provenance.get("provider_contract_sha256"):
        return False
    if _file_sha256(wrapper) != provenance.get("provider_wrapper_sha256"):
        return False
    try:
        payload = json.loads(contract.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict) or payload.get("schema_version") != "provider-wrapper-contract/1":
        return False
    try:
        if Path(str(payload.get("wrapper_path") or "")).resolve() != wrapper.resolve():
            return False
    except (OSError, RuntimeError):
        return False
    modes = payload.get("modes")
    mode = modes.get("web") if isinstance(modes, dict) else None
    return (
        isinstance(mode, dict)
        and mode.get("trace_wrapped") is True
        and mode.get("web_search_capable") is True
        and mode.get("exec_argv_prefix") == ["codex", "--search", "exec"]
        and provenance.get("provider_wrapper_mode") == "web"
    )


def _trace_matches_provider_proof(trace_payload: dict[str, Any], provenance: dict[str, Any]) -> bool:
    for key in [
        "provider_capability_proof",
        "provider_contract_path",
        "provider_contract_sha256",
        "provider_wrapper_path",
        "provider_wrapper_sha256",
        "provider_wrapper_mode",
    ]:
        if provenance.get(key) is not None and trace_payload.get(key) != provenance.get(key):
            return False
    return True


def _citation_support_check(cwd: str | Path | None, state, *, quality_mode: str = "ralph") -> dict[str, Any]:
    path = _citation_support_path(cwd, state)
    payload = _read_json_if_exists(path)
    if not isinstance(payload, dict):
        return {"status": "fail", "path": str(path), "failing_codes": ["citation_support_review_missing"], "summary": None}
    current_sha = _file_sha256(state.artifacts.paper_full_tex)
    if current_sha and payload.get("manuscript_sha256") != current_sha:
        return {
            "status": "fail",
            "path": str(path),
            "failing_codes": ["citation_support_review_stale"],
            "summary": None,
            "expected_manuscript_sha256": current_sha,
            "actual_manuscript_sha256": payload.get("manuscript_sha256"),
        }
    raw_items = payload.get("items") if isinstance(payload.get("items"), list) else []
    items = [item for item in raw_items if isinstance(item, dict)]
    summary: dict[str, int] = {}
    invalid_status_count = 0
    invalid_status_values: list[str] = []
    for item in items:
        status_value = str(item.get("support_status") or "needs_manual_check")
        if status_value not in CITATION_SUPPORT_STATUSES:
            invalid_status_count += 1
            invalid_status_values.append(status_value)
        summary[status_value] = summary.get(status_value, 0) + 1
    reported_summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    provenance = payload.get("evidence_provenance") if isinstance(payload.get("evidence_provenance"), dict) else {}
    legacy_untrusted = payload.get("schema_version") != "citation-support-review/2" or provenance.get("claim_support_not_metadata_lookup") is not True
    summary_mismatch = reported_summary != summary
    claims_checked = payload.get("claims_checked")
    claim_count_mismatch = claims_checked != len(items)
    current_cited_sentence_count = 0
    if state.artifacts.paper_full_tex and Path(state.artifacts.paper_full_tex).exists():
        current_cited_sentence_count = len(extract_cited_sentences(Path(state.artifacts.paper_full_tex).read_text(encoding="utf-8")))
    cited_sentence_coverage_mismatch = current_cited_sentence_count != len(items)
    current_citation_map_sha = _file_sha256(state.artifacts.citation_map_json)
    citation_map_stale = bool(current_citation_map_sha and payload.get("citation_map_sha256") != current_citation_map_sha)
    current_citation_map = _read_json_if_exists(state.artifacts.citation_map_json)
    if not isinstance(current_citation_map, dict):
        current_citation_map = {}
    def _item_with_current_citation_entries(item: dict[str, Any]) -> dict[str, Any]:
        updated = dict(item)
        entries = []
        for key in item.get("citation_keys") or []:
            entry = current_citation_map.get(key, {}) if isinstance(current_citation_map, dict) else {}
            entry_payload = dict(entry) if isinstance(entry, dict) else {}
            entry_payload["key"] = key
            entries.append(entry_payload)
        updated["citation_entries"] = entries
        return updated

    expected_web_digest = None
    if quality_mode == "claim_safe":
        try:
            expected_provider = get_citation_support_provider("shell", evidence_mode="web")
            if isinstance(expected_provider, ShellProvider):
                expected_web_digest = hashlib.sha256(json.dumps(expected_provider.argv, ensure_ascii=False).encode("utf-8")).hexdigest()
        except Exception:
            expected_web_digest = None
    unsupported = int(summary.get("unsupported") or 0)
    contradicted = int(summary.get("contradicted") or 0)
    weak = int(summary.get("weakly_supported") or 0)
    manual = int(summary.get("needs_manual_check") or 0)
    metadata_only = int(summary.get("metadata_only") or 0)
    insufficient = int(summary.get("insufficient_evidence") or 0)
    model_review_used = bool(provenance.get("model_review_used"))
    evidence_missing_count = 0
    non_web_supported_count = 0
    untrusted_web_provenance_count = 0
    trace_missing_count = 0
    trace_mismatch_count = 0
    trace_invalid_count = 0
    trace_path = provenance.get("review_trace_path")
    trace_sha = provenance.get("review_trace_sha256")
    actual_trace_sha = _file_sha256(trace_path) if isinstance(trace_path, str) else None
    trace_payload = _read_json_if_exists(trace_path) if isinstance(trace_path, str) else None
    for item in items:
        if item.get("support_status") == "supported":
            if quality_mode == "claim_safe" and provenance.get("web_search_required") is not True:
                non_web_supported_count += 1
            if quality_mode == "claim_safe" and (
                provenance.get("web_search_required") is True
                and not _provider_proof_is_trusted(provenance, expected_web_digest)
            ):
                untrusted_web_provenance_count += 1
            if quality_mode == "claim_safe" and provenance.get("web_search_required") is True:
                if not actual_trace_sha:
                    trace_missing_count += 1
                elif trace_sha != actual_trace_sha:
                    trace_mismatch_count += 1
                elif not isinstance(trace_payload, dict) or (
                    trace_payload.get("schema_version") != "citation-support-trace/1"
                    or trace_payload.get("manuscript_sha256") != payload.get("manuscript_sha256")
                    or trace_payload.get("citation_map_sha256") != payload.get("citation_map_sha256")
                    or trace_payload.get("review_mode") != "web"
                    or trace_payload.get("web_search_required") is not True
                    or trace_payload.get("provider_command_digest") != provenance.get("provider_command_digest")
                    or trace_payload.get("web_search_capable") is not True
                    or not _trace_matches_provider_proof(trace_payload, provenance)
                    or trace_payload.get("review_items_sha256")
                    != hashlib.sha256(json.dumps(items, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
                    or not trace_payload.get("system_prompt_sha256")
                    or not trace_payload.get("user_prompt_sha256")
                    or not trace_payload.get("response_sha256")
                ):
                    trace_invalid_count += 1
            if not citation_item_has_valid_supporting_evidence(_item_with_current_citation_entries(item)):
                evidence_missing_count += 1
    failing_codes: list[str] = []
    if unsupported:
        failing_codes.append("citation_support_unsupported")
    if contradicted:
        failing_codes.append("citation_support_contradicted")
    if weak:
        failing_codes.append("citation_support_weak")
    if manual:
        failing_codes.append("citation_support_manual_check")
    if metadata_only:
        failing_codes.append("citation_support_metadata_only")
    if insufficient:
        failing_codes.append("citation_support_insufficient_evidence")
    if evidence_missing_count:
        failing_codes.append("citation_support_evidence_missing")
    if legacy_untrusted:
        failing_codes.append("citation_support_review_legacy_untrusted")
    if summary_mismatch:
        failing_codes.append("citation_support_summary_mismatch")
    if claim_count_mismatch:
        failing_codes.append("citation_support_claim_count_mismatch")
    if cited_sentence_coverage_mismatch:
        failing_codes.append("citation_support_sentence_coverage_mismatch")
    if citation_map_stale:
        failing_codes.append("citation_support_citation_map_stale")
    if invalid_status_count:
        failing_codes.append("citation_support_invalid_status")
    if non_web_supported_count:
        failing_codes.append("citation_support_non_web_supported")
    if untrusted_web_provenance_count:
        failing_codes.append("citation_support_untrusted_web_provenance")
    if trace_missing_count:
        failing_codes.append("citation_support_trace_missing")
    if trace_mismatch_count:
        failing_codes.append("citation_support_trace_mismatch")
    if trace_invalid_count:
        failing_codes.append("citation_support_trace_invalid")
    status = "fail" if failing_codes else "warn" if manual else "pass"
    return {
        "status": status,
        "path": str(path),
        "citation_review_sha256": _file_sha256(path),
        "summary": summary,
        "canonical_summary": summary,
        "reported_summary": reported_summary,
        "unsupported_count": unsupported,
        "contradicted_count": contradicted,
        "weakly_supported_count": weak,
        "needs_manual_check_count": manual,
        "metadata_only_count": metadata_only,
        "insufficient_evidence_count": insufficient,
        "evidence_missing_count": evidence_missing_count,
        "non_web_supported_count": non_web_supported_count,
        "untrusted_web_provenance_count": untrusted_web_provenance_count,
        "trace_missing_count": trace_missing_count,
        "trace_mismatch_count": trace_mismatch_count,
        "trace_invalid_count": trace_invalid_count,
        "review_trace_path": trace_path,
        "review_trace_sha256": trace_sha,
        "actual_review_trace_sha256": actual_trace_sha,
        "invalid_status_count": invalid_status_count,
        "invalid_status_values": sorted(set(invalid_status_values)),
        "claims_checked": claims_checked,
        "item_count": len(items),
        "current_cited_sentence_count": current_cited_sentence_count,
        "citation_map_sha256": payload.get("citation_map_sha256"),
        "expected_citation_map_sha256": current_citation_map_sha,
        "expected_web_provider_command_digest": expected_web_digest,
        "evidence_mode": payload.get("review_mode") or provenance.get("mode"),
        "semantic_scholar_required": provenance.get("semantic_scholar_required"),
        "web_search_required": provenance.get("web_search_required"),
        "model_review_used": model_review_used,
        "legacy_untrusted": legacy_untrusted,
        "failing_codes": failing_codes,
    }


def ensure_final_citation_review_bound_to_quality_eval(quality_eval_path: str | Path, final_review_path: str | Path) -> dict[str, Any]:
    """Validate that a surfaced final citation review is the gate-of-record artifact."""
    quality_eval = _read_json_if_exists(quality_eval_path)
    source_artifacts = quality_eval.get("source_artifacts") if isinstance(quality_eval, dict) else {}
    expected_sha = source_artifacts.get("citation_review_sha256") if isinstance(source_artifacts, dict) else None
    actual_sha = _file_sha256(final_review_path)
    if expected_sha and str(expected_sha).startswith("sha256:"):
        expected_sha = str(expected_sha).split("sha256:", 1)[1]
    if actual_sha and str(actual_sha).startswith("sha256:"):
        actual_sha = str(actual_sha).split("sha256:", 1)[1]
    if not expected_sha:
        raise ValueError("quality-eval source_artifacts.citation_review_sha256 is missing")
    if not actual_sha:
        raise ValueError(f"final citation review does not exist or is unreadable: {final_review_path}")
    if str(expected_sha) != str(actual_sha):
        raise ValueError(
            "final citation review is not bound to gate-of-record citation review "
            f"(expected sha256:{expected_sha}, actual sha256:{actual_sha})"
        )
    return {
        "status": "pass",
        "quality_eval_path": str(quality_eval_path),
        "final_review_path": str(final_review_path),
        "citation_review_sha256": str(actual_sha),
    }
