from __future__ import annotations

from paperorchestra.reviews.reproducibility_context import ReproducibilityAuditContext


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
