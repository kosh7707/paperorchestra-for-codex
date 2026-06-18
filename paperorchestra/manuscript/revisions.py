from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paperorchestra.manuscript.revision_action_taxonomy import (
    _action_type_for_item,
    _priority_for_action,
    _target_for_item,
)
from paperorchestra.manuscript.revision_action_templates import _patch_hunk_template
from paperorchestra.manuscript.revision_issue_findings import _iter_citation_findings, _iter_section_findings
from paperorchestra.manuscript.revision_review_findings import _iter_review_findings
from paperorchestra.manuscript.revision_source_files import _load_optional_json, _section_diagnostics, _section_files


def _done_criteria(action_type: str) -> list[str]:
    if action_type == "curate_and_verify_citations":
        return [
            "Add or import real BibTeX/metadata for the cited prior work.",
            "Ensure all claims in the revised section cite verified or curated entries.",
            "Regenerate citation_map.json/references.bib and run review/eval artifacts again.",
        ]
    if action_type == "formalize_security_argument":
        return [
            "State theorem, model, and assumptions explicitly.",
            "Provide a concrete bound, guarantee, or clearly label a proof sketch.",
            "Check notation consistency against the method section.",
        ]
    if action_type == "specify_protocol_interface":
        return [
            "Define all method inputs, outputs, state variables, and failure conditions.",
            "State what breaks if the deployment violates the stated assumptions.",
        ]
    if action_type == "tighten_evaluation_scope":
        return [
            "Separate primitive-level measurements from end-to-end deployment claims.",
            "List environment, message-size, associated-data, and platform limitations.",
        ]
    return ["Revise the target section with grounded text and rerun review."]


def build_revision_suggestions(
    source_paper: str | Path,
    review_json: str | Path,
    *,
    section_review_json: str | Path | None = None,
    citation_review_json: str | Path | None = None,
) -> dict[str, Any]:
    source_path = Path(source_paper).resolve()
    review_path = Path(review_json).resolve()
    review = json.loads(review_path.read_text(encoding="utf-8"))
    section_map = _section_files(source_path)
    findings = _iter_review_findings(review)
    findings.extend(_iter_section_findings(_load_optional_json(section_review_json)))
    findings.extend(_iter_citation_findings(_load_optional_json(citation_review_json)))
    actions = []
    for idx, finding in enumerate(findings, start=1):
        item = finding["text"]
        target = finding.get("target_area") or _target_for_item(item)
        action_type = finding.get("action_type") or _action_type_for_item(item)
        priority, severity = _priority_for_action(action_type, item)
        actions.append(
            {
                "id": f"rev-{idx:02d}",
                "priority": priority,
                "severity": severity,
                "action_type": action_type,
                "target_area": target,
                "target_file": section_map.get(target, str(source_path)),
                "review_trace": {"source": finding["source"], "source_index": finding["source_index"]},
                "review_item": item,
                "suggested_action": "Add or revise manuscript text to address this review item with grounded evidence and citations.",
                "suggested_patch_hunk": _patch_hunk_template(target, action_type, item),
                "done_criteria": _done_criteria(action_type),
                "status": "proposed",
            }
        )
    severity_counts: dict[str, int] = {}
    for action in actions:
        severity_counts[action["severity"]] = severity_counts.get(action["severity"], 0) + 1
    grouped: dict[str, list[str]] = {}
    for action in actions:
        grouped.setdefault(action["target_area"], []).append(action["id"])
    return {
        "source_paper": str(source_path),
        "review_json": str(review_path),
        "section_review_json": str(Path(section_review_json).resolve()) if section_review_json else None,
        "citation_review_json": str(Path(citation_review_json).resolve()) if citation_review_json else None,
        "overall_score": review.get("overall_score"),
        "action_count": len(actions),
        "severity_counts": severity_counts,
        "actions_by_target": grouped,
        "section_diagnostics": _section_diagnostics(section_map),
        "actions": actions,
        "notes": ["Suggestions are patch-planning guidance; apply manually or in a later editing lane."],
    }


def write_revision_suggestions(
    source_paper: str | Path,
    review_json: str | Path,
    output_path: str | Path,
    *,
    section_review_json: str | Path | None = None,
    citation_review_json: str | Path | None = None,
) -> Path:
    payload = build_revision_suggestions(
        source_paper,
        review_json,
        section_review_json=section_review_json,
        citation_review_json=citation_review_json,
    )
    path = Path(output_path).resolve()
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
