from __future__ import annotations

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
