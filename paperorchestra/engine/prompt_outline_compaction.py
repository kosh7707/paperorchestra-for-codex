from __future__ import annotations

from typing import Any

from paperorchestra.core.boundary import sanitize_author_facing_text


def _compact_outline_for_prompt(outline: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(outline, dict):
        return outline
    section_plan = []
    for item in outline.get("section_plan", [])[:8]:
        if not isinstance(item, dict):
            continue
        compact_item: dict[str, Any] = {"section_title": item.get("section_title")}
        subsections = []
        for subsection in item.get("subsections", [])[:2]:
            if not isinstance(subsection, dict):
                continue
            compact_subsection = {
                "subsection_title": subsection.get("subsection_title"),
                "content_bullets": subsection.get("content_bullets", [])[:1],
                "citation_hints": subsection.get("citation_hints", [])[:1],
            }
            subsections.append(compact_subsection)
        compact_item["subsections"] = subsections
        section_plan.append(compact_item)
    return {"section_plan": section_plan}


def _compact_intro_related_plan_for_prompt(plan: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(plan, dict):
        return plan
    compact: dict[str, Any] = {}
    intro = plan.get("introduction_strategy")
    if isinstance(intro, dict):
        compact["introduction_strategy"] = {
            "opening_frame": sanitize_author_facing_text(str(intro.get("hook_hypothesis") or ""), fallback=""),
            "problem_gap": sanitize_author_facing_text(str(intro.get("problem_gap_hypothesis") or ""), fallback=""),
            "background_topics": [
                sanitize_author_facing_text(str(item), fallback="")
                for item in (intro.get("search_directions") or [])[:3]
                if str(item).strip()
            ],
        }
    related = plan.get("related_work_strategy")
    if isinstance(related, dict):
        subsections = []
        for subsection in related.get("subsections", [])[:4]:
            if not isinstance(subsection, dict):
                continue
            subsections.append(
                {
                    "subsection_title": subsection.get("subsection_title"),
                    "methodology_cluster": sanitize_author_facing_text(str(subsection.get("methodology_cluster") or ""), fallback=""),
                    "comparative_context_goal": sanitize_author_facing_text(str(subsection.get("sota_investigation_mission") or ""), fallback=""),
                    "limitations_to_discuss": sanitize_author_facing_text(str(subsection.get("limitation_hypothesis") or ""), fallback=""),
                    "bridge_to_our_method": sanitize_author_facing_text(str(subsection.get("bridge_to_our_method") or ""), fallback=""),
                }
            )
        compact["related_work_strategy"] = {
            "overview": sanitize_author_facing_text(str(related.get("overview") or ""), fallback=""),
            "subsections": subsections,
        }
    return compact
