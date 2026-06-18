from __future__ import annotations

import json

from paperorchestra.engine.planning_stages import _author_facing_writer_brief_block
from paperorchestra.engine.prompt_context import _data_block, _prompt_compact_text
from paperorchestra.engine.section_writing_types import SectionPromptContext
from paperorchestra.manuscript.validator import canonical_citation_keys


def render_section_writing_user_prompt(context: SectionPromptContext) -> str:
    prompt_idea = _prompt_compact_text(context.inputs["idea"], head_chars=3000, tail_chars=500)
    prompt_experimental_log = _prompt_compact_text(
        context.inputs["experimental_log"],
        head_chars=5000,
        tail_chars=1000,
    )
    return f"""
{_data_block('outline.json', json.dumps(context.outline.prompt_outline, indent=2, ensure_ascii=False))}

{_author_facing_writer_brief_block(context.planning.writer_brief)}

{_data_block('idea.md', prompt_idea)}

{_data_block('experimental_log.md', prompt_experimental_log)}

{_data_block('source_critical_context.json', json.dumps(context.source_critical_context, indent=2, ensure_ascii=False))}

{_data_block('citation_map.json', json.dumps(context.citations.prompt_citation_map, indent=2, ensure_ascii=False))}

{_data_block('citation_coverage_target.json', json.dumps(_citation_coverage_payload(context), ensure_ascii=False))}

{_data_block('plot_manifest.json', json.dumps(context.plots.prompt_plot_manifest, indent=2, ensure_ascii=False))}

{_data_block('plot_assets.json', json.dumps(context.plots.prompt_plot_assets_index, indent=2, ensure_ascii=False))}

{_data_block('conference_guidelines.md', context.inputs['guidelines'])}

{_data_block('current_template.tex', context.template.prompt_template_content)}

{_data_block('figures_list', context.inputs['figures'])}

{_data_block('figures_dir', context.figures_dir or 'null')}
{_data_block('rewrite_scope.json', json.dumps(_rewrite_scope_payload(context), ensure_ascii=False))}

{_global_section_instructions(context)}
{_section_scope_instructions(context)}
""".strip()


def _citation_coverage_payload(context: SectionPromptContext) -> dict[str, int]:
    return {
        "min_distinct_verified_citations": context.citations.min_citation_coverage,
        "available_verified_citations": len(canonical_citation_keys(context.citations.citation_map)),
    }


def _rewrite_scope_payload(context: SectionPromptContext) -> dict[str, object]:
    return {
        "only_sections": context.selected_sections,
        "preserve_all_other_sections": bool(context.selected_sections),
    }


def _global_section_instructions(context: SectionPromptContext) -> str:
    citation_requirement = (
        f"- Use at least {context.citations.min_citation_coverage} distinct verified citations "
        "when that many verified references are available.\n"
    )
    return (
        "Global Writing Constraints:\n"
        f"{citation_requirement}"
        "- Do NOT invent meta sections such as checklists or workflow notes that are not part of "
        "current_template.tex.\n"
        "- Write manuscript prose only; express evidence limits as scholarly assumptions, scope, and limitations.\n"
        "- Do NOT preserve input-note headings as manuscript sections; fold their constraints into normal prose, "
        "especially Discussion limitations.\n"
    )


def _section_scope_instructions(context: SectionPromptContext) -> str:
    if not context.selected_sections:
        return ""
    return (
        "Section-scope Instructions:\n"
        f"- Rewrite ONLY these sections: {', '.join(context.selected_sections)}.\n"
        "- Preserve all section titles, labels, citations, and figure references already present in "
        "current_template.tex for those sections.\n"
        "- Do NOT invent new citation keys, figure filenames, labels, or cross-references that are absent from "
        "current_template.tex.\n"
        "- Prefer revising the prose within the existing section skeleton over introducing new structural elements.\n"
    )
