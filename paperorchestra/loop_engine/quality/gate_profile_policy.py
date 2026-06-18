from __future__ import annotations

from typing import Any

QUALITY_GATE_PROFILES = {"auto", "mock", "ralph", "claim_safe"}


def normalize_profile(profile: str | None, quality_eval: dict[str, Any]) -> str:
    requested = (profile or "auto").strip().lower().replace("-", "_")
    if requested not in QUALITY_GATE_PROFILES:
        raise ValueError(f"Unknown quality-gate profile {profile!r}; expected one of: {', '.join(sorted(QUALITY_GATE_PROFILES))}")
    if requested != "auto":
        return requested
    mode = str(quality_eval.get("mode") or "").strip().lower()
    provenance = quality_eval.get("provenance_trust") if isinstance(quality_eval.get("provenance_trust"), dict) else {}
    if provenance.get("level") == "mock":
        return "mock"
    if mode == "claim_safe":
        return "claim_safe"
    return "ralph"


def status_for_profile(raw_status: str, *, profile: str, axis: str) -> tuple[str, bool]:
    if raw_status in {"pass", "never_automated"}:
        return ("pass" if raw_status == "pass" else "human_owned", False)
    if raw_status.startswith("skipped"):
        return ("block" if profile == "claim_safe" else "warn", profile == "claim_safe")
    if raw_status == "fail":
        if profile == "mock" and axis in {"story_logic", "citation_claim_safety", "reviewer_acceptability", "reproducibility"}:
            return "warn", False
        return "block", True
    if raw_status == "warn":
        return ("block", True) if profile == "claim_safe" else ("warn", False)
    return ("warn", False) if profile == "mock" else ("block", True)
