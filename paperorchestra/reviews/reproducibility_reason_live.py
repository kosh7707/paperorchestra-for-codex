from __future__ import annotations

from typing import Any

from paperorchestra.reviews.reproducibility_context import ReproducibilityAuditContext


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
