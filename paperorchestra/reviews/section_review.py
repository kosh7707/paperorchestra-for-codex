from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from paperorchestra.core.boundary import control_prose_markers
from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.manuscript.citations import extract_citation_keys


SECTION_RE = re.compile(r"\\section\*?\{([^}]+)\}")


IMPORTANT_SECTIONS = {
    "introduction",
    "related work",
    "method",
    "proposed method",
    "security analysis",
    "implementation and results",
    "experiments",
    "discussion",
    "discussion and limitations",
    "conclusion",
}


CITATION_HEAVY_SECTIONS = {
    "introduction",
    "related work",
    "security analysis",
    "implementation and results",
    "experiments",
    "discussion",
    "discussion and limitations",
    "conclusion",
}


EMPIRICAL_SECTIONS = {
    "implementation and results",
    "experiments",
    "additional implementation and benchmark detail",
}


CLAIM_MAKING_RE = re.compile(r"outperform|state-of-the-art|faster|better|superior|novel|we show|we demonstrate|our results", re.IGNORECASE)


def _plain_words(text: str) -> list[str]:
    text = re.sub(r"\\cite[a-zA-Z*]*\s*(?:\[[^\]]*\]){0,2}\{[^}]+\}", " ", text)
    text = re.sub(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})?", " ", text)
    return re.findall(r"[A-Za-z0-9]+", text)


def _section_bodies(latex: str) -> list[dict[str, Any]]:
    matches = list(SECTION_RE.finditer(latex))
    result = []
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else latex.find(r"\end{document}", start)
        if end == -1:
            end = len(latex)
        title = re.sub(r"\s+", " ", match.group(1).strip())
        result.append({"title": title, "body": latex[start:end]})
    return result


def build_section_review(cwd: str | Path | None) -> dict[str, Any]:
    state = load_session(cwd)
    if not state.artifacts.paper_full_tex:
        raise ValueError("Need paper.full.tex before section review.")
    paper_path = Path(state.artifacts.paper_full_tex)
    latex = paper_path.read_text(encoding="utf-8")
    sections = []
    for section in _section_bodies(latex):
        title = section["title"]
        body = section["body"]
        words = _plain_words(body)
        word_count = len(words)
        citation_count = len(extract_citation_keys(body))
        numeric_count = len(re.findall(r"\b\d+(?:\.\d+)?%?\b", body))
        todo_count = len(re.findall(r"TODO|TBD|\\todo", body, flags=re.IGNORECASE))
        process_residue_markers = control_prose_markers(body)
        claim_like = bool(CLAIM_MAKING_RE.search(body))
        citation_density = round((citation_count * 1000.0) / max(word_count, 1), 2)
        score = 85
        fixes = []
        normalized = title.lower()
        if word_count < 80:
            score -= 12
            fixes.append("Expand this section beyond a placeholder-level stub before relying on the critic score.")
        elif word_count < 120 and normalized in IMPORTANT_SECTIONS:
            score -= 20
            fixes.append("Expand this expected section with substantive, evidence-grounded prose.")
        elif word_count < 220 and normalized in IMPORTANT_SECTIONS:
            score -= 8
            fixes.append("Deepen this important section with more grounded detail and fewer placeholder-level summaries.")
        if citation_count == 0 and (normalized in CITATION_HEAVY_SECTIONS or claim_like):
            score -= 12 if normalized in CITATION_HEAVY_SECTIONS else 8
            fixes.append("Add verified citations that support the section's core claims.")
        elif citation_count > 0 and (normalized in CITATION_HEAVY_SECTIONS or claim_like) and word_count >= 200 and citation_density < 4.0:
            score -= 5
            fixes.append("Increase citation density or narrow unsupported claims in this citation-heavy section.")
        if todo_count:
            score -= 20
            fixes.append("Remove TODO/TBD markers before treating this section as review-ready.")
        if process_residue_markers:
            score -= 25
            fixes.append("Remove process/control prose; section scores are advisory until Tier 0-2 quality gates pass.")
        if normalized in EMPIRICAL_SECTIONS and numeric_count == 0:
            score -= 10
            fixes.append("Include grounded quantitative results or explicitly explain why this is not an empirical section.")
        elif normalized in EMPIRICAL_SECTIONS and numeric_count < 2:
            score -= 4
            fixes.append("Quantitative sections should carry more than one isolated numeric result.")
        score = max(0, min(100, score))
        verdict = "pass" if score >= 70 else "needs_revision" if score >= 45 else "major_revision"
        sections.append(
            {
                "section_title": title,
                "score": score,
                "verdict": verdict,
                "word_count": word_count,
                "citation_count": citation_count,
                "citation_density_per_1000_words": citation_density,
                "numeric_count": numeric_count,
                "todo_count": todo_count,
                "process_residue_markers": process_residue_markers,
                "claim_like": claim_like,
                "required_fixes": fixes,
            }
        )
    overall = round(sum(item["score"] for item in sections) / len(sections), 2) if sections else None
    return {
        "schema_version": "section-review/1",
        "session_id": state.session_id,
        "manuscript_path": str(paper_path),
        "manuscript_sha256": hashlib.sha256(paper_path.read_bytes()).hexdigest(),
        "overall_section_score": overall,
        "score_use": {
            "advisory": True,
            "load_bearing": False,
            "advisory_reason": "Raw section-review scores are local diagnostics; only quality-eval Tier 3 may consume them after Tier 0-2 pass.",
        },
        "sections": sections,
    }


def write_section_review(cwd: str | Path | None, output_path: str | Path | None = None) -> Path:
    state = load_session(cwd)
    path = Path(output_path).resolve() if output_path else artifact_path(cwd, "section_review.json")
    path.write_text(json.dumps(build_section_review(cwd), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    state.artifacts.latest_section_review_json = str(path)
    state.notes.append(f"Section-level critic artifact recorded: {path.name}")
    save_session(cwd, state)
    return path

