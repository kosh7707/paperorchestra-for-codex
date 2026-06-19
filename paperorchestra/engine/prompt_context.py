from __future__ import annotations

from pathlib import Path

from paperorchestra.core.io import read_text
from paperorchestra.engine.completion_env import _env_flag

from .prompt_citation_compaction import _compact_citation_map_for_prompt
from .prompt_citation_context import _raise_if_strict_source_citations_unmapped, _unknown_citation_key_counts
from .prompt_figure_compaction import _compact_plot_assets_for_prompt, _compact_plot_manifest_for_prompt
from .prompt_markup import _data_block, _prompt_compact_text
from .prompt_outline_compaction import _compact_intro_related_plan_for_prompt, _compact_outline_for_prompt
from .prompt_source_context import _source_critical_context_for_prompt, _source_grounding_text


def _strict_content_gates_enabled(*, claim_safe: bool = False) -> bool:
    return claim_safe or _env_flag("PAPERO_STRICT_CONTENT_GATES")


def _read_inputs(state) -> dict[str, str]:
    return {
        "idea": read_text(state.inputs.idea_path),
        "experimental_log": read_text(state.inputs.experimental_log_path),
        "template": read_text(state.inputs.template_path),
        "guidelines": read_text(state.inputs.guidelines_path),
        "figures": _figure_listing(state.inputs.figures_dir),
    }


def _figure_listing(figures_dir: str | None) -> str:
    if not figures_dir:
        return "No figures directory provided."
    root = Path(figures_dir)
    if not root.exists():
        return f"Figures directory does not exist: {figures_dir}"
    files = [str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()]
    if not files:
        return "Figures directory is empty."
    return "\n".join(sorted(files))


__all__ = [
    "_compact_citation_map_for_prompt",
    "_compact_intro_related_plan_for_prompt",
    "_compact_outline_for_prompt",
    "_compact_plot_assets_for_prompt",
    "_compact_plot_manifest_for_prompt",
    "_data_block",
    "_figure_listing",
    "_prompt_compact_text",
    "_raise_if_strict_source_citations_unmapped",
    "_read_inputs",
    "_source_critical_context_for_prompt",
    "_source_grounding_text",
    "_strict_content_gates_enabled",
    "_unknown_citation_key_counts",
]
