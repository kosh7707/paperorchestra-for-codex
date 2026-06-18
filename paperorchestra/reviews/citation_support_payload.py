from __future__ import annotations

from typing import Any

from paperorchestra.reviews.citation_items import _summary_from_items
from paperorchestra.runtime.provider_base import BaseProvider


def _citation_support_payload(
    *,
    state: Any,
    manuscript_sha256: str,
    citation_map_sha256: str | None,
    evidence_mode: str,
    provider: BaseProvider | None,
    provider_identity: dict[str, Any],
    retrieved_web_evidence_sha256: str | None,
    retrieved_web_evidence_path: str | None,
    items: list[dict[str, Any]],
    research_notes: Any,
    model_trace: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "schema_version": "citation-support-review/2",
        "session_id": state.session_id,
        "manuscript_sha256": manuscript_sha256,
        "citation_map_sha256": citation_map_sha256,
        "review_mode": evidence_mode,
        "evidence_provenance": _evidence_provenance(
            evidence_mode=evidence_mode,
            provider=provider,
            provider_identity=provider_identity,
            retrieved_web_evidence_sha256=retrieved_web_evidence_sha256,
            retrieved_web_evidence_path=retrieved_web_evidence_path,
        ),
        "claims_checked": len(items),
        "summary": _summary_from_items(items),
        "items": items,
        "research_notes": research_notes,
        "_trace": model_trace,
    }


def _evidence_provenance(
    *,
    evidence_mode: str,
    provider: BaseProvider | None,
    provider_identity: dict[str, Any],
    retrieved_web_evidence_sha256: str | None,
    retrieved_web_evidence_path: str | None,
) -> dict[str, Any]:
    return {
        "mode": evidence_mode,
        "semantic_scholar_required": False,
        "web_search_required": evidence_mode == "web",
        "model_review_used": evidence_mode in {"model", "web"},
        "provider_name": getattr(provider, "name", None) if provider is not None else None,
        "provider_command_digest": provider_identity.get("provider_command_digest"),
        "provider_class": provider_identity.get("provider_class"),
        "provider_argv": provider_identity.get("provider_argv"),
        "provider_capability_proof": provider_identity.get("provider_capability_proof"),
        "provider_contract_path": provider_identity.get("provider_contract_path"),
        "provider_contract_sha256": provider_identity.get("provider_contract_sha256"),
        "provider_wrapper_path": provider_identity.get("provider_wrapper_path"),
        "provider_wrapper_sha256": provider_identity.get("provider_wrapper_sha256"),
        "provider_wrapper_mode": provider_identity.get("provider_wrapper_mode"),
        "provider_wrapper_exec_argv_prefix": provider_identity.get("provider_wrapper_exec_argv_prefix"),
        "web_search_capable": bool(provider_identity.get("web_search_capable")),
        "claim_support_not_metadata_lookup": True,
        "retrieved_web_evidence_sha256": retrieved_web_evidence_sha256,
        "retrieved_web_evidence_path": retrieved_web_evidence_path,
    }
