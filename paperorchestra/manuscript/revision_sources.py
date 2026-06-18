from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from paperorchestra.manuscript.revision_actions import _target_for_item, _target_for_section_title


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
