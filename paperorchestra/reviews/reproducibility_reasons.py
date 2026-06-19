from __future__ import annotations

from dataclasses import dataclass, field

from paperorchestra.reviews.reproducibility_blockers import (
    append_artifact_blockers,
    append_citation_surface_blocker,
    append_live_seed_blocker,
    append_live_verification_blockers,
    append_mixed_provenance_blocker,
    append_strict_content_blockers,
)
from paperorchestra.reviews.reproducibility_context import ReproducibilityAuditContext
from paperorchestra.reviews.reproducibility_warnings import append_mock_watermark_warning, append_warnings


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
