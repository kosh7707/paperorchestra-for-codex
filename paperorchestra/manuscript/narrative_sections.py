from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from paperorchestra.core.boundary import is_material_packet_control_section_title, is_material_packet_section_title
from paperorchestra.manuscript.narrative_sources import _plain_section_title


@dataclass(frozen=True)
class NarrativeSectionTargets:
    method: str
    proof: str
    results: str
    discussion: str
    positioning: str


def _section_titles(outline: dict[str, Any], template_text: str) -> list[str]:
    titles: list[str] = []
    saw_material_packet_control_section = False
    for item in outline.get("section_plan") or []:
        if isinstance(item, dict) and isinstance(item.get("section_title"), str):
            title = _plain_section_title(item["section_title"])
            if is_material_packet_control_section_title(title):
                saw_material_packet_control_section = True
            if not is_material_packet_section_title(title):
                titles.append(title)
    if saw_material_packet_control_section and not any(title.strip().lower() == "discussion" for title in titles):
        titles.append("Discussion")
    if titles:
        return titles
    template_titles = []
    for match in re.finditer(r"\\section\*?\{([^}]+)\}", template_text):
        title = match.group(1).strip()
        if not is_material_packet_section_title(title):
            template_titles.append(title)
    return template_titles


def default_sections() -> list[str]:
    return [
        "Introduction",
        "Related Work",
        "Method",
        "Experiments",
        "Discussion",
        "Conclusion",
    ]


def section_targets(sections: list[str], *, citation_key: str | None) -> NarrativeSectionTargets:
    method_section = next((s for s in sections if re.search(r"method|approach|construction", s, re.I)), "Method")
    proof_section = next((s for s in sections if re.search(r"security|proof|analysis", s, re.I)), method_section)
    results_section = next(
        (s for s in sections if re.search(r"experiment|result|benchmark|evaluation", s, re.I)),
        "Experiments",
    )
    discussion_section = next((s for s in sections if re.search(r"discussion|limitation", s, re.I)), "Discussion")
    positioning_section = _positioning_section(sections, citation_key=citation_key)
    return NarrativeSectionTargets(
        method=method_section,
        proof=proof_section,
        results=results_section,
        discussion=discussion_section,
        positioning=positioning_section,
    )


def _positioning_section(sections: list[str], *, citation_key: str | None) -> str:
    positioning_section = next((s for s in sections if re.search(r"related|introduction", s, re.I)), "")
    if citation_key and not positioning_section:
        # Some minimal/generated outlines omit Introduction/Related Work even when the
        # template has them. Keep verified-citation positioning available instead of
        # dropping the planning obligation, while still preferring explicit
        # intro/related sections when present.
        positioning_section = next((s for s in sections if s.strip()), "Introduction")
    return positioning_section
