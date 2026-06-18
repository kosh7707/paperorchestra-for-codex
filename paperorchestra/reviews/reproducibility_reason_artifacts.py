from __future__ import annotations

from paperorchestra.reviews.reproducibility_artifacts import _lane_completed
from paperorchestra.reviews.reproducibility_context import ReproducibilityAuditContext


def append_artifact_blockers(blocking: list[str], context: ReproducibilityAuditContext) -> None:
    state = context.state
    if not context.prompt_files:
        blocking.append("Prompt trace artifacts are missing; stage prompts cannot be audited after the fact.")
    if state.latest_runtime_mode == "omx_native" and context.lane_summary.get("fallback_count", 0) > 0:
        blocking.append("OMX-native run used fallback execution in one or more lane manifests.")
    if state.latest_verify_fallback_used == "mock":
        blocking.append("Live verification fell back to mock verification.")
    if state.latest_provider_name == "mock":
        blocking.append("Provider was mock; manuscript output is not a live factual draft.")
    if state.latest_verify_mode == "mock":
        blocking.append("Citation verification used mock mode.")
    cited_mock_count = int(context.citation_live_provenance.get("cited_mock_count") or 0)
    if cited_mock_count > 0:
        blocking.append(f"Cited citation registry contains {cited_mock_count} mock entry/entries.")
    append_citation_surface_blocker(blocking, context)


def append_citation_surface_blocker(blocking: list[str], context: ReproducibilityAuditContext) -> None:
    state = context.state
    citation_lane_completed = _lane_completed(context.lane_summary, "literature", "verify")
    if not context.citation_surface["issues"]:
        return
    if not (
        context.verification_invoked
        or state.artifacts.references_bib
        or state.artifacts.paper_full_tex
        or citation_lane_completed
    ):
        return
    prefix = (
        "Citation lane completed but final citation artifacts are incomplete or malformed"
        if citation_lane_completed
        else "Final citation artifacts are incomplete or malformed"
    )
    blocking.append(prefix + ": " + "; ".join(context.citation_surface["issues"]))
