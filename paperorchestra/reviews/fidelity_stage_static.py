from __future__ import annotations

import os
from pathlib import Path

from paperorchestra.core.io import read_json
from paperorchestra.core.models import SessionState
from paperorchestra.manuscript import prompts as prompt_module
from paperorchestra.reviews.fidelity_types import FidelityCheck
from paperorchestra.reviews.reproducibility_citations import _citation_surface_health

PAPER_SOURCE_NAME = "PaperOrchestra A Multi-Agent Framework for Automated AI Research Paper Writing.pdf"
PAPER_SOURCE_ENV_VAR = "PAPERO_REFERENCE_PDF"
EXPECTED_OUTLINE_KEYS = {"plotting_plan", "intro_related_work_plan", "section_plan"}
EXPECTED_PROMPT_ASSETS = {
    "outline_agent.md",
    "literature_review_agent.md",
    "section_writing_agent.md",
    "content_refinement_agent.md",
    "prompt_fidelity_matrix.md",
}


def paper_source_candidates(cwd: str | Path | None) -> list[Path]:
    candidates: list[Path] = []
    explicit = os.environ.get(PAPER_SOURCE_ENV_VAR)
    if explicit:
        candidates.append(Path(explicit).expanduser().resolve())
    if cwd is not None:
        candidates.append(Path(cwd).resolve() / PAPER_SOURCE_NAME)
    repo_root = Path(prompt_module.__file__).resolve().parent.parent
    candidates.append(repo_root / PAPER_SOURCE_NAME)
    return candidates


def _session_artifact_dir(state: SessionState) -> Path | None:
    if not state.artifacts.paper_full_tex:
        return None
    return Path(state.artifacts.paper_full_tex).resolve().parent


def _paper_source_check(cwd: str | Path | None) -> FidelityCheck:
    return FidelityCheck(
        code="paper_source_present",
        status="implemented" if any(path.exists() for path in paper_source_candidates(cwd)) else "missing",
        rationale="An explicit or locally cached PaperOrchestra reference PDF should remain available as the primary reconstruction reference.",
    )


def _prompt_assets_check() -> FidelityCheck:
    prompt_assets_dir = Path(prompt_module.__file__).with_name("prompt_assets")
    prompt_asset_status = "missing"
    if prompt_assets_dir.exists():
        present_assets = {path.name for path in prompt_assets_dir.iterdir() if path.is_file()}
        if EXPECTED_PROMPT_ASSETS <= present_assets:
            prompt_asset_status = "implemented"
        elif present_assets:
            prompt_asset_status = "partial"
    return FidelityCheck(
        code="appendix_f_prompt_fidelity_assets",
        status=prompt_asset_status,
        rationale="Prompt fidelity claims should be backed by first-class Appendix F-derived prompt assets, not only compressed inline prompt summaries.",
    )


def _outline_contract_check(state: SessionState) -> FidelityCheck:
    outline_status = "partial"
    if state.artifacts.outline_json and Path(state.artifacts.outline_json).exists():
        outline_payload = read_json(state.artifacts.outline_json)
        outline_status = "implemented" if EXPECTED_OUTLINE_KEYS <= set(outline_payload.keys()) else "missing"
    return FidelityCheck(
        code="outline_json_contract",
        status=outline_status,
        rationale="The paper's Outline Agent emits a structured outline with plotting_plan, intro_related_work_plan, and section_plan.",
    )


def _parallel_semantics_check(state: SessionState) -> FidelityCheck:
    evidence_notes = list(state.notes_archive) + list(state.notes)
    parallel_status = "implemented" if any("completed in parallel" in note.lower() for note in evidence_notes) else "partial"
    return FidelityCheck(
        code="parallel_step_2_3_semantics",
        status=parallel_status,
        rationale="PaperOrchestra runs Plot Generation and Literature Review as sibling parallel stages after outline generation.",
    )


def _verified_citation_lane_check(state: SessionState) -> FidelityCheck:
    citation_surface = _citation_surface_health(state)
    return FidelityCheck(
        code="verified_citation_lane",
        status=citation_surface["status"],
        rationale="The paper requires candidate discovery, verification, citation registry construction, and BibTeX generation.",
        next_step=(
            "Rebuild the citation lane and confirm citation_registry.json, citation_map.json, and references.bib are non-empty."
            if citation_surface["issues"]
            else None
        ),
    )
