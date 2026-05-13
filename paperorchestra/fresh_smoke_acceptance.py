from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from .fresh_smoke import (
    FORBIDDEN_SMOKE_VERDICTS,
    build_fresh_smoke_artifact_manifest,
    validate_evidence_completeness,
    validate_fresh_smoke_verdict,
)
from .io_utils import write_json

FRESH_SMOKE_ACCEPTANCE_SCHEMA_VERSION = "fresh-smoke-acceptance-summary/1"
FRESH_SMOKE_ACCEPTANCE_FILENAME = "fresh-smoke-acceptance-summary.json"
SMOKE_MODES = {"synthetic_container", "private_final"}
MAX_OPERATOR_FEEDBACK_CYCLES = 5

_ACCEPTANCE_GATE_IDS = (
    "fresh_container_functional_smoke",
    "private_final_live_smoke_redacted",
    "private_leakage_scan",
    "compile_export",
    "exported_pdf_tex_evidence_bundle",
)
_OUTPUT_SUMMARY_PATH = f"artifacts/{FRESH_SMOKE_ACCEPTANCE_FILENAME}"
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_RAW_COMMAND_RE = re.compile(
    r"(?:^|\b)(?:run\s+)?(?:omx|codex)\s+(?:status|trace|exec|ralph|autoresearch|sparkshell|doctor|state|explore|help|version|setup|update)\b",
    re.IGNORECASE,
)
_UPPER_PRIVATE_MARKERS = ("PRIVATE", "SECRET", "TOKEN")
_FORBIDDEN_MANIFEST_KEYS = {
    "argv",
    "bibtex_key",
    "caption",
    "claim",
    "executable_command",
    "filename",
    "name",
    "path",
    "prompt",
    "raw_text",
    "source",
    "title",
}


def build_fresh_smoke_acceptance_summary(
    evidence_root: str | Path,
    *,
    smoke_mode: str = "synthetic_container",
    material_manifest: str | Path | None = None,
) -> dict[str, Any]:
    """Return a public-safe acceptance summary for an existing fresh-smoke evidence root.

    The function is deliberately diagnostic: it never launches the smoke loop,
    Docker, Codex, OMX, web search, models, compile, or export. It converts
    already-recorded evidence into a redacted status surface.
    """

    if smoke_mode not in SMOKE_MODES:
        raise ValueError(f"Unsupported fresh smoke mode: {smoke_mode}")
    root = Path(evidence_root).expanduser().resolve()
    material_manifest_path = Path(material_manifest).expanduser().resolve() if material_manifest else None

    verdict_payload = _read_json_or_none(root / "readable" / "verdict.json")
    artifact_manifest = _read_json_or_none(root / "artifact-manifest.json")
    material_manifest_payload = _read_json_or_none(material_manifest_path) if material_manifest_path else None

    checks = [
        _evidence_completeness_check(root),
        _fresh_smoke_verdict_check(verdict_payload, root / "readable" / "verdict.json"),
        _material_invariance_check(root),
        _meta_leakage_check(root),
        _operator_feedback_cycles_check(verdict_payload),
        _exported_pdf_tex_check(root, artifact_manifest),
        _material_manifest_safety_check(
            smoke_mode=smoke_mode,
            material_manifest_path=material_manifest_path,
            material_manifest_payload=material_manifest_payload,
        ),
    ]
    overall = _overall_status(check["status"] for check in checks)
    material_count = _safe_material_count(material_manifest_payload) if _check_by_id(checks, "material_manifest_safety")["status"] == "pass" else 0
    summary: dict[str, Any] = {
        "schema_version": FRESH_SMOKE_ACCEPTANCE_SCHEMA_VERSION,
        "smoke_mode": smoke_mode,
        "overall_status": overall,
        "evidence_root_label": _redacted_label("evidence-root", str(root)),
        "material_manifest_label": _redacted_label("material-manifest", str(material_manifest_path)) if material_manifest_path else None,
        "checks": checks,
        "redacted_counts": {
            "operator_feedback_cycles": _safe_int((verdict_payload or {}).get("operator_feedback_cycles"), default=0),
            "artifact_file_count": _artifact_file_count(artifact_manifest),
            "material_file_count": material_count,
        },
        "private_safe_summary": True,
    }
    summary["acceptance_evidence"] = fresh_smoke_acceptance_evidence(summary)
    return summary


