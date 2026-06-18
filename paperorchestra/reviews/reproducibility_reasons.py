from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from paperorchestra.reviews.reproducibility_artifacts import _lane_completed
from paperorchestra.reviews.reproducibility_context import ReproducibilityAuditContext


@dataclass(frozen=True)
class ReproducibilityReasons:
    blocking: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        if self.blocking:
            return "BLOCK"
        if self.warnings:
            return "WARN"
        return "OK"

    @property
    def combined(self) -> list[str]:
        return [*self.blocking, *self.warnings]


def build_reproducibility_reasons(
    context: ReproducibilityAuditContext,
    *,
    require_live_verification: bool,
) -> ReproducibilityReasons:
    blocking: list[str] = []
    warnings: list[str] = []
    append_artifact_blockers(blocking, context)
    append_live_verification_blockers(blocking, context, require_live_verification=require_live_verification)
    append_warnings(warnings, context, require_live_verification=require_live_verification)
    append_strict_content_blockers(blocking, context)
    append_mock_watermark_warning(warnings, context)
    return ReproducibilityReasons(blocking=blocking, warnings=warnings)


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


def append_live_verification_blockers(
    blocking: list[str],
    context: ReproducibilityAuditContext,
    *,
    require_live_verification: bool,
) -> None:
    state = context.state
    if require_live_verification and not context.verification_invoked:
        blocking.append("Live citation verification was required for this audit, but no live verification stage was invoked.")
    if not (require_live_verification and context.verification_invoked and state.latest_verify_mode == "live"):
        return
    append_live_seed_blocker(blocking, context.citation_live_provenance)
    append_mixed_provenance_blocker(blocking, context.citation_live_provenance)


def append_live_seed_blocker(blocking: list[str], citation_live_provenance: dict[str, Any]) -> None:
    cited_curated_seed_count = citation_live_provenance.get(
        "cited_curated_seed_count",
        citation_live_provenance.get("seed_only_count", 0),
    )
    if cited_curated_seed_count <= 0:
        return
    blocking.append(
        "Live citation verification was required, but "
        f"{cited_curated_seed_count} cited reference"
        f"{' is' if cited_curated_seed_count == 1 else 's are'} "
        "still seed-only or curated metadata without live verification."
    )


def append_mixed_provenance_blocker(blocking: list[str], citation_live_provenance: dict[str, Any]) -> None:
    cited_mixed_count = citation_live_provenance.get("cited_mixed_count", 0)
    if cited_mixed_count <= 0:
        return
    blocking.append(
        "Live citation verification was required, but "
        f"{cited_mixed_count} cited reference"
        f"{' has' if cited_mixed_count == 1 else 's have'} "
        "mixed cited provenance that needs explicit operator acceptance."
    )


def append_warnings(
    warnings: list[str],
    context: ReproducibilityAuditContext,
    *,
    require_live_verification: bool,
) -> None:
    state = context.state
    if (
        not require_live_verification
        and not context.verification_invoked
        and state.latest_discovery_mode in {"manual_bibtex", "manual_seed", "codex_web_seed"}
    ):
        warnings.append(
            "Live citation verification was never invoked for this session; citation coverage is curated metadata rather than verified search results."
        )
    if context.runtime_parity and context.runtime_parity.get("overall_status") != "implemented":
        warnings.append(f"Runtime parity status is {context.runtime_parity.get('overall_status')}, not implemented.")
    if context.compile_report and not context.compile_report.get("clean"):
        warnings.append("Latest compile report is not clean.")
    if context.lane_summary.get("manifest_count", 0) == 0:
        warnings.append("No lane manifests were recorded for the current session.")
    if context.validation_warning_count > 0:
        warnings.append(
            f"{context.validation_warning_count} non-blocking validation warning(s) were recorded for the current session."
        )
    if context.refinement_compile_preservation_count > 0:
        warnings.append(
            f"{context.refinement_compile_preservation_count} refinement iteration(s) preserved the prior compiled manuscript after compile failure."
        )


def append_mock_watermark_warning(warnings: list[str], context: ReproducibilityAuditContext) -> None:
    state = context.state
    mock_or_fallback = (
        state.latest_provider_name == "mock"
        or state.latest_verify_mode == "mock"
        or state.latest_verify_fallback_used == "mock"
    )
    if mock_or_fallback and not context.paper_has_mock_watermark:
        warnings.append("Mock or fallback-generated draft is missing the expected manuscript watermark.")


def append_strict_content_blockers(blocking: list[str], context: ReproducibilityAuditContext) -> None:
    if not (context.strict_content_gates and context.strict_content_gate_issues):
        return
    codes = ", ".join(sorted({str(issue.get("code")) for issue in context.strict_content_gate_issues}))
    blocking.append(f"Strict content gates blocked warning code(s): {codes}.")


_append_artifact_blockers = append_artifact_blockers
_append_citation_surface_blocker = append_citation_surface_blocker
_append_live_seed_blocker = append_live_seed_blocker
_append_live_verification_blockers = append_live_verification_blockers
_append_mixed_provenance_blocker = append_mixed_provenance_blocker
_append_mock_watermark_warning = append_mock_watermark_warning
_append_strict_content_blockers = append_strict_content_blockers
_append_warnings = append_warnings

__all__ = [
    "ReproducibilityReasons",
    "build_reproducibility_reasons",
    "_append_artifact_blockers",
    "_append_citation_surface_blocker",
    "_append_live_seed_blocker",
    "_append_live_verification_blockers",
    "_append_mixed_provenance_blocker",
    "_append_mock_watermark_warning",
    "_append_strict_content_blockers",
    "_append_warnings",
]
