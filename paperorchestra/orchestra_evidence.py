from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

from .orchestra_state import OrchestraState

SCHEMA_VERSION = "orchestrator-evidence-bundle/1"
EVIDENCE_REF_SCHEMA_VERSION = "orchestrator-evidence-ref/1"
DEFAULT_EVIDENCE_DIR = Path(".paper-orchestra") / "orchestrator-evidence"
REDACTED = "<redacted>"
PRIVATE_PREFIX = "private_"
PRIVATE_KEYS = {"raw_text", "prompt", "argv", "executable_command"}
PUBLIC_SAFE_KEYS = {"private_safe", "private_safe_summary"}


def write_orchestrator_evidence_bundle(
    cwd: str | Path,
    state: OrchestraState,
    *,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Persist public-safe orchestrator state/evidence refs under ``cwd``.

    The bundle is intentionally an audit surface only. Writing it must not
    change readiness, mark an OMX/model action as executed, or leak private raw
    material from nested evidence refs.
    """

    root = Path(cwd).resolve()
    bundle_dir = _resolve_bundle_dir(root, output_dir)
    evidence_dir = bundle_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    _remove_stale_evidence_files(evidence_dir)

    state_path = bundle_dir / "orchestra-state.json"
    state_sha256 = _write_json(state_path, _redact_public(state.to_public_dict(), root=root))

    evidence_entries: list[dict[str, Any]] = []
    for index, evidence_ref in enumerate(state.evidence_refs):
        if not isinstance(evidence_ref, dict):
            kind = "evidence"
            payload: Any = evidence_ref
        else:
            kind = str(evidence_ref.get("kind") or "evidence")
            payload = evidence_ref.get("payload")
        filename = f"{index:02d}-{_slugify(kind)}.json"
        path = evidence_dir / filename
        evidence_sha256 = _write_json(
            path,
            {
                "schema_version": EVIDENCE_REF_SCHEMA_VERSION,
                "index": index,
                "kind": kind,
                "payload": _redact_public(payload, root=root),
                "private_safe_summary": True,
            },
        )
        evidence_entries.append(
            {
                "index": index,
                "kind": kind,
                "path": _relative_to_bundle(path, bundle_dir),
                "sha256": evidence_sha256,
                "bytes": path.stat().st_size,
            }
        )

    manifest_path = bundle_dir / "manifest.json"
    manifest_payload = {
        "schema_version": SCHEMA_VERSION,
        "manifest_path": "manifest.json",
        "state_path": _relative_to_bundle(state_path, bundle_dir),
        "state_sha256": state_sha256,
        "state_bytes": state_path.stat().st_size,
        "evidence_count": len(evidence_entries),
        "evidence": evidence_entries,
        "private_safe_summary": True,
    }
    manifest_sha256 = _write_json(manifest_path, manifest_payload)

    return {
        "schema_version": SCHEMA_VERSION,
        "output_dir": str(bundle_dir),
        "manifest_path": str(manifest_path),
        "manifest_sha256": manifest_sha256,
        "state_path": str(state_path),
        "state_sha256": state_sha256,
        "evidence_count": len(evidence_entries),
        "private_safe_summary": True,
    }


def _resolve_bundle_dir(root: Path, output_dir: str | Path | None) -> Path:
    if output_dir is None:
        candidate = root / DEFAULT_EVIDENCE_DIR
    else:
        candidate = Path(output_dir).expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
    resolved = candidate.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError("Evidence output must stay under the current workspace.")
    return resolved


def _remove_stale_evidence_files(evidence_dir: Path) -> None:
    for path in evidence_dir.glob("*.json"):
        path.unlink()
    for path in evidence_dir.iterdir():
        if path.is_dir():
            shutil.rmtree(path)


def _redact_public(value: Any, *, root: Path) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if (key_text.startswith(PRIVATE_PREFIX) and key_text not in PUBLIC_SAFE_KEYS) or key_text in PRIVATE_KEYS:
                redacted[key_text] = REDACTED
            else:
                redacted[key_text] = _redact_public(item, root=root)
        return redacted
    if isinstance(value, list):
        return [_redact_public(item, root=root) for item in value]
    if isinstance(value, tuple):
        return [_redact_public(item, root=root) for item in value]
    if isinstance(value, str):
        return _sanitize_string(value, root=root)
    return value


def _sanitize_string(value: str, *, root: Path) -> str:
    root_text = str(root)
    if value == root_text:
        return "."
    if value.startswith(root_text + "/"):
        return Path(value).relative_to(root).as_posix()
    if root_text in value:
        return value.replace(root_text, "<workspace>")
    return value


def _write_json(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return _sha256_file(path)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-").lower()
    return slug or "evidence"


def _relative_to_bundle(path: Path, bundle_dir: Path) -> str:
    return path.relative_to(bundle_dir).as_posix()