def fresh_smoke_acceptance_evidence(summary: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Map a redacted fresh-smoke summary to acceptance-ledger evidence entries."""

    if summary.get("schema_version") != FRESH_SMOKE_ACCEPTANCE_SCHEMA_VERSION:
        raise ValueError("Invalid fresh smoke acceptance summary schema_version.")
    smoke_mode = str(summary.get("smoke_mode") or "")
    overall = _status(summary.get("overall_status"))
    check_statuses = {
        str(check.get("id")): _status(check.get("status"))
        for check in summary.get("checks", [])
        if isinstance(check, Mapping)
    }

    exported = check_statuses.get("exported_pdf_tex_evidence", "blocked")
    leakage = check_statuses.get("meta_leakage_scan", "blocked")
    manifest = check_statuses.get("material_manifest_safety", "blocked")
    leakage_gate_status = _combine_statuses(leakage, manifest) if smoke_mode == "private_final" else leakage

    if smoke_mode == "synthetic_container":
        container_status = _gate_from_overall(overall)
        private_status = "blocked"
        private_note = "synthetic_only_not_final_evidence"
    elif smoke_mode == "private_final":
        container_status = "blocked"
        private_status = _gate_from_overall(overall) if manifest == "pass" else manifest
        private_note = "redacted_final_smoke_mode"
    else:
        container_status = "fail"
        private_status = "fail"
        private_note = "unknown_smoke_mode"

    return {
        "fresh_container_functional_smoke": _gate(
            container_status,
            "fresh_smoke/summary",
            "container smoke summary",
            note="container_mode" if smoke_mode == "synthetic_container" else "not_container_proof",
        ),
        "private_final_live_smoke_redacted": _gate(
            private_status,
            "fresh_smoke/summary",
            "redacted final smoke summary",
            note=private_note,
        ),
        "private_leakage_scan": _gate(
            leakage_gate_status,
            "fresh_smoke/leakage",
            "redacted leakage scan summary",
            note="synthetic_only" if smoke_mode == "synthetic_container" else "redacted_final_mode",
        ),
        "compile_export": _gate(
            exported,
            "fresh_smoke/export",
            "compiled/exported PDF and TeX accounted for",
            note="export_manifest_checked",
        ),
        "exported_pdf_tex_evidence_bundle": _gate(
            exported,
            "fresh_smoke/export",
            "PDF TeX and evidence bundle accounted for",
            note="export_bundle_checked",
        ),
    }


def write_fresh_smoke_acceptance_summary(
    evidence_root: str | Path,
    *,
    output_path: str | Path | None = None,
    smoke_mode: str = "synthetic_container",
    material_manifest: str | Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    summary = build_fresh_smoke_acceptance_summary(
        evidence_root,
        smoke_mode=smoke_mode,
        material_manifest=material_manifest,
    )
    root = Path(evidence_root).expanduser().resolve()
    path = Path(output_path).expanduser().resolve() if output_path else root / "artifacts" / FRESH_SMOKE_ACCEPTANCE_FILENAME
    summary["output_label"] = _redacted_label("fresh-smoke-output", str(path))
    write_json(path, summary)
    return path, summary


def _evidence_completeness_check(root: Path) -> dict[str, Any]:
    try:
        result = validate_evidence_completeness(root)
    except Exception:
        return _check("evidence_completeness", "fail", "evidence_completeness_validation_error")
    if result.get("status") == "pass":
        return _check("evidence_completeness", "pass", "evidence_completeness_pass")
    if result.get("inconsistent"):
        return _check("evidence_completeness", "fail", _first_code(result, "evidence_completeness_inconsistent"))
    return _check("evidence_completeness", "blocked", _first_code(result, "required_evidence_missing"))


def _fresh_smoke_verdict_check(payload: dict[str, Any] | None, path: Path) -> dict[str, Any]:
    if payload is None:
        return _check("fresh_smoke_verdict", "blocked", "fresh_smoke_verdict_missing")
    verdict = payload.get("smoke_verdict")
    if verdict in FORBIDDEN_SMOKE_VERDICTS:
        return _check("fresh_smoke_verdict", "fail", "fresh_smoke_verdict_forbidden_state")
    result = validate_fresh_smoke_verdict(payload)
    if result.get("status") == "pass":
        return _check("fresh_smoke_verdict", "pass", "fresh_smoke_verdict_schema_pass")
    return _check("fresh_smoke_verdict", "fail", _first_code(result, "fresh_smoke_verdict_schema_invalid"))


def _material_invariance_check(root: Path) -> dict[str, Any]:
    payload = _read_json_or_none(root / "artifacts" / "material-invariance.json")
    if payload is None:
        return _check("material_invariance", "blocked", "material_invariance_missing")
    status = str(payload.get("status") or "").lower()
    if status == "pass":
        return _check("material_invariance", "pass", "material_invariance_pass")
    if status in {"fail", "failed"}:
        return _check("material_invariance", "fail", "material_invariance_failed")
    return _check("material_invariance", "blocked", "material_invariance_not_final")


def _meta_leakage_check(root: Path) -> dict[str, Any]:
    payload = _read_json_or_none(root / "artifacts" / "meta-leakage-scan.json")
    if payload is None:
        return _check("meta_leakage_scan", "blocked", "meta_leakage_scan_missing")
    status = str(payload.get("status") or "").lower()
    match_count = _match_count(payload)
    if status in {"pass", "ok"} and match_count == 0:
        return _check("meta_leakage_scan", "pass", "meta_leakage_scan_pass")
    if status in {"fail", "failed", "blocked"} or match_count > 0:
        return _check("meta_leakage_scan", "fail", "meta_leakage_scan_detected")
    return _check("meta_leakage_scan", "blocked", "meta_leakage_scan_not_final")


def _operator_feedback_cycles_check(payload: dict[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return _check("operator_feedback_cycles", "blocked", "operator_feedback_cycles_unknown")
    cycles = payload.get("operator_feedback_cycles")
    attempted = payload.get("operator_feedback_cycles_attempted", cycles)
    if not isinstance(cycles, int) or not isinstance(attempted, int):
        return _check("operator_feedback_cycles", "blocked", "operator_feedback_cycle_counter_missing")
    if attempted < 0 or cycles < 0:
        return _check("operator_feedback_cycles", "fail", "operator_feedback_cycle_counter_negative")
    if attempted > MAX_OPERATOR_FEEDBACK_CYCLES or cycles > MAX_OPERATOR_FEEDBACK_CYCLES:
        return _check("operator_feedback_cycles", "fail", "operator_feedback_cycle_cap_exceeded")
    split_present = any(
        key in payload
        for key in [
            "operator_feedback_cycles_promoted",
            "operator_feedback_cycles_rolled_back",
            "operator_feedback_cycles_failed",
        ]
    )
    if split_present:
        split_values = [
            payload.get("operator_feedback_cycles_promoted"),
            payload.get("operator_feedback_cycles_rolled_back"),
            payload.get("operator_feedback_cycles_failed"),
        ]
        if not all(isinstance(value, int) for value in split_values):
            return _check("operator_feedback_cycles", "fail", "operator_feedback_cycle_split_invalid")
        if sum(split_values) != attempted:
            return _check("operator_feedback_cycles", "fail", "operator_feedback_cycle_split_mismatch")
    if payload.get("qa_loop_terminal_verdict") == "human_needed" and cycles < 1:
        return _check("operator_feedback_cycles", "fail", "human_needed_cycle_evidence_missing")
    return _check("operator_feedback_cycles", "pass", "operator_feedback_cycle_counters_pass")


def _exported_pdf_tex_check(root: Path, manifest: dict[str, Any] | None) -> dict[str, Any]:
    if manifest is None:
        return _check("exported_pdf_tex_evidence", "blocked", "artifact_manifest_missing")
    if manifest.get("missing_referenced_artifacts"):
        return _check("exported_pdf_tex_evidence", "fail", "artifact_manifest_missing_references")
    files = manifest.get("files")
    if not isinstance(files, list):
        return _check("exported_pdf_tex_evidence", "blocked", "artifact_manifest_files_missing")
    rels = [str(item.get("path") or "") for item in files if isinstance(item, Mapping)]
    if any(_looks_unsafe_public_string(rel) or rel.startswith("/") or ".." in Path(rel).parts for rel in rels):
        return _check("exported_pdf_tex_evidence", "fail", "artifact_manifest_public_path_unsafe")
    has_pdf = any(rel.endswith(".pdf") for rel in rels)
    has_tex = any(rel.endswith(".tex") for rel in rels)
    has_evidence = any("evidence" in rel and rel.endswith((".json", ".jsonl", ".md")) for rel in rels)
    if has_pdf and has_tex and has_evidence:
        return _check("exported_pdf_tex_evidence", "pass", "exported_pdf_tex_evidence_present")
    return _check("exported_pdf_tex_evidence", "blocked", "exported_pdf_tex_evidence_missing")


def _material_manifest_safety_check(
    *,
    smoke_mode: str,
    material_manifest_path: Path | None,
    material_manifest_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    if material_manifest_path is None:
        if smoke_mode == "private_final":
            return _check("material_manifest_safety", "blocked", "material_manifest_required_for_redacted_final")
        return _check("material_manifest_safety", "pass", "material_manifest_not_required_for_synthetic")
    if material_manifest_payload is None:
        return _check("material_manifest_safety", "fail", "material_manifest_unreadable")
    unsafe = _material_manifest_unsafe_reasons(material_manifest_payload)
    if unsafe:
        return _check("material_manifest_safety", "fail", "material_manifest_public_payload_unsafe")
    if smoke_mode == "private_final" and _safe_material_count(material_manifest_payload) <= 0:
        return _check("material_manifest_safety", "blocked", "material_manifest_material_count_missing")
    return _check("material_manifest_safety", "pass", "material_manifest_public_payload_safe")


def _read_json_or_none(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _check(check_id: str, status: str, reason: str) -> dict[str, str]:
    return {"id": check_id, "status": _status(status), "reason": _safe_reason(reason)}


def _status(value: Any) -> str:
    text = str(value or "blocked")
    return text if text in {"pass", "blocked", "fail"} else "blocked"


def _safe_reason(reason: str) -> str:
    text = re.sub(r"[^a-z0-9_:-]+", "_", str(reason).lower()).strip("_")
    if not text or _looks_unsafe_public_string(text):
        return "redacted_reason"
    return text


def _overall_status(statuses: Any) -> str:
    normalized = [_status(status) for status in statuses]
    if "fail" in normalized:
        return "fail"
    if "blocked" in normalized:
        return "blocked"
    return "pass"


def _gate_from_overall(status: str) -> str:
    return {"pass": "pass", "fail": "fail"}.get(status, "blocked")


def _combine_statuses(*statuses: str) -> str:
    normalized = [_status(status) for status in statuses]
    if "fail" in normalized:
        return "fail"
    if "blocked" in normalized:
        return "blocked"
    return "pass"


def _gate(status: str, kind: str, summary: str, *, note: str) -> dict[str, Any]:
    safe_status = _status(status)
    return {
        "status": safe_status,
        "evidence_refs": [
            {
                "kind": kind,
                "summary": summary,
                "path": _OUTPUT_SUMMARY_PATH,
            }
        ],
        "notes": [_safe_reason(note)],
    }


def _first_code(result: Mapping[str, Any], fallback: str) -> str:
    codes = result.get("failing_codes")
    if isinstance(codes, list):
        for code in codes:
            text = _safe_reason(str(code))
            if text:
                return text
    return _safe_reason(fallback)


def _redacted_label(kind: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()
    return f"redacted-{kind}:{digest[:12]}"


def _match_count(payload: Mapping[str, Any]) -> int:
    for key in ("match_count", "matches_count", "count"):
        value = payload.get(key)
        if isinstance(value, int):
            return value
    matches = payload.get("matches")
    return len(matches) if isinstance(matches, list) else 0


def _artifact_file_count(manifest: Mapping[str, Any] | None) -> int:
    files = manifest.get("files") if isinstance(manifest, Mapping) else None
    return len(files) if isinstance(files, list) else 0


def _safe_material_count(manifest: Mapping[str, Any] | None) -> int:
    if not isinstance(manifest, Mapping):
        return 0
    count = manifest.get("material_count")
    if isinstance(count, int):
        return max(count, 0)
    count = manifest.get("file_count")
    if isinstance(count, int):
        return max(count, 0)
    materials = manifest.get("materials")
    if isinstance(materials, list):
        return len(materials)
    files = manifest.get("files")
    return len(files) if isinstance(files, list) else 0


def _safe_int(value: Any, *, default: int = 0) -> int:
    return value if isinstance(value, int) else default


def _check_by_id(checks: list[dict[str, Any]], check_id: str) -> dict[str, Any]:
    for check in checks:
        if check.get("id") == check_id:
            return check
    return {"status": "blocked", "reason": "missing_check"}


def _material_manifest_unsafe_reasons(payload: Any) -> list[str]:
    reasons: set[str] = set()

    def visit(node: Any, *, key: str | None = None) -> None:
        key_text = str(key or "")
        if key_text in _FORBIDDEN_MANIFEST_KEYS:
            reasons.add("forbidden_manifest_key")
            return
        if isinstance(node, Mapping):
            for child_key, child_value in node.items():
                visit(child_value, key=str(child_key))
            return
        if isinstance(node, list):
            for item in node:
                visit(item)
            return
        if not isinstance(node, str):
            return
        if key_text == "label" and node.startswith("redacted-"):
            return
        if key_text == "schema_version":
            return
        if key_text == "sha256" and _SHA256_RE.fullmatch(node):
            return
        if _looks_unsafe_public_string(node):
            reasons.add("unsafe_manifest_string")

    visit(payload)
    return sorted(reasons)


def _looks_unsafe_public_string(value: str) -> bool:
    if any(marker in value for marker in _UPPER_PRIVATE_MARKERS):
        return True
    if value.startswith("/") or re.search(r"\s/[A-Za-z0-9_.-]", value):
        return True
    if _RAW_COMMAND_RE.search(value):
        return True
    return False
