from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json
from paperorchestra.core.session import artifact_path, save_session
from paperorchestra.runtime.provider_base import BaseProvider
from paperorchestra.runtime.provider_web_capability import provider_web_search_capability_proof
from paperorchestra.runtime.shell_provider import ShellProvider


def _citation_support_provider_identity(provider: BaseProvider | None) -> dict[str, Any]:
    if provider is None:
        return {"provider_name": None, "provider_command_digest": None, "provider_class": None}
    identity: dict[str, Any] = {
        "provider_name": getattr(provider, "name", None),
        "provider_command_digest": None,
        "provider_class": type(provider).__name__,
    }
    if isinstance(provider, ShellProvider):
        command_digest = hashlib.sha256(json.dumps(provider.argv, ensure_ascii=False).encode("utf-8")).hexdigest()
        identity["provider_command_digest"] = command_digest
        identity["provider_argv"] = list(provider.argv)
        proof = provider_web_search_capability_proof(provider)
        if proof:
            identity.update(proof)
    return identity


def _citation_support_cache_dir(cwd: str | Path | None) -> Path:
    return artifact_path(cwd, "citation-support-cache")


def _citation_support_cache_key(
    state,
    provider: BaseProvider | None,
    evidence_mode: str,
    *,
    semantic_scholar_required: bool = False,
    retrieved_web_evidence_sha256: str | None = None,
) -> str:
    citation_map_sha256 = None
    if state.artifacts.citation_map_json and Path(state.artifacts.citation_map_json).exists():
        citation_map_sha256 = hashlib.sha256(Path(state.artifacts.citation_map_json).read_bytes()).hexdigest()
    payload = {
        "schema_version": "citation-support-cache-key/1",
        "session_id": state.session_id,
        "manuscript_sha256": hashlib.sha256(Path(state.artifacts.paper_full_tex).read_bytes()).hexdigest()
        if state.artifacts.paper_full_tex
        else None,
        "citation_map_sha256": citation_map_sha256,
        "evidence_mode": evidence_mode,
        "semantic_scholar_required": semantic_scholar_required,
        "web_search_required": evidence_mode == "web",
        "model_review_used": evidence_mode in {"model", "web"},
        "retrieved_web_evidence_sha256": retrieved_web_evidence_sha256,
        "provider": _citation_support_provider_identity(provider),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _reuse_cached_citation_review(
    *,
    cwd: str | Path | None,
    state,
    output_path: Path,
    cache_payload_path: Path,
    cache_trace_path: Path | None,
    evidence_mode: str,
    note_suffix: str = "session cache",
) -> Path | None:
    if not cache_payload_path.exists():
        return None
    cached_payload = read_json(cache_payload_path)
    if not isinstance(cached_payload, dict):
        return None
    provenance = cached_payload.get("evidence_provenance")
    if isinstance(provenance, dict):
        trace_path = provenance.get("review_trace_path")
        if isinstance(trace_path, str) and cache_trace_path is not None and cache_trace_path.exists():
            Path(trace_path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(cache_trace_path, trace_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(cached_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    state.notes.append(f"Citation-support critic artifact reused from {note_suffix}: {output_path.name} (mode={evidence_mode})")
    save_session(cwd, state)
    return output_path
