from __future__ import annotations

from pathlib import Path
from typing import Any

from .utils import _file_sha256, _sha256_jsonable


def validate_quality_eval_input(
    quality_eval: dict[str, Any],
    *,
    state: Any,
    reproducibility: dict[str, Any],
    fidelity: dict[str, Any],
    quality_eval_path: Path,
) -> None:
    """Reject a quality-eval snapshot that no longer matches current inputs."""

    current_hash = _file_sha256(state.artifacts.paper_full_tex)
    expected_manuscript_hash = f"sha256:{current_hash}" if current_hash else None
    if quality_eval.get("manuscript_hash") != expected_manuscript_hash:
        raise ValueError(
            "quality-eval input is stale for the current manuscript: "
            f"{quality_eval_path} has {quality_eval.get('manuscript_hash')!r}, expected {expected_manuscript_hash!r}"
        )
    snapshot_hashes = quality_eval.get("audit_snapshot_hashes")
    if not isinstance(snapshot_hashes, dict):
        return

    expected_repro = f"sha256:{_sha256_jsonable(reproducibility)}"
    expected_fidelity = f"sha256:{_sha256_jsonable(fidelity)}"
    if snapshot_hashes.get("reproducibility") != expected_repro:
        raise ValueError(f"quality-eval input is stale for the current reproducibility audit: {quality_eval_path}")
    if snapshot_hashes.get("fidelity") != expected_fidelity:
        raise ValueError(f"quality-eval input is stale for the current fidelity audit: {quality_eval_path}")
