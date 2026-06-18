from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _write_review_trace(output_path: Path, payload: dict[str, Any]) -> None:
    trace_payload = payload.pop("_trace", None)
    if not isinstance(trace_payload, dict):
        return
    trace_payload = _trace_payload_with_review_identity(trace_payload, payload)
    trace_path = output_path.with_name(output_path.stem + ".trace.json")
    trace_text = json.dumps(trace_payload, indent=2, ensure_ascii=False) + "\n"
    trace_path.write_text(trace_text, encoding="utf-8")
    trace_sha = hashlib.sha256(trace_text.encode("utf-8")).hexdigest()
    payload.setdefault("evidence_provenance", {})["review_trace_path"] = str(trace_path)
    payload.setdefault("evidence_provenance", {})["review_trace_sha256"] = trace_sha


def _trace_payload_with_review_identity(trace_payload: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    provenance = payload.get("evidence_provenance") or {}
    enriched = dict(trace_payload)
    enriched.update(
        {
            "manuscript_sha256": payload.get("manuscript_sha256"),
            "citation_map_sha256": payload.get("citation_map_sha256"),
            "review_mode": payload.get("review_mode"),
            "provider_command_digest": provenance.get("provider_command_digest"),
            "provider_capability_proof": provenance.get("provider_capability_proof"),
            "provider_contract_path": provenance.get("provider_contract_path"),
            "provider_contract_sha256": provenance.get("provider_contract_sha256"),
            "provider_wrapper_path": provenance.get("provider_wrapper_path"),
            "provider_wrapper_sha256": provenance.get("provider_wrapper_sha256"),
            "provider_wrapper_mode": provenance.get("provider_wrapper_mode"),
            "web_search_capable": provenance.get("web_search_capable"),
            "review_items_sha256": hashlib.sha256(
                json.dumps(payload.get("items") or [], sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest(),
        }
    )
    return enriched
