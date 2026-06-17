from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _citation_progress_path(output_path: Path) -> Path:
    return output_path.with_name(f"{output_path.stem}.progress.jsonl")


def _emit_citation_progress(progress_stream: Any, message: str) -> None:
    if progress_stream is None:
        return
    progress_stream.write(f"[paperorchestra] citation-support {message}\n")
    progress_stream.flush()


def _citation_progress_cite_label(item: dict[str, Any]) -> str:
    keys = [str(key) for key in (item.get("citation_keys") or []) if str(key).strip()]
    return ",".join(keys) if keys else str(item.get("id") or "unknown")


def _stable_json_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _citation_progress_claim_input_sha256(item: dict[str, Any]) -> str:
    return _stable_json_sha256(
        {
            "id": item.get("id"),
            "sentence": item.get("sentence"),
            "citation_keys": item.get("citation_keys") or [],
            "citation_entries": item.get("citation_entries") or [],
            "claim_type": item.get("claim_type"),
            "heuristic_support_status": item.get("heuristic_support_status"),
            "heuristic_risk": item.get("heuristic_risk"),
        }
    )


def _citation_progress_provider_identity_sha256(provider_identity: dict[str, Any]) -> str:
    return _stable_json_sha256(provider_identity)


def _load_citation_progress_checkpoint(
    checkpoint_path: Path | None,
    *,
    manuscript_sha256: str,
    citation_map_sha256: str | None,
    evidence_mode: str,
    provider_identity: dict[str, Any],
    retrieved_web_evidence_sha256: str | None,
    items: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    if checkpoint_path is None or not checkpoint_path.exists():
        return {}
    provider_identity_sha256 = _citation_progress_provider_identity_sha256(provider_identity)
    claim_hashes = {str(item.get("id")): _citation_progress_claim_input_sha256(item) for item in items}
    reusable: dict[str, dict[str, Any]] = {}
    for line in checkpoint_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        claim_id = str(row.get("claim_id") or "")
        if (
            row.get("schema_version") != "citation-support-progress-checkpoint/1"
            or row.get("event") != "checked"
            or row.get("manuscript_sha256") != manuscript_sha256
            or row.get("citation_map_sha256") != citation_map_sha256
            or row.get("evidence_mode") != evidence_mode
            or row.get("provider_identity_sha256") != provider_identity_sha256
            or row.get("retrieved_web_evidence_sha256") != retrieved_web_evidence_sha256
            or row.get("claim_input_sha256") != claim_hashes.get(claim_id)
            or not isinstance(row.get("item"), dict)
        ):
            continue
        reusable[claim_id] = row["item"]
    return reusable


def _append_citation_progress_checkpoint(checkpoint_path: Path | None, record: dict[str, Any]) -> None:
    if checkpoint_path is None:
        return
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    with checkpoint_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")


