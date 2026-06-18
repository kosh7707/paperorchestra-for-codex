from __future__ import annotations

import json
from typing import Any

from paperorchestra.engine.planning_payloads import _author_facing_writer_brief_block
from paperorchestra.engine.prompt_context import _data_block
from paperorchestra.engine.refine_review import _redact_review_scores_for_writer


def build_refinement_user_prompt(
    *,
    paper_text: str,
    review_payload: dict[str, Any],
    writer_brief: dict[str, Any] | None,
    experimental_log_text: str,
    source_critical_context: dict[str, Any],
    citation_map: dict[str, Any],
    plot_manifest: dict[str, Any] | list[Any] | None,
    plot_assets_index: dict[str, Any] | list[Any] | None,
    previous_worklog: str,
) -> str:
    writer_review_payload = _redact_review_scores_for_writer(review_payload)
    return f"""
{_data_block('paper.tex', paper_text)}

{_data_block('reviewer_feedback', json.dumps(writer_review_payload, indent=2, ensure_ascii=False))}

{_author_facing_writer_brief_block(writer_brief)}

{_data_block('experimental_log.md', experimental_log_text)}

{_data_block('source_critical_context.json', json.dumps(source_critical_context, indent=2, ensure_ascii=False))}

{_data_block('citation_map.json', json.dumps(citation_map, indent=2, ensure_ascii=False))}

{_data_block('plot_manifest.json', json.dumps(plot_manifest, indent=2, ensure_ascii=False))}

{_data_block('plot_assets.json', json.dumps(plot_assets_index, indent=2, ensure_ascii=False))}

{_data_block('worklog.json', previous_worklog)}
""".strip()
