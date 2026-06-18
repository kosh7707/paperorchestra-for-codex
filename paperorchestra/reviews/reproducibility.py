from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import write_json
from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.reviews.reproducibility_context import collect_reproducibility_audit_context
from paperorchestra.reviews.reproducibility_report import build_reproducibility_report
from paperorchestra.reviews.reproducibility_reasons import build_reproducibility_reasons
from paperorchestra.reviews.reproducibility_artifacts import (
    _has_mock_watermark,
    _lane_completed,
    _note_occurrence_count,
    _prompt_trace_files,
    _read_json_if_exists,
)
from paperorchestra.reviews.reproducibility_citations import (
    _citation_registry_live_provenance,
    _citation_support_review_provenance,
    _citation_surface_health,
    _mock_registry_entry_count,
)
from paperorchestra.reviews.reproducibility_validation import (
    _strict_content_gate_issues,
    _strict_content_gates_enabled,
    _validation_warning_reports,
)
from paperorchestra.runtime.parity import write_lane_manifest_summary


def build_reproducibility_audit(cwd: str | Path | None, *, require_live_verification: bool = False) -> dict[str, Any]:
    context = collect_reproducibility_audit_context(cwd)
    reasons = build_reproducibility_reasons(context, require_live_verification=require_live_verification)
    return build_reproducibility_report(context, reasons, require_live_verification=require_live_verification)


def write_reproducibility_audit(
    cwd: str | Path | None,
    output_path: str | Path | None = None,
    *,
    require_live_verification: bool = False,
) -> tuple[Path, dict[str, Any]]:
    lane_summary_path, lane_summary_payload = write_lane_manifest_summary(cwd)
    payload = build_reproducibility_audit(cwd, require_live_verification=require_live_verification)
    payload["source_artifacts"]["latest_lane_summary_json"] = str(lane_summary_path)
    payload["lane_manifest_summary"] = lane_summary_payload
    path = Path(output_path).resolve() if output_path else artifact_path(cwd, "reproducibility.audit.json")
    write_json(path, payload)
    state = load_session(cwd)
    state.artifacts.latest_lane_summary_json = str(lane_summary_path)
    state.artifacts.latest_reproducibility_json = str(path)
    state.notes.append(f"Reproducibility audit recorded: {path.name}")
    save_session(cwd, state)
    return path, payload


__all__ = [
    "_citation_registry_live_provenance",
    "_citation_support_review_provenance",
    "_citation_surface_health",
    "_has_mock_watermark",
    "_lane_completed",
    "_mock_registry_entry_count",
    "_note_occurrence_count",
    "_prompt_trace_files",
    "_read_json_if_exists",
    "_strict_content_gate_issues",
    "_strict_content_gates_enabled",
    "_validation_warning_reports",
    "build_reproducibility_audit",
    "write_reproducibility_audit",
]
