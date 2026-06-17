from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha256(path: str | Path | None) -> str | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return None
    return _sha256_bytes(candidate.read_bytes())


def _sha256_digest(value: str | None) -> str | None:
    if not value:
        return None
    return value.split("sha256:", 1)[1] if value.startswith("sha256:") else value


def _sha256_prefixed(value: str | None) -> str | None:
    digest = _sha256_digest(value)
    return f"sha256:{digest}" if digest else None


def _canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _canonical_sha256(payload: Any) -> str:
    return _sha256_bytes(_canonical_json_bytes(payload))


def _packet_sha256(packet: dict[str, Any]) -> str:
    normalized = dict(packet)
    normalized.pop("packet_sha256", None)
    return _canonical_sha256(normalized)


def _artifact_record(role: str, path: str | Path | None, *, required: bool = False) -> dict[str, Any] | None:
    if not path:
        if required:
            raise ContractError(f"required operator review artifact is missing: {role}")
        return None
    candidate = Path(path).resolve()
    if not candidate.exists() or not candidate.is_file():
        if required:
            raise ContractError(f"required operator review artifact is missing: {role}: {candidate}")
        return None
    return {
        "role": role,
        "path": str(candidate),
        "sha256": _file_sha256(candidate),
        "size_bytes": candidate.stat().st_size,
    }


def _safe_packet_artifact_name(role: str, digest: str, source: Path) -> str:
    safe_role = re.sub(r"[^A-Za-z0-9_.-]+", "-", role).strip("-") or "artifact"
    suffix = "".join(source.suffixes[-2:]) if source.suffixes else ".artifact"
    return f"{safe_role}.{digest[:16]}{suffix}"


def _snapshot_operator_packet_artifacts(packet_path: Path, artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Freeze packet-bound artifacts next to the packet before hashing it."""

    snapshot_dir = packet_path.with_suffix(".artifacts")
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    frozen: list[dict[str, Any]] = []
    for artifact in artifacts:
        source = Path(str(artifact.get("path") or "")).resolve()
        digest = str(artifact.get("sha256") or _file_sha256(source) or "")
        if not digest or not source.exists() or not source.is_file():
            frozen.append(dict(artifact))
            continue
        dest = snapshot_dir / _safe_packet_artifact_name(str(artifact.get("role") or "artifact"), digest, source)
        if not dest.exists() or _file_sha256(dest) != digest:
            shutil.copy2(source, dest)
        record = dict(artifact)
        record["original_path"] = str(source)
        record["path"] = str(dest.resolve())
        record["snapshot_path"] = str(dest.resolve())
        record["sha256"] = digest
        record["size_bytes"] = dest.stat().st_size
        frozen.append(record)
    return frozen
