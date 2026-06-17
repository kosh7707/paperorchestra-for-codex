from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from paperorchestra.core.io import read_text
from paperorchestra.engine.prompt_context import _data_block, _prompt_compact_text


@dataclass(frozen=True)
class PriorWorkSeedPrompts:
    system_prompt: str
    user_prompt: str


def build_prior_work_context_from_paths(paper: str | Path | None, artifact_repo: str | Path | None) -> str:
    chunks: list[str] = []
    if paper:
        paper_path = Path(paper).resolve()
        if paper_path.exists():
            chunks.append(_data_block("source_paper.tex", read_text(paper_path)))
            references = paper_path.parent / "references.bib"
            if references.exists():
                chunks.append(_data_block("source_references.bib", read_text(references)))
    if artifact_repo:
        repo = Path(artifact_repo).resolve()
        for rel in ["README.md", "benchmarks/result.txt", "benchmarks/DATA_FORMAT.md"]:
            path = repo / rel
            if path.exists():
                chunks.append(_data_block(f"artifact_repo/{rel}", read_text(path)))
    return "\n\n".join(chunks) if chunks else ""


def build_prior_work_seed_prompts(
    inputs: dict[str, str],
    *,
    cutoff_date: str | None,
    source: str,
    paper: str | Path | None,
    artifact_repo: str | Path | None,
) -> PriorWorkSeedPrompts:
    extra_context = _prompt_compact_text(
        build_prior_work_context_from_paths(paper, artifact_repo),
        head_chars=6000,
        tail_chars=1000,
    )
    prompt_idea = _prompt_compact_text(inputs["idea"], head_chars=6000, tail_chars=1000)
    prompt_experimental_log = _prompt_compact_text(
        inputs["experimental_log"],
        head_chars=10000,
        tail_chars=2000,
    )
    user_prompt = f"""
{_data_block('idea.md', prompt_idea)}

{_data_block('experimental_log.md', prompt_experimental_log)}

{_data_block('conference_guidelines.md', inputs['guidelines'])}

{_data_block('cutoff_date', cutoff_date or 'null')}

{extra_context}

Task:
Produce a curated prior_work seed JSON for this research paper. Prefer canonical standards, foundational papers, benchmark/spec documents, and close prior work. If this runtime has web/search tools, use them conservatively; otherwise derive only from supplied materials. Do not invent authors or venues. If uncertain, include a provenance note saying what must be manually verified.

Return JSON with exactly two top-level keys: references and research_notes.
""".strip()
    system_prompt = f"""
You are a prior-work seed generator for PaperOrchestra.
Return one valid JSON object matching this contract:
- references: array of objects with title, authors, year, venue, url, doi, source, why_relevant, provenance_notes
- research_notes: array of concise caveats or follow-up checks

Rules:
- Use source={source!r} unless an entry has a more precise provenance.
- Prefer official RFC/NIST/spec URLs for standards.
- Do not fabricate bibliographic metadata. Use null for unknown year/venue/url/doi.
- This seed is an input to import-prior-work; it is not live Semantic Scholar verification.

""".strip()
    return PriorWorkSeedPrompts(system_prompt=system_prompt, user_prompt=user_prompt)
