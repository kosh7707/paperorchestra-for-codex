from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _iter_review_findings(review: dict[str, Any]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    summary = review.get("summary") if isinstance(review, dict) else {}
    if isinstance(summary, dict):
        for key in ["weaknesses", "top_improvements"]:
            values = summary.get(key)
            if isinstance(values, list):
                for idx, value in enumerate(values, start=1):
                    text = str(value).strip()
                    if text:
                        findings.append({"source": f"summary.{key}", "source_index": str(idx), "text": text})
    questions = review.get("questions") if isinstance(review, dict) else []
    if isinstance(questions, list):
        for idx, question in enumerate(questions, start=1):
            text = str(question).strip()
            if text:
                findings.append({"source": "questions", "source_index": str(idx), "text": text})
    penalties = review.get("penalties") if isinstance(review, dict) else []
    if isinstance(penalties, list):
        for idx, penalty in enumerate(penalties, start=1):
            if isinstance(penalty, dict):
                reason = str(penalty.get("reason") or "").strip()
                if reason:
                    findings.append({"source": "penalties", "source_index": str(idx), "text": reason})
    axis_scores = review.get("axis_scores") if isinstance(review, dict) else {}
    if isinstance(axis_scores, dict):
        for axis, payload in axis_scores.items():
            if isinstance(payload, dict):
                score = payload.get("score")
                justification = str(payload.get("justification") or "").strip()
                if isinstance(score, (int, float)) and score < 60 and justification:
                    findings.append({"source": f"axis_scores.{axis}", "source_index": str(score), "text": justification})
    return findings


def _target_for_item(item: str) -> str:
    lowered = item.lower()
    if any(token in lowered for token in ["proof", "theorem", "bound", "analysis", "guarantee", "security", "privacy"]):
        return "security_analysis"
    if any(token in lowered for token in ["evaluation", "benchmark", "experiment", "measurement", "throughput", "latency", "dataset", "baseline"]):
        return "implementation_results"
    if any(token in lowered for token in ["citation", "bibliography", "prior", "related", "novelty", "literature"]):
        return "introduction_related_work"
    if any(token in lowered for token in ["method", "construction", "interface", "protocol", "algorithm", "architecture", "model"]):
        return "proposed_method"
    return "discussion_limitations"


def _target_for_section_title(title: str) -> str:
    return _target_for_item(title)


def _action_type_for_item(item: str) -> str:
    lowered = item.lower()
    if any(token in lowered for token in ["citation", "bibliography", "prior", "related"]):
        return "curate_and_verify_citations"
    if any(token in lowered for token in ["proof", "theorem", "bound", "analysis", "guarantee"]):
        return "formalize_security_argument"
    if any(token in lowered for token in ["protocol", "interface", "algorithm", "architecture", "model"]):
        return "specify_protocol_interface"
    if any(token in lowered for token in ["evaluation", "benchmark", "experiment", "measurement", "throughput", "latency", "dataset", "baseline"]):
        return "tighten_evaluation_scope"
    if any(token in lowered for token in ["novelty", "comparison", "close prior"]):
        return "strengthen_novelty_positioning"
    return "revise_exposition"


def _priority_for_action(action_type: str, item: str) -> tuple[str, str]:
    lowered = item.lower()
    if action_type in {"curate_and_verify_citations", "formalize_security_argument"}:
        return "P0", "critical"
    if action_type in {"specify_protocol_interface", "strengthen_novelty_positioning"}:
        return "P1", "high"
    if "unsupported" in lowered or "invalid" in lowered:
        return "P1", "high"
    return "P2", "medium"


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


def _section_anchor_for_target(target_area: str) -> str:
    return {
        "introduction_related_work": r"\section{Introduction} or \section{Related Work}",
        "proposed_method": r"\section{Method} or \section{Proposed Method}",
        "security_analysis": r"\section{Security Analysis}",
        "implementation_results": r"\section{Implementation and Results} or \section{Experiments}",
        "discussion_limitations": r"\section{Discussion} or \section{Discussion and Limitations}",
    }.get(target_area, r"\section{...}")


def _patch_hunk_template(target_area: str, action_type: str, review_item: str) -> dict[str, Any]:
    anchor = _section_anchor_for_target(target_area)
    if action_type == "formalize_security_argument":
        snippet = (
            "@@ after theorem/proof/analysis paragraph @@\n"
            "- % informal proof sketch\n"
            "+ \\paragraph{Analysis statement.}\n"
            "+ Define the assumptions, resources, and notation used by the argument.\n"
            "+ State the exact theorem, guarantee, or bound (or explicitly relabel this as a proof sketch).\n"
            "+ Tie the notation back to the method section and stated assumptions.\n"
        )
    elif action_type == "specify_protocol_interface":
        snippet = (
            "@@ near the method/interface subsection @@\n"
            "- % high-level method/interface description\n"
            "+ \\paragraph{Method interface details.}\n"
            "+ Define inputs, outputs, state, configuration, assumptions, and failure conditions.\n"
            "+ State what breaks if the stated assumptions are violated.\n"
        )
    elif action_type == "curate_and_verify_citations":
        snippet = (
            "@@ at the cited claim sentence @@\n"
            "- Existing claim without grounded support.\n"
            "+ Narrow the claim to the measured setting and add verified citation keys from citation_map.json.\n"
            "+ If the claim is comparative, add the exact baseline/standard source that supports the comparison.\n"
        )
    elif action_type == "tighten_evaluation_scope":
        snippet = (
            "@@ in experiments/limitations section @@\n"
            "- Broad deployment claim.\n"
            "+ \\paragraph{Evaluation scope.}\n"
            "+ Clarify the measurement level and environment, then list workload, dataset, platform, and portability limits.\n"
        )
    elif action_type == "strengthen_novelty_positioning":
        snippet = (
            "@@ in related work or method intro @@\n"
            "- Generic novelty statement.\n"
            "+ Add a contrast paragraph naming the closest prior constructions and stating exactly what is new here.\n"
        )
    else:
        snippet = (
            "@@ in the target section @@\n"
            "- Existing vague or incomplete paragraph.\n"
            "+ Replace it with grounded prose that addresses the cited review item directly and cites available evidence.\n"
        )
    return {
        "anchor": anchor,
        "edit_kind": "manual_patch_draft",
        "hunk_template": snippet,
        "review_focus": review_item,
    }


def _section_files(source_paper: Path) -> dict[str, str]:
    text = source_paper.read_text(encoding="utf-8", errors="replace")
    root = source_paper.parent
    mapping: dict[str, str] = {}
    for include in re.findall(r"\\(?:input|include)\{([^}]+)\}", text):
        path = (root / include).with_suffix(".tex") if not include.endswith(".tex") else root / include
        key = path.stem.lower()
        if "intro" in key or "related" in key:
            mapping.setdefault("introduction_related_work", str(path))
        if "method" in key or "proposed" in key:
            mapping.setdefault("proposed_method", str(path))
        if "security" in key:
            mapping.setdefault("security_analysis", str(path))
        if "implementation" in key or "result" in key or "experiment" in key:
            mapping.setdefault("implementation_results", str(path))
        if "discussion" in key or "conclusion" in key:
            mapping.setdefault("discussion_limitations", str(path))
    return mapping


def _section_diagnostics(section_map: dict[str, str]) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {}
    for area, filename in section_map.items():
        path = Path(filename)
        text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        diagnostics[area] = {
            "file": filename,
            "exists": path.exists(),
            "word_count": len(re.findall(r"\w+", text)),
            "citation_count": len(re.findall(r"\\cite\{", text)),
            "todo_markers": len(re.findall(r"TODO|TBD|\\todo", text, flags=re.IGNORECASE)),
        }
    return diagnostics


def _load_optional_json(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    candidate = Path(path)
    if not candidate.exists():
        return {}
    payload = json.loads(candidate.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _iter_section_findings(section_review: dict[str, Any]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    sections = section_review.get("sections") if isinstance(section_review, dict) else []
    if not isinstance(sections, list):
        return findings
    for section in sections:
        if not isinstance(section, dict):
            continue
        title = str(section.get("section_title") or "").strip()
        fixes = section.get("required_fixes") if isinstance(section.get("required_fixes"), list) else []
        for idx, fix in enumerate(fixes, start=1):
            text = str(fix).strip()
            if text:
                findings.append(
                    {
                        "source": f"section_review.{title or 'unknown'}",
                        "source_index": str(idx),
                        "text": f"{title}: {text}" if title else text,
                        "target_area": _target_for_section_title(title),
                    }
                )
    return findings


def _iter_citation_findings(citation_review: dict[str, Any]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    items = citation_review.get("items") if isinstance(citation_review, dict) else []
    if not isinstance(items, list):
        return findings
    for item in items:
        if not isinstance(item, dict):
            continue
        status = str(item.get("support_status") or "").strip()
        risk = str(item.get("risk") or "").strip()
        if status == "supported" and risk == "low":
            continue
        sentence = str(item.get("sentence") or "").strip()
        fix = str(item.get("suggested_fix") or "Check citation support.").strip()
        citation_id = str(item.get("id") or len(findings) + 1)
        text = f"Citation support issue ({status or 'unknown'}, risk={risk or 'unknown'}): {fix} Claim: {sentence}"
        findings.append(
            {
                "source": "citation_support_review",
                "source_index": citation_id,
                "text": text,
                "target_area": _target_for_item(sentence + " " + fix),
                "action_type": "curate_and_verify_citations",
            }
        )
    return findings


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
