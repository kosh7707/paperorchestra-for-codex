from __future__ import annotations

from paperorchestra.reviews.reproducibility_context import ReproducibilityAuditContext
from paperorchestra.reviews.reproducibility_reason_artifacts import append_artifact_blockers
from paperorchestra.reviews.reproducibility_reason_live import append_live_verification_blockers
from paperorchestra.reviews.reproducibility_reason_model import ReproducibilityReasons
from paperorchestra.reviews.reproducibility_reason_strict import append_strict_content_blockers
from paperorchestra.reviews.reproducibility_reason_warnings import append_mock_watermark_warning, append_warnings


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
