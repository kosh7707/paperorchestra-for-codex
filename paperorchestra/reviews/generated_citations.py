from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json
from paperorchestra.core.session import load_session
from paperorchestra.manuscript.citations import citation_entry_for_key
from paperorchestra.reviews.eval_text import normalize_eval_title
from paperorchestra.reviews.evaluation_io import _write_json_artifact

_CITE_RE = re.compile(r"\\cite[a-zA-Z*]*\s*(?:\[[^\]]*\]){0,2}\{([^}]+)\}")


def _cited_keys_from_latex(latex_text: str) -> list[str]:
    cited_keys: list[str] = []
    for match in _CITE_RE.findall(latex_text):
        for key in [part.strip() for part in match.split(",") if part.strip()]:
            if key not in cited_keys:
                cited_keys.append(key)
    return cited_keys


def _resolved_title_entries(cited_keys: list[str], citation_map: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    generated_titles: list[str] = []
    resolved_entries: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for key in cited_keys:
        entry = citation_entry_for_key(citation_map, key) if isinstance(citation_map, dict) else {}
        title = entry.get("title") if isinstance(entry, dict) else None
        if not isinstance(title, str) or not title.strip():
            continue
        clean_title = title.strip()
        normalized = normalize_eval_title(clean_title)
        if normalized in seen_titles:
            continue
        seen_titles.add(normalized)
        generated_titles.append(clean_title)
        resolved_entries.append(
            {
                "citation_key": key,
                "title": clean_title,
                "normalized_title": normalized,
                "paper_id": entry.get("paper_id") if isinstance(entry, dict) else None,
            }
        )
    return generated_titles, resolved_entries


def build_generated_citation_titles_payload(*, session_id: str, latex_text: str, citation_map: dict[str, Any]) -> dict[str, Any]:
    cited_keys = _cited_keys_from_latex(latex_text)
    generated_titles, resolved_entries = _resolved_title_entries(cited_keys, citation_map)
    return {
        "session_id": session_id,
        "cited_keys": cited_keys,
        "generated_titles": generated_titles,
        "resolved_entries": resolved_entries,
        "count": len(generated_titles),
        "notes": [
            "Titles are resolved from the current paper's cite-style commands against citation_map.json.",
            "Duplicate citation titles are collapsed by normalized title for scaffold comparisons.",
        ],
    }


def build_generated_citation_titles(cwd: str | Path | None) -> dict[str, Any]:
    state = load_session(cwd)
    if not state.artifacts.paper_full_tex or not Path(state.artifacts.paper_full_tex).exists():
        return {"cited_keys": [], "generated_titles": [], "notes": ["No paper_full_tex artifact available."]}
    if not state.artifacts.citation_map_json or not Path(state.artifacts.citation_map_json).exists():
        return {"cited_keys": [], "generated_titles": [], "notes": ["No citation_map_json artifact available."]}

    return build_generated_citation_titles_payload(
        session_id=state.session_id,
        latex_text=Path(state.artifacts.paper_full_tex).read_text(encoding="utf-8"),
        citation_map=read_json(state.artifacts.citation_map_json),
    )


def write_generated_citation_titles(cwd: str | Path | None, output_path: str | Path) -> Path:
    payload = build_generated_citation_titles(cwd)
    return _write_json_artifact(payload, output_path)
