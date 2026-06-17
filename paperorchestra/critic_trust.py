from __future__ import annotations

import os
from typing import Any

from .providers import ProviderError, ShellProvider, provider_web_search_capability_proof


def _command_has_web_capability(command: str | None) -> bool:
    if not command:
        return False
    try:
        provider = ShellProvider(command=command)
    except ProviderError:
        return False
    return provider_web_search_capability_proof(provider) is not None


def build_critic_trust_card(
    *,
    provider_name: str | None,
    citation_evidence_mode: str,
    provider_command: str | None = None,
    claim_safe: bool = False,
) -> dict[str, Any]:
    provider = (provider_name or "missing").strip().lower()
    citation_mode = (citation_evidence_mode or "heuristic").strip().lower()
    command = provider_command or os.environ.get("PAPERO_MODEL_CMD")
    blockers: list[str] = []

    if provider == "mock":
        trust_tier = "mock_smoke"
        blockers.append("provider=mock")
    elif provider != "shell":
        trust_tier = "local_diagnostic"
        blockers.append(f"provider={provider or 'missing'}")
    elif not command:
        trust_tier = "local_diagnostic"
        blockers.append("provider_command_missing")
    elif citation_mode == "web":
        if _command_has_web_capability(command):
            trust_tier = "claim_safe_live" if claim_safe else "web_citation_review"
        else:
            trust_tier = "live_model_review"
            blockers.append("web_search_not_configured")
    else:
        trust_tier = "live_model_review"

    web_search_configured = _command_has_web_capability(command)
    if citation_mode == "web" and provider == "shell" and web_search_configured:
        citation_trust_tier = "web_citation_review"
    elif citation_mode == "model" and provider == "shell" and command:
        citation_trust_tier = "live_model_review"
    else:
        citation_trust_tier = "heuristic_citation"
        if "citation_evidence_mode=" + citation_mode not in blockers:
            blockers.append(f"citation_evidence_mode={citation_mode}")

    live_critic_claim_allowed = trust_tier in {"web_citation_review", "claim_safe_live"} and not blockers
    return {
        "schema_version": "critic-trust/1",
        "trust_tier": trust_tier,
        "citation_trust_tier": citation_trust_tier,
        "provider_name": provider,
        "provider_command_configured": bool(command),
        "web_search_configured": web_search_configured,
        "citation_evidence_mode": citation_mode,
        "claim_safe": claim_safe,
        "live_critic_claim_allowed": live_critic_claim_allowed,
        "blockers": sorted(dict.fromkeys(blockers)),
        "labels": {
            "local_diagnostic": trust_tier == "local_diagnostic",
            "mock_smoke": trust_tier == "mock_smoke",
            "heuristic_citation": citation_trust_tier == "heuristic_citation",
            "live_model_review": trust_tier == "live_model_review",
            "web_citation_review": citation_trust_tier == "web_citation_review",
            "claim_safe_live": trust_tier == "claim_safe_live",
        },
    }


def require_live_critic_trust(card: dict[str, Any]) -> None:
    if not card.get("live_critic_claim_allowed"):
        raise ValueError(
            "live critic requested but trust preflight is not live/web-capable: "
            f"trust_tier={card.get('trust_tier')}, blockers={card.get('blockers')}"
        )
