from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import write_json
from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.reviews.reproducibility_artifacts import (
    _has_mock_watermark,
    _lane_completed,
    _note_occurrence_count,
    _prompt_trace_files,
    _read_json_if_exists,
)
from paperorchestra.reviews.reproducibility_citations import (
    _citation_registry_live_provenance,
    _citation_support_review_provenance,
    _citation_surface_health,
    _mock_registry_entry_count,
)
from paperorchestra.reviews.reproducibility_validation import (
    _strict_content_gate_issues,
    _strict_content_gates_enabled,
    _validation_warning_reports,
)
from paperorchestra.runtime.parity import build_lane_manifest_summary, write_lane_manifest_summary


def build_reproducibility_audit(cwd: str | Path | None, *, require_live_verification: bool = False) -> dict[str, Any]:
    state = load_session(cwd)
    lane_summary = build_lane_manifest_summary(cwd)
    session_artifact_dir = Path(state.artifacts.paper_full_tex).resolve().parent if state.artifacts.paper_full_tex else None
    runtime_parity = _read_json_if_exists(state.artifacts.latest_runtime_parity_json)
    if runtime_parity is None and session_artifact_dir is not None:
        runtime_parity = _read_json_if_exists(session_artifact_dir / "runtime-parity.json")
    provider_identity = _read_json_if_exists(state.artifacts.latest_provider_identity_json)
    compile_report = _read_json_if_exists(state.artifacts.latest_compile_report_json)
    prompt_trace_dir = state.artifacts.latest_prompt_trace_dir or (str(session_artifact_dir / "prompts") if session_artifact_dir else None)
    prompt_files = _prompt_trace_files(prompt_trace_dir)
    mock_registry_count = _mock_registry_entry_count(state.artifacts.citation_registry_json)
    citation_live_provenance = _citation_registry_live_provenance(
        state.artifacts.citation_registry_json,
        state.artifacts.paper_full_tex,
    )
    citation_support_review_provenance = _citation_support_review_provenance(cwd, state, session_artifact_dir)
    citation_surface = _citation_surface_health(state)
    validation_warning_reports = _validation_warning_reports(state, session_artifact_dir)
    validation_warning_count = sum(item["warning_count"] for item in validation_warning_reports)
    strict_content_gates = _strict_content_gates_enabled()
    strict_content_gate_issues = _strict_content_gate_issues(state, session_artifact_dir) if strict_content_gates else []
    refinement_compile_preservation_count = _note_occurrence_count(
        state.notes,
        "Compile-failed refinement iteration",
    )
    verification_invoked = state.latest_verify_mode is not None

    block_reasons: list[str] = []
    warn_reasons: list[str] = []

    if not prompt_files:
        block_reasons.append('Prompt trace artifacts are missing; stage prompts cannot be audited after the fact.')
    if state.latest_runtime_mode == 'omx_native' and lane_summary.get('fallback_count', 0) > 0:
        block_reasons.append('OMX-native run used fallback execution in one or more lane manifests.')
    if state.latest_verify_fallback_used == 'mock':
        block_reasons.append('Live verification fell back to mock verification.')
    if state.latest_provider_name == 'mock':
        block_reasons.append('Provider was mock; manuscript output is not a live factual draft.')
    if state.latest_verify_mode == 'mock':
        block_reasons.append('Citation verification used mock mode.')
    cited_mock_count = int(citation_live_provenance.get("cited_mock_count") or 0)
    if cited_mock_count > 0:
        block_reasons.append(f'Cited citation registry contains {cited_mock_count} mock entry/entries.')
    citation_lane_completed = _lane_completed(lane_summary, "literature", "verify")
    if citation_surface["issues"] and (
        verification_invoked
        or state.artifacts.references_bib
        or state.artifacts.paper_full_tex
        or citation_lane_completed
    ):
        prefix = "Citation lane completed but final citation artifacts are incomplete or malformed" if citation_lane_completed else "Final citation artifacts are incomplete or malformed"
        block_reasons.append(
            prefix + ": " + "; ".join(citation_surface["issues"])
        )

    if require_live_verification and not verification_invoked:
        block_reasons.append(
            "Live citation verification was required for this audit, but no live verification stage was invoked."
        )
    if (
        require_live_verification
        and verification_invoked
        and state.latest_verify_mode == "live"
        and citation_live_provenance.get("cited_curated_seed_count", citation_live_provenance.get("seed_only_count", 0)) > 0
    ):
        cited_curated_seed_count = citation_live_provenance.get("cited_curated_seed_count", citation_live_provenance.get("seed_only_count", 0))
        block_reasons.append(
            "Live citation verification was required, but "
            f"{cited_curated_seed_count} cited reference"
            f"{' is' if cited_curated_seed_count == 1 else 's are'} "
            "still seed-only or curated metadata without live verification."
        )
    if (
        require_live_verification
        and verification_invoked
        and state.latest_verify_mode == "live"
        and citation_live_provenance.get("cited_mixed_count", 0) > 0
    ):
        cited_mixed_count = citation_live_provenance.get("cited_mixed_count", 0)
        block_reasons.append(
            "Live citation verification was required, but "
            f"{cited_mixed_count} cited reference"
            f"{' has' if cited_mixed_count == 1 else 's have'} "
            "mixed cited provenance that needs explicit operator acceptance."
        )
    if (
        not require_live_verification
        and not verification_invoked
        and state.latest_discovery_mode in {"manual_bibtex", "manual_seed", "codex_web_seed"}
    ):
        skipped_verification_reason = (
            "Live citation verification was never invoked for this session; citation coverage is curated metadata rather than verified search results."
        )
        warn_reasons.append(skipped_verification_reason)
    if runtime_parity and runtime_parity.get('overall_status') != 'implemented':
        warn_reasons.append(f"Runtime parity status is {runtime_parity.get('overall_status')}, not implemented.")
    if compile_report and not compile_report.get('clean'):
        warn_reasons.append('Latest compile report is not clean.')
    if lane_summary.get('manifest_count', 0) == 0:
        warn_reasons.append('No lane manifests were recorded for the current session.')
    if validation_warning_count > 0:
        warn_reasons.append(f'{validation_warning_count} non-blocking validation warning(s) were recorded for the current session.')
    if strict_content_gates and strict_content_gate_issues:
        codes = ", ".join(sorted({str(issue.get("code")) for issue in strict_content_gate_issues}))
        block_reasons.append(f"Strict content gates blocked warning code(s): {codes}.")
    if refinement_compile_preservation_count > 0:
        warn_reasons.append(
            f'{refinement_compile_preservation_count} refinement iteration(s) preserved the prior compiled manuscript after compile failure.'
        )

    if (state.latest_provider_name == 'mock' or state.latest_verify_mode == 'mock' or state.latest_verify_fallback_used == 'mock') and not _has_mock_watermark(state.artifacts.paper_full_tex):
        warn_reasons.append('Mock or fallback-generated draft is missing the expected manuscript watermark.')

    verdict = 'BLOCK' if block_reasons else 'WARN' if warn_reasons else 'OK'
    source_artifacts = {
        'paper_full_tex': state.artifacts.paper_full_tex,
        'citation_registry_json': state.artifacts.citation_registry_json,
        'citation_map_json': state.artifacts.citation_map_json,
        'references_bib': state.artifacts.references_bib,
        'latest_provider_identity_json': state.artifacts.latest_provider_identity_json,
        'latest_figure_placement_review_json': state.artifacts.latest_figure_placement_review_json,
        'latest_runtime_parity_json': state.artifacts.latest_runtime_parity_json or (str(session_artifact_dir / "runtime-parity.json") if session_artifact_dir else None),
        'latest_compile_report_json': state.artifacts.latest_compile_report_json,
        'latest_prompt_trace_dir': prompt_trace_dir,
        'latest_lane_summary_json': state.artifacts.latest_lane_summary_json,
    }
    return {
        'session_id': state.session_id,
        'verdict': verdict,
        'reasons': block_reasons + warn_reasons,
        'blocking_reasons': block_reasons,
        'warning_reasons': warn_reasons,
        'source_artifacts': source_artifacts,
        'lane_manifest_summary': lane_summary,
        'runtime_parity': runtime_parity,
        'provider_identity': provider_identity,
        'generation_determinism': {
            'byte_identical_generation_claimed': False,
            'auditability_claimed': True,
            'rationale': (
                'PaperOrchestra reproducibility audits track inputs, provider/runtime identity, '
                'prompt traces, validation results, and artifact health; they do not promise '
                'byte-identical LLM text generation.'
            ),
        },
        'latest_provider_name': state.latest_provider_name,
        'latest_runtime_mode': state.latest_runtime_mode,
        'require_live_verification': require_live_verification,
        'verification_invoked': verification_invoked,
        'latest_verify_mode': state.latest_verify_mode,
        'latest_verify_fallback_used': state.latest_verify_fallback_used,
        'prompt_trace_file_count': len(prompt_files),
        'mock_registry_entry_count': mock_registry_count,
        'semantic_scholar_required': bool(citation_support_review_provenance.get("semantic_scholar_required")),
        'citation_support_review_live': bool(citation_support_review_provenance.get("live")),
        'citation_support_review_provenance': citation_support_review_provenance,
        'citation_live_provenance': citation_live_provenance,
        'citation_registry_live_verified_count': citation_live_provenance.get("live_verified_count", 0),
        'citation_registry_entry_count': citation_surface["registry_entry_count"],
        'citation_map_entry_count': citation_surface["citation_map_entry_count"],
        'references_bib_entry_count': citation_surface["references_bib_entry_count"],
        'citation_artifact_issues': citation_surface["issues"],
        'paper_has_mock_watermark': _has_mock_watermark(state.artifacts.paper_full_tex),
        'validation_warning_count': validation_warning_count,
        'validation_warning_reports': validation_warning_reports,
        'strict_content_gates': strict_content_gates,
        'strict_content_gate_issues': strict_content_gate_issues,
        'refinement_compile_preservation_count': refinement_compile_preservation_count,
    }


def write_reproducibility_audit(
    cwd: str | Path | None,
    output_path: str | Path | None = None,
    *,
    require_live_verification: bool = False,
) -> tuple[Path, dict[str, Any]]:
    lane_summary_path, lane_summary_payload = write_lane_manifest_summary(cwd)
    payload = build_reproducibility_audit(cwd, require_live_verification=require_live_verification)
    payload['source_artifacts']['latest_lane_summary_json'] = str(lane_summary_path)
    payload['lane_manifest_summary'] = lane_summary_payload
    path = Path(output_path).resolve() if output_path else artifact_path(cwd, 'reproducibility.audit.json')
    write_json(path, payload)
    state = load_session(cwd)
    state.artifacts.latest_lane_summary_json = str(lane_summary_path)
    state.artifacts.latest_reproducibility_json = str(path)
    state.notes.append(f'Reproducibility audit recorded: {path.name}')
    save_session(cwd, state)
    return path, payload
