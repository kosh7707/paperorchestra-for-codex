from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OperatorFeedbackOptions:
    max_supervised_iterations: int = 1
    require_compile: bool = False
    quality_mode: str = "claim_safe"
    max_iterations: int = 10
    require_live_verification: bool = False
    accept_mixed_provenance: bool = False
    runtime_mode: str = "compatibility"
    citation_evidence_mode: str = "web"
    citation_provider_name: str | None = None
    citation_provider_command: str | None = None

    def prepare_kwargs(self) -> dict[str, Any]:
        return {
            "require_compile": self.require_compile,
            "runtime_mode": self.runtime_mode,
            "quality_mode": self.quality_mode,
        }

    def evaluation_kwargs(self) -> dict[str, Any]:
        return {
            "require_compile": self.require_compile,
            "quality_mode": self.quality_mode,
            "max_iterations": self.max_iterations,
            "require_live_verification": self.require_live_verification,
            "accept_mixed_provenance": self.accept_mixed_provenance,
            "runtime_mode": self.runtime_mode,
            "citation_evidence_mode": self.citation_evidence_mode,
            "citation_provider_name": self.citation_provider_name,
            "citation_provider_command": self.citation_provider_command,
        }

    def verification_kwargs(self, validation_name: str, *, require_compile: bool | None = None) -> dict[str, Any]:
        return {
            "require_compile": self.require_compile if require_compile is None else require_compile,
            "quality_mode": self.quality_mode,
            "max_iterations": self.max_iterations,
            "require_live_verification": self.require_live_verification,
            "accept_mixed_provenance": self.accept_mixed_provenance,
            "runtime_mode": self.runtime_mode,
            "citation_evidence_mode": self.citation_evidence_mode,
            "citation_provider_name": self.citation_provider_name,
            "citation_provider_command": self.citation_provider_command,
            "validation_name": validation_name,
        }

    def rollback_kwargs(self) -> dict[str, Any]:
        return {
            "require_compile": self.require_compile,
            "quality_mode": self.quality_mode,
            "max_iterations": self.max_iterations,
            "require_live_verification": self.require_live_verification,
            "accept_mixed_provenance": self.accept_mixed_provenance,
            "runtime_mode": self.runtime_mode,
            "citation_evidence_mode": self.citation_evidence_mode,
            "citation_provider_name": self.citation_provider_name,
            "citation_provider_command": self.citation_provider_command,
        }

    def exception_kwargs(self) -> dict[str, Any]:
        return {
            "quality_mode": self.quality_mode,
            "max_iterations": self.max_iterations,
            "require_live_verification": self.require_live_verification,
            "accept_mixed_provenance": self.accept_mixed_provenance,
            "runtime_mode": self.runtime_mode,
            "citation_evidence_mode": self.citation_evidence_mode,
            "citation_provider_name": self.citation_provider_name,
            "citation_provider_command": self.citation_provider_command,
        }
