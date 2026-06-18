from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json
from paperorchestra.core.session import artifact_path, load_session
from paperorchestra.reviews import source_support_cases
from paperorchestra.reviews.source_support_evidence import _inspect_source_case, _resolve_source_evidence
from paperorchestra.reviews.source_support_resolution import _apply_human_resolution
from paperorchestra.reviews.source_support_retrieval import _source_locators


def build_source_backed_citation_cases(
    cwd: str | Path | None,
    *,
    resolve_evidence: bool = True,
) -> list[dict[str, Any]]:
    """Build lean per-citation cases from the current manuscript.

    This is the source-backed v3 surface.  Cases are derived from the actual
    manuscript, not from the planning artifact: one case per citation key, with
    paragraph context plus a sentence anchor and target claim span.
    """

    state = load_session(cwd)
    if not state.artifacts.paper_full_tex:
        raise ValueError("Need paper.full.tex before citation support review.")
    latex = Path(state.artifacts.paper_full_tex).read_text(encoding="utf-8")
    citation_map = read_json(state.artifacts.citation_map_json) if state.artifacts.citation_map_json else {}
    cases = source_support_cases.build_source_backed_citation_cases_from_latex(latex, citation_map)
    if resolve_evidence:
        for case in cases:
            case["_cwd"] = cwd
            ignore_existing_source = _apply_human_resolution(cwd, case, citation_map)
            if not case.get("_skip_source_resolution"):
                evidence = _resolve_source_evidence(cwd, case, ignore_existing_source=ignore_existing_source)
                case["evidence"] = evidence
                verdict, message_field, message = _inspect_source_case(case, evidence)
                case["verdict"] = verdict
                case[message_field] = message
    return cases


def _source_review_summary(cases: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"pass": 0, "weak": 0, "fail": 0, "human_needed": 0}
    for case in cases:
        verdict = str(case.get("verdict") or "human_needed")
        if verdict not in summary:
            verdict = "human_needed"
        summary[verdict] += 1
    return summary


def _short_markdown_value(value: Any, *, limit: int = 240) -> str:
    text = source_support_cases._collapse_ws(str(value or ""))
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def render_citation_support_human_needed_markdown(review: dict[str, Any]) -> str | None:
    if review.get("schema") != "citation-support-review/3":
        return None
    cases = [
        case
        for case in review.get("cases") or []
        if isinstance(case, dict) and str(case.get("verdict") or "").strip().lower() == "human_needed"
    ]
    if not cases:
        return None
    lines = [
        "# Citation source follow-up",
        "",
        "Add the missing source artifact, then rerun `paperorchestra critique --citation-evidence-mode source`.",
        "",
    ]
    for case in cases:
        source = case.get("source") if isinstance(case.get("source"), dict) else {}
        evidence = case.get("evidence") if isinstance(case.get("evidence"), dict) else {}
        title = _short_markdown_value(source.get("title") or case.get("key"), limit=160)
        url = _short_markdown_value(source.get("url"), limit=180)
        reason = _short_markdown_value(evidence.get("why") or evidence.get("status") or "missing", limit=120)
        lines.extend(
            [
                f"## {case.get('id', '?')} — `{case.get('key', '?')}`",
                f"- Location: {_short_markdown_value(case.get('loc'), limit=120)}",
                f"- Paragraph: {_short_markdown_value(case.get('paragraph'), limit=360)}",
                f"- Anchor: {_short_markdown_value(case.get('anchor'), limit=300)}",
                f"- Target: {_short_markdown_value(case.get('target'), limit=300)}",
                f"- Source: {title}" + (f" ({url})" if url else ""),
                f"- Problem: {reason}",
                f"- Ask: {_short_markdown_value(case.get('ask'), limit=300)}",
                f"- Resolution file: `artifacts/references/{case.get('id', '?')}/human-resolution.json`",
                "- Resolution examples: `provide_source_url`, `replace_citation`, `weaken_claim`, or `remove_claim`.",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def build_source_backed_citation_support_review(cwd: str | Path | None, *, mode: str = "source") -> dict[str, Any]:
    cases = build_source_backed_citation_cases(cwd, resolve_evidence=True)
    public_cases: list[dict[str, Any]] = []
    for case in cases:
        case = dict(case)
        case.pop("_cwd", None)
        case.pop("_skip_source_resolution", None)
        public_cases.append(case)
    return {
        "schema": "citation-support-review/3",
        "mode": mode,
        "summary": _source_review_summary(public_cases),
        "cases": public_cases,
    }


def build_citation_source_retrieval_debug(cwd: str | Path | None) -> dict[str, Any]:
    cases = build_source_backed_citation_cases(cwd, resolve_evidence=False)
    items: list[dict[str, Any]] = []
    summary: dict[str, int] = {}
    for case in cases:
        evidence = _resolve_source_evidence(cwd, case)
        status = str(evidence.get("status") or "missing")
        summary[status] = summary.get(status, 0) + 1
        source = case.get("source") if isinstance(case.get("source"), dict) else {}
        items.append(
            {
                "id": case.get("id"),
                "key": case.get("key"),
                "source": source,
                "candidate_locators": _source_locators(source),
                "evidence": evidence,
            }
        )
    return {
        "schema": "citation-source-retrieval-debug/1",
        "summary": dict(sorted(summary.items())),
        "items": items,
    }


def write_citation_source_retrieval_debug(cwd: str | Path | None, output_path: str | Path | None = None) -> Path:
    path = Path(output_path).resolve() if output_path else artifact_path(cwd, "citation_source_retrieval_debug.json")
    path.write_text(json.dumps(build_citation_source_retrieval_debug(cwd), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
