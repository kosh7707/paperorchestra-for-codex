from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.orchestra.evidence_files import (
    DEFAULT_EVIDENCE_DIR,
    relative_to_bundle,
    remove_stale_evidence_files,
    resolve_bundle_dir,
    slugify_evidence_kind,
    write_json_with_sha,
)
from paperorchestra.orchestra.evidence_redaction import REDACTED, redact_public
from paperorchestra.orchestra.state import OrchestraState

SCHEMA_VERSION = "orchestrator-evidence-bundle/1"
EVIDENCE_REF_SCHEMA_VERSION = "orchestrator-evidence-ref/1"


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
    bundle_dir = resolve_bundle_dir(root, output_dir)
    evidence_dir = bundle_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    remove_stale_evidence_files(evidence_dir)

    state_path = bundle_dir / "orchestra-state.json"
    state_sha256 = write_json_with_sha(state_path, redact_public(state.to_public_dict(), root=root))

    evidence_entries = _write_evidence_refs(state.evidence_refs, evidence_dir=evidence_dir, bundle_dir=bundle_dir, root=root)
    manifest_path = bundle_dir / "manifest.json"
    manifest_payload = {
        "schema_version": SCHEMA_VERSION,
        "manifest_path": "manifest.json",
        "state_path": relative_to_bundle(state_path, bundle_dir),
        "state_sha256": state_sha256,
        "state_bytes": state_path.stat().st_size,
        "evidence_count": len(evidence_entries),
        "evidence": evidence_entries,
        "private_safe_summary": True,
    }
    manifest_sha256 = write_json_with_sha(manifest_path, manifest_payload)

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


def _write_evidence_refs(
    evidence_refs: list[Any],
    *,
    evidence_dir: Path,
    bundle_dir: Path,
    root: Path,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for index, evidence_ref in enumerate(evidence_refs):
        kind, payload = _split_evidence_ref(evidence_ref)
        path = evidence_dir / f"{index:02d}-{slugify_evidence_kind(kind)}.json"
        evidence_sha256 = write_json_with_sha(
            path,
            {
                "schema_version": EVIDENCE_REF_SCHEMA_VERSION,
                "index": index,
                "kind": kind,
                "payload": redact_public(payload, root=root),
                "private_safe_summary": True,
            },
        )
        entries.append(
            {
                "index": index,
                "kind": kind,
                "path": relative_to_bundle(path, bundle_dir),
                "sha256": evidence_sha256,
                "bytes": path.stat().st_size,
            }
        )
    return entries


def _split_evidence_ref(evidence_ref: Any) -> tuple[str, Any]:
    if not isinstance(evidence_ref, dict):
        return "evidence", evidence_ref
    return str(evidence_ref.get("kind") or "evidence"), evidence_ref.get("payload")


__all__ = [
    "DEFAULT_EVIDENCE_DIR",
    "EVIDENCE_REF_SCHEMA_VERSION",
    "REDACTED",
    "SCHEMA_VERSION",
    "write_orchestrator_evidence_bundle",
]
