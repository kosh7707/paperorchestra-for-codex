from __future__ import annotations

from pathlib import Path

from paperorchestra.core.session import artifact_path

CITATION_INTEGRITY_AUDIT_FILENAME = "citation_integrity.audit.json"
CITATION_INTEGRITY_CRITIC_FILENAME = "citation_integrity.critic.json"
CITATION_INTENT_PLAN_FILENAME = "citation_intent_plan.json"
CITATION_SOURCE_MATCH_FILENAME = "citation_source_match.json"


def citation_integrity_audit_path(cwd: str | Path | None) -> Path:
    return artifact_path(cwd, CITATION_INTEGRITY_AUDIT_FILENAME)


def citation_integrity_critic_path(cwd: str | Path | None) -> Path:
    return artifact_path(cwd, CITATION_INTEGRITY_CRITIC_FILENAME)


def citation_intent_plan_path(cwd: str | Path | None) -> Path:
    return artifact_path(cwd, CITATION_INTENT_PLAN_FILENAME)


def citation_source_match_path(cwd: str | Path | None) -> Path:
    return artifact_path(cwd, CITATION_SOURCE_MATCH_FILENAME)
