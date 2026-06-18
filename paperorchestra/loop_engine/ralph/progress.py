from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.session import load_session
from paperorchestra.loop_engine.ralph.io_files import _read_json


def _failing_codes(quality_eval: dict[str, Any]) -> list[str]:
    result: list[str] = []
    tiers = quality_eval.get("tiers") if isinstance(quality_eval, dict) else {}
    if not isinstance(tiers, dict):
        return result
    for key, tier in tiers.items():
        if not str(key).startswith("tier_") or not isinstance(tier, dict):
            continue
        if tier.get("status") not in {"fail", "warn"}:
            continue
        result.extend(str(code) for code in tier.get("failing_codes") or [])
    return sorted(dict.fromkeys(result))


def _citation_summary(cwd: str | Path | None) -> dict[str, int]:
    state = load_session(cwd)
    if not state.artifacts.paper_full_tex:
        return {}
    path = Path(state.artifacts.paper_full_tex).resolve().parent / "citation_support_review.json"
    payload = _read_json(path)
    summary = payload.get("summary") if isinstance(payload, dict) else {}
    return dict(summary) if isinstance(summary, dict) else {}


def _citation_issue_count(summary: dict[str, int]) -> int:
    return sum(int(value or 0) for key, value in summary.items() if key != "supported")


def _manuscript_hash(payload: dict[str, Any]) -> str | None:
    value = payload.get("manuscript_hash") if isinstance(payload, dict) else None
    if value:
        return str(value)
    return None


def quality_eval_status(quality_eval: dict[str, Any]) -> dict[str, str]:
    tiers = quality_eval.get("tiers") if isinstance(quality_eval, dict) else {}
    result: dict[str, str] = {}
    if isinstance(tiers, dict):
        for key, tier in tiers.items():
            if isinstance(tier, dict):
                result[str(key)] = str(tier.get("status"))
    return result


def compute_progress_delta(before_eval: dict[str, Any], after_eval: dict[str, Any], before_summary: dict[str, int], after_summary: dict[str, int]) -> dict[str, Any]:
    before_codes = set(_failing_codes(before_eval))
    after_codes = set(_failing_codes(after_eval))
    before_issues = _citation_issue_count(before_summary)
    after_issues = _citation_issue_count(after_summary)
    before_hash = _manuscript_hash(before_eval)
    after_hash = _manuscript_hash(after_eval)
    manuscript_identity_known = bool(before_hash and after_hash)
    same_manuscript = manuscript_identity_known and before_hash == after_hash
    progress_signal = bool((before_codes - after_codes) or after_issues < before_issues)
    forward_progress = progress_signal
    if not manuscript_identity_known:
        forward_progress = False
    elif after_codes and same_manuscript:
        forward_progress = False
    return {
        "resolved_codes": sorted(before_codes - after_codes),
        "new_codes": sorted(after_codes - before_codes),
        "before_failing_codes": sorted(before_codes),
        "after_failing_codes": sorted(after_codes),
        "before_manuscript_hash": before_hash,
        "after_manuscript_hash": after_hash,
        "same_manuscript_as_previous": same_manuscript if manuscript_identity_known else None,
        "manuscript_identity_known": manuscript_identity_known,
        "before_citation_issue_count": before_issues,
        "after_citation_issue_count": after_issues,
        "citation_issue_delta": after_issues - before_issues,
        "forward_progress": forward_progress,
    }
