from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.loop_engine.ralph.repair_claim_safety_issues import _truncate_issue_text
from paperorchestra.loop_engine.ralph.state import _read_json
from paperorchestra.manuscript.source_obligations import evaluate_source_obligations, source_obligations_path


def _source_obligation_repair_context(cwd: str | Path | None, *, limit: int = 48) -> dict[str, Any]:
    try:
        trust_report = evaluate_source_obligations(cwd)
    except Exception as exc:
        return {"available": False, "reason": "source_obligation_trust_check_error", "error_type": type(exc).__name__}
    trust_failing_codes = (
        {str(code) for code in trust_report.get("failing_codes") or [] if str(code).strip()}
        if isinstance(trust_report, dict)
        else {"source_obligations_missing"}
    )
    untrusted_codes = {
        "source_obligations_missing",
        "source_obligations_stale",
        "source_obligations_legacy_untrusted",
    }
    if trust_failing_codes & untrusted_codes:
        return {
            "available": False,
            "reason": sorted(trust_failing_codes & untrusted_codes)[0],
            "failing_codes": sorted(trust_failing_codes),
        }
    try:
        path = source_obligations_path(cwd)
        payload = _read_json(path)
    except Exception:
        return {"available": False}
    if not isinstance(payload, dict):
        return {"available": False}
    obligations: list[dict[str, Any]] = []
    for obligation in payload.get("obligations") or []:
        if not isinstance(obligation, dict):
            continue
        obligations.append(
            {
                "id": obligation.get("id"),
                "type": obligation.get("type"),
                "expected_manuscript_area": obligation.get("expected_manuscript_area"),
                "required_terms": obligation.get("required_terms") or [],
                "numeric_tokens": obligation.get("numeric_tokens") or [],
                "excerpt_preview": _truncate_issue_text(obligation.get("excerpt_preview"), limit=360),
            }
        )
        if len(obligations) >= limit:
            break
    return {
        "available": True,
        "path": str(path),
        "obligation_count": len(payload.get("obligations") or []),
        "included_obligation_count": len(obligations),
        "obligations": obligations,
    }
