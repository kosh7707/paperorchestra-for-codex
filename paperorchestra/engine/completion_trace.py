from __future__ import annotations

import hashlib
from pathlib import Path
import time
from typing import Any

from paperorchestra.core.io import read_json, write_json, write_text
from paperorchestra.core.models import utc_now_iso
from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.runtime.provider_base import BaseProvider, CompletionRequest

from .completion_identity import _provider_identity_payload, _provider_name


def _record_provider_identity(
    cwd: str | Path | None,
    *,
    provider: BaseProvider | None,
    runtime_mode: str,
    stage: str | None = None,
    request: CompletionRequest | None = None,
) -> list[str]:
    try:
        path = artifact_path(cwd, "provider-identity.json")
        payload = _provider_identity_payload(provider, runtime_mode=runtime_mode, stage=stage, request=request)
        write_json(path, payload)
        state = load_session(cwd)
        state.artifacts.latest_provider_identity_json = str(path)
        state.latest_provider_name = payload.get("provider_name")
        state.latest_runtime_mode = runtime_mode
        save_session(cwd, state)
        return [f"Provider identity recorded: {path.name}"]
    except Exception as exc:  # pragma: no cover - defensive artifact guard
        return [f"Provider identity recording failed: {exc}"]


def _record_prompt_trace(
    cwd: str | Path | None,
    *,
    stage: str,
    request: CompletionRequest,
    runtime_mode: str,
    provider: BaseProvider | None,
) -> list[str]:
    token = f"{stage}.{time.time_ns()}"
    provider_identity = _provider_identity_payload(provider, runtime_mode=runtime_mode, stage=stage, request=request)
    provider_notes = _record_provider_identity(
        cwd,
        provider=provider,
        runtime_mode=runtime_mode,
        stage=stage,
        request=request,
    )
    try:
        system_path = artifact_path(cwd, f"prompts/{token}.system.md")
        user_path = artifact_path(cwd, f"prompts/{token}.user.md")
        combined_path = artifact_path(cwd, f"prompts/{token}.combined.md")
        meta_path = artifact_path(cwd, f"prompts/{token}.meta.json")
        write_text(system_path, request.system_prompt.strip() + "\n")
        write_text(user_path, request.user_prompt.strip() + "\n")
        write_text(combined_path, request.combined_prompt())
        write_json(
            meta_path,
            {
                "stage": stage,
                "runtime_mode": runtime_mode,
                "provider_name": _provider_name(provider),
                "system_chars": len(request.system_prompt),
                "user_chars": len(request.user_prompt),
                "combined_chars": len(request.combined_prompt()),
                "request_controls": request.control_summary(),
                "deterministic_generation_guaranteed": False,
                "provider_identity": {
                    "provider_name": provider_identity.get("provider_name"),
                    "runtime_mode": provider_identity.get("runtime_mode"),
                    "stage": provider_identity.get("stage"),
                    "provider_command_present": provider_identity.get("provider_command_present"),
                    "provider_command_digest": provider_identity.get("provider_command_digest"),
                    "model_command_source": provider_identity.get("model_command_source"),
                    "resolved_backend_class": provider_identity.get("resolved_backend_class"),
                    "generation_determinism": provider_identity.get("generation_determinism"),
                },
            },
        )
        state = load_session(cwd)
        state.artifacts.latest_prompt_trace_dir = str(system_path.parent)
        state.latest_provider_name = _provider_name(provider)
        state.latest_runtime_mode = runtime_mode
        save_session(cwd, state)
        return provider_notes + [
            f"Prompt trace recorded: {system_path.name}",
            f"Prompt trace recorded: {user_path.name}",
            f"Prompt size metadata recorded: {meta_path.name}",
        ]
    except Exception as exc:  # pragma: no cover - defensive trace guard
        return provider_notes + [f"Prompt trace recording failed: {exc}"]


def _file_sha256(path: str | Path | None) -> str | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return None
    return hashlib.sha256(candidate.read_bytes()).hexdigest()


def _latest_prompt_meta_for_stage(cwd: str | Path | None, stage: str) -> Path | None:
    state = load_session(cwd)
    prompt_dir = Path(state.artifacts.latest_prompt_trace_dir) if state.artifacts.latest_prompt_trace_dir else artifact_path(cwd, "prompts/dummy").parent
    if not prompt_dir.exists():
        return None
    candidates: list[Path] = []
    for path in prompt_dir.glob(f"{stage}.*.meta.json"):
        try:
            payload = read_json(path)
        except Exception:
            continue
        if isinstance(payload, dict) and payload.get("stage") == stage:
            candidates.append(path)
    return sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True)[0] if candidates else None


def _review_provenance_payload(
    cwd: str | Path | None,
    *,
    stage: str,
    manuscript_sha256: str,
    lane_manifest_path: str | Path | None = None,
    reviewer_label: str | None = None,
) -> dict[str, Any]:
    meta_path = _latest_prompt_meta_for_stage(cwd, stage)
    provider_identity_path = load_session(cwd).artifacts.latest_provider_identity_json
    meta_payload = read_json(meta_path) if meta_path and meta_path.exists() else {}
    provider_identity = meta_payload.get("provider_identity") if isinstance(meta_payload, dict) else {}
    return {
        "schema_version": "review-provenance/1",
        "stage": stage,
        "manuscript_sha256": manuscript_sha256,
        "reviewer_label": reviewer_label or str(provider_identity.get("provider_command_digest") or provider_identity.get("provider_name") or stage),
        "prompt_trace_meta_path": str(meta_path) if meta_path else None,
        "prompt_trace_meta_sha256": _file_sha256(meta_path),
        "provider_identity_path": provider_identity_path,
        "provider_identity_sha256": _file_sha256(provider_identity_path),
        "provider_name": provider_identity.get("provider_name") if isinstance(provider_identity, dict) else None,
        "provider_command_digest": provider_identity.get("provider_command_digest") if isinstance(provider_identity, dict) else None,
        "runtime_mode": provider_identity.get("runtime_mode") if isinstance(provider_identity, dict) else None,
        "lane_manifest_path": str(lane_manifest_path) if lane_manifest_path else None,
        "lane_manifest_sha256": _file_sha256(lane_manifest_path),
        "recorded_at": utc_now_iso(),
    }
