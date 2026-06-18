from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.session import runtime_root
from paperorchestra.loop_engine.quality.utils import _file_sha256, _read_json_if_exists, _sha256_jsonable


def _mixed_provenance_acceptance_path(cwd: str | Path | None) -> Path:
    return runtime_root(cwd) / "mixed-provenance-acceptance.json"


def _mixed_provenance_acceptance(cwd: str | Path | None, quality_eval: dict[str, Any]) -> dict[str, Any]:
    path = _mixed_provenance_acceptance_path(cwd)
    payload = _read_json_if_exists(path)
    provenance = quality_eval.get("provenance_trust") if isinstance(quality_eval.get("provenance_trust"), dict) else {}
    failures: list[str] = []
    if not isinstance(payload, dict):
        return {"status": "missing", "path": str(path), "failing_codes": ["mixed_provenance_acceptance_missing"]}
    if payload.get("schema_version") != "mixed-provenance-acceptance/1":
        failures.append("mixed_provenance_acceptance_legacy_untrusted")
    if payload.get("source") == "codex_operator" or payload.get("not_independent_human_review") is True:
        failures.append("mixed_provenance_acceptance_operator_not_independent")
    if payload.get("manuscript_sha256") != quality_eval.get("manuscript_hash"):
        failures.append("mixed_provenance_acceptance_stale")
    expected_provenance_sha = f"sha256:{_sha256_jsonable({k: v for k, v in provenance.items() if k != 'mixed_acceptance'})}"
    if payload.get("provenance_trust_sha256") != expected_provenance_sha:
        failures.append("mixed_provenance_acceptance_stale")
    if not str(payload.get("operator_label") or "").strip() or not str(payload.get("accepted_at") or "").strip():
        failures.append("mixed_provenance_acceptance_incomplete")
    if len(str(payload.get("rationale") or "").strip()) < 10:
        failures.append("mixed_provenance_acceptance_incomplete")
    return {
        "status": "fail" if failures else "pass",
        "path": str(path),
        "sha256": _file_sha256(path),
        "failing_codes": sorted(dict.fromkeys(failures)),
    }
