from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from paperorchestra.core.io import write_json
from paperorchestra.engine.research_verification_stage import build_bib
from paperorchestra.reviews.citation_integrity_audit import write_citation_integrity_audit
from paperorchestra.reviews.citation_integrity_gate import write_citation_integrity_critic
from paperorchestra.reviews.citation_rendered_references import write_rendered_reference_audit
from .state import _next_execution_path


def _refresh_citation_integrity_for_current_manuscript(
    cwd: str | Path | None,
    *,
    quality_mode: str,
) -> dict[str, Any]:
    """Regenerate citation-integrity artifacts after manuscript/citation-review changes.

    `write_quality_eval()` intentionally treats stale citation-integrity artifacts
    as hard claim-safe failures.  Candidate verification therefore must refresh
    the rendered-reference audit, source-match/intent/integrity audit, and the
    deterministic citation critic after staging a candidate manuscript and after
    restoring the original manuscript.
    """

    rendered_path, rendered_payload = write_rendered_reference_audit(cwd, quality_mode=quality_mode)
    audit_path, audit_payload = write_citation_integrity_audit(cwd, quality_mode=quality_mode)
    critic_path, critic_payload = write_citation_integrity_critic(cwd, quality_mode=quality_mode)
    return {
        "rendered_reference_audit": {
            "path": str(rendered_path),
            "status": rendered_payload.get("status") if isinstance(rendered_payload, dict) else None,
            "manuscript_sha256": rendered_payload.get("manuscript_sha256") if isinstance(rendered_payload, dict) else None,
            "failing_codes": rendered_payload.get("failing_codes") if isinstance(rendered_payload, dict) else None,
        },
        "citation_integrity_audit": {
            "path": str(audit_path),
            "status": audit_payload.get("status") if isinstance(audit_payload, dict) else None,
            "manuscript_sha256": audit_payload.get("manuscript_sha256") if isinstance(audit_payload, dict) else None,
            "failing_codes": audit_payload.get("failing_codes") if isinstance(audit_payload, dict) else None,
        },
        "citation_integrity_critic": {
            "path": str(critic_path),
            "status": critic_payload.get("status") if isinstance(critic_payload, dict) else None,
            "manuscript_sha256": critic_payload.get("manuscript_sha256") if isinstance(critic_payload, dict) else None,
            "failing_codes": critic_payload.get("failing_codes") if isinstance(critic_payload, dict) else None,
        },
    }


def _try_rebuild_bib_for_citation_quality(cwd: str | Path | None) -> dict[str, Any]:
    """Best-effort bibliography regeneration before weak-reference re-audit.

    Weak rendered-reference identity can be caused by stale `references.bib`
    after the registry has better metadata.  Rebuilding is safe and reversible
    because `build_bib()` derives from the session registry; if the registry is
    absent or incomplete, keep the QA-loop action machine-owned and record the
    failure instead of routing to `unsupported_handler`.
    """

    try:
        path = build_bib(cwd)
    except Exception as exc:
        return {"ok": False, "error_type": exc.__class__.__name__, "error": str(exc)}
    return {"ok": True, "path": str(path)}


def _write_execution_artifact(cwd: str | Path | None, payload: dict[str, Any]) -> Path:
    reserved = payload.pop("_reserved_execution_path", None)
    path = Path(reserved) if reserved else _next_execution_path(cwd)[1]
    approval = payload.get("candidate_approval")
    if isinstance(approval, dict) and approval.get("source_execution_sha256") == "pending_until_execution_write":
        payload_for_hash = json.loads(json.dumps(payload, sort_keys=True))
        payload_for_hash.get("candidate_approval", {}).pop("source_execution_sha256", None)
        approval["source_execution_sha256"] = "sha256:" + hashlib.sha256(
            json.dumps(payload_for_hash, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest()
    write_json(path, payload)
    return path

