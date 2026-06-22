from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json, read_text, write_json, write_text
from paperorchestra.core.session import load_session, save_session
from paperorchestra.core.session_paths import runtime_root
from paperorchestra.engine.current_manuscript_stages import compile_current_paper
from paperorchestra.engine.plan_gate import PlanGateResult, ensure_approved_plan
from paperorchestra.engine.planning_stages import generate_outline, plan_narrative_and_claims
from paperorchestra.engine.research_prior_work_stage import research_prior_work
from paperorchestra.engine.review_stages import review_current_paper
from paperorchestra.engine.section_writing_stage import write_sections
from paperorchestra.manuscript.skeleton import can_derive_paper_skeleton, write_paper_skeleton
from paperorchestra.manuscript.revisions import write_revision_suggestions
from paperorchestra.reviews.citation_model_writer import write_citation_support_review
from paperorchestra.reviews.critic_trust import build_critic_trust_card, require_live_critic_trust
from paperorchestra.reviews.section_review import write_section_review
from paperorchestra.runtime.provider_base import BaseProvider, ProviderError
from paperorchestra.runtime.provider_registry import get_citation_support_provider
from paperorchestra.runtime.provider_web_capability import provider_supports_web_search


DEFAULT_AUTHORING_ROUND_SCHEMA = "authoring-round/1"


def run_authoring_round(
    cwd: str | Path | None,
    provider: BaseProvider,
    *,
    round_dir: str | Path | None = None,
    runtime_mode: str = "compatibility",
    only_sections: list[str] | str | None = None,
    output_path: str | Path | None = None,
    claim_safe: bool = False,
    bypass_plan_gate: bool = False,
    ensure_planning_artifacts: bool = True,
    run_literature: bool = True,
    import_literature_seed: bool = True,
    require_complete_metadata: bool = False,
    require_web_research: bool = False,
    run_critic: bool = True,
    require_live_critic: bool = False,
    compile_paper: bool = False,
    citation_evidence_mode: str = "web",
    citation_provider_name: str | None = None,
    citation_provider_command: str | None = None,
    provider_name: str | None = None,
    provider_command: str | None = None,
    progress_stream: Any = None,
) -> dict[str, Any]:
    """Run one evidence-bearing manuscript authoring round.

    This is the first-draft/revision orchestration surface used by the CLI,
    MCP tool, and Codex skill.  It intentionally performs pre-draft literature
    positioning before `write_sections`, then records critic artifacts after the
    manuscript exists.  Callers can disable expensive lanes for tests or manual
    dry-runs, but the manifest always records which lanes were skipped.
    """

    gate = ensure_approved_plan(cwd, bypass=bypass_plan_gate)
    if require_web_research and run_literature and not provider_supports_web_search(provider):
        raise ProviderError(
            "authoring-round --require-web-research needs a shell provider command with web search capability. "
            "Use a codex --search exec provider command or disable the requirement for local tests."
        )

    if require_live_critic:
        require_live_critic_trust(
            _critic_trust_card(
                provider_name=provider_name,
                provider_command=provider_command,
                citation_evidence_mode=citation_evidence_mode,
                claim_safe=claim_safe,
            )
        )

    round_path = _resolve_round_dir(cwd, round_dir)
    output_tex = Path(output_path).resolve() if output_path else round_path / "paper.full.tex"
    artifacts: dict[str, Any] = {}
    notes: list[str] = []

    if ensure_planning_artifacts:
        _ensure_outline(cwd, provider, runtime_mode=runtime_mode, artifacts=artifacts, notes=notes)
    else:
        notes.append("Outline/narrative planning artifact refresh skipped by caller.")

    literature_result: dict[str, Any] | None = None
    seed_path = round_path / "prior_work_seed.json"
    if run_literature:
        literature_result = research_prior_work(
            cwd,
            provider,
            output=seed_path,
            runtime_mode=runtime_mode,
            source="codex_web_seed",
            import_seed=import_literature_seed,
            require_complete_metadata=require_complete_metadata,
        )
        artifacts["prior_work_seed"] = _artifact(seed_path)
        notes.append("Prior-work seed generated before drafting.")
    else:
        notes.append("Prior-work research skipped by caller.")

    if ensure_planning_artifacts:
        _refresh_narrative_planning(cwd, provider, runtime_mode=runtime_mode, artifacts=artifacts, notes=notes)
        if can_derive_paper_skeleton(gate):
            skeleton_path = write_paper_skeleton(cwd, gate=gate)
            artifacts["paper_skeleton"] = _artifact(skeleton_path)
            notes.append("Derived paper-skeleton.md after narrative planning and before drafting.")
        else:
            notes.append("paper-skeleton.md derivation skipped because this round used explicit plan-gate bypass without an approved plan.")

    positioning_path = round_path / "positioning_brief.md"
    _write_positioning_brief(positioning_path, cwd=cwd, gate=gate, literature_result=literature_result, seed_path=seed_path if seed_path.exists() else None)
    artifacts["positioning_brief"] = _artifact(positioning_path)

    paper_path = write_sections(
        cwd,
        provider,
        runtime_mode=runtime_mode,
        only_sections=only_sections,
        output_path=output_tex,
        claim_safe=claim_safe,
        bypass_plan_gate=bypass_plan_gate,
    )
    artifacts["paper_full_tex"] = _artifact(paper_path)

    if compile_paper:
        compiled = compile_current_paper(cwd)
        artifacts["compiled_pdf"] = _artifact(compiled)
    else:
        notes.append("Compile skipped by caller.")

    critic_trust = _critic_trust_card(
        provider_name=provider_name,
        provider_command=provider_command,
        citation_evidence_mode=citation_evidence_mode,
        claim_safe=claim_safe,
    )
    if run_critic:
        review = review_current_paper(cwd, provider, review_name=f"{round_path.name}.review.json", runtime_mode=runtime_mode)
        section = write_section_review(cwd, round_path / "section_review.json")
        citation_provider = get_citation_support_provider(
            citation_provider_name or provider_name or "shell",
            command=citation_provider_command or provider_command,
            evidence_mode=citation_evidence_mode,
        )
        citation = write_citation_support_review(
            cwd,
            round_path / "citation_support_review.json",
            provider=citation_provider,
            evidence_mode=citation_evidence_mode,
            progress_stream=progress_stream,
        )
        suggestions = write_revision_suggestions(
            paper_path,
            review,
            round_path / "revision_suggestions.json",
            section_review_json=section,
            citation_review_json=citation,
        )
        artifacts.update(
            {
                "review": _artifact(review),
                "section_review": _artifact(section),
                "citation_support_review": _artifact(citation),
                "revision_suggestions": _artifact(suggestions),
            }
        )
        status = "completed_with_critic"
    else:
        notes.append("Critic lanes skipped by caller.")
        status = "drafted_without_critic"

    manifest = {
        "schema_version": DEFAULT_AUTHORING_ROUND_SCHEMA,
        "status": status,
        "mode": "revision" if only_sections else "first_draft",
        "round_dir": str(round_path),
        "plan_gate": gate.to_dict(),
        "options": {
            "ensure_planning_artifacts": ensure_planning_artifacts,
            "run_literature": run_literature,
            "import_literature_seed": import_literature_seed,
            "require_web_research": require_web_research,
            "run_critic": run_critic,
            "require_live_critic": require_live_critic,
            "compile_paper": compile_paper,
            "citation_evidence_mode": citation_evidence_mode,
            "runtime_mode": runtime_mode,
            "only_sections": only_sections,
            "claim_safe": claim_safe,
            "bypass_plan_gate": bypass_plan_gate,
        },
        "critic_trust": critic_trust,
        "artifacts": artifacts,
        "notes": notes,
        "next_recommended_actions": _next_actions(status=status, compile_paper=compile_paper, run_critic=run_critic),
    }
    manifest_path = round_path / "authoring-round.manifest.json"
    manifest["artifacts"]["manifest"] = _manifest_artifact(manifest_path)
    write_json(manifest_path, manifest)
    _record_authoring_round(cwd, manifest_path, status=status)
    return manifest


def _ensure_outline(
    cwd: str | Path | None,
    provider: BaseProvider,
    *,
    runtime_mode: str,
    artifacts: dict[str, Any],
    notes: list[str],
) -> None:
    # Authoring rounds are the user-facing "turn the approved plan into a draft"
    # surface.  Reusing an older outline by mere file existence lets a previous
    # section contract leak into a new approved plan, causing downstream
    # narrative/claim validation failures.  Regenerate the outline whenever the
    # caller asks us to ensure planning artifacts; callers that intentionally
    # want legacy/manual artifacts can pass ensure_planning_artifacts=False.
    outline_path = generate_outline(cwd, provider, runtime_mode=runtime_mode)
    notes.append("Outline regenerated before drafting.")
    artifacts["outline_json"] = _artifact(outline_path)


def _refresh_narrative_planning(
    cwd: str | Path | None,
    provider: BaseProvider,
    *,
    runtime_mode: str,
    artifacts: dict[str, Any],
    notes: list[str],
) -> None:
    planning_paths = plan_narrative_and_claims(cwd, provider, runtime_mode=runtime_mode)
    notes.append("Narrative, claim, and citation-placement planning artifacts refreshed after prior-work import and before drafting.")
    for name, path in planning_paths.items():
        artifacts[name] = _artifact(path)


def _critic_trust_card(
    *,
    provider_name: str | None,
    provider_command: str | None,
    citation_evidence_mode: str,
    claim_safe: bool,
) -> dict[str, Any]:
    return build_critic_trust_card(
        provider_name=provider_name,
        provider_command=provider_command,
        citation_evidence_mode=citation_evidence_mode,
        claim_safe=claim_safe,
    )


def _resolve_round_dir(cwd: str | Path | None, round_dir: str | Path | None) -> Path:
    if round_dir is not None:
        path = Path(round_dir).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path
    root = runtime_root(cwd)
    for index in range(1, 10_000):
        candidate = root / f"round-{index}"
        if not candidate.exists():
            candidate.mkdir(parents=True)
            return candidate
    raise RuntimeError("Unable to allocate a new authoring round directory.")


def _manifest_artifact(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).resolve()
    return {
        "path": str(resolved),
        "exists": True,
        "sha256": None,
        "hash_note": "Manifest self-hash is intentionally omitted because embedding it would change the file bytes.",
    }


def _artifact(path: str | Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    resolved = Path(path).resolve()
    result: dict[str, Any] = {"path": str(resolved), "exists": resolved.exists()}
    if resolved.exists() and resolved.is_file():
        result["sha256"] = hashlib.sha256(resolved.read_bytes()).hexdigest()
        result["bytes"] = resolved.stat().st_size
    return result


def _write_positioning_brief(
    path: Path,
    *,
    cwd: str | Path | None,
    gate: PlanGateResult,
    literature_result: dict[str, Any] | None,
    seed_path: Path | None,
) -> None:
    plan_excerpt = _excerpt(gate.plan_path, max_chars=2800) if gate.plan_path else "No plan path recorded."
    idea_excerpt = _excerpt(load_session(cwd).inputs.idea_path, max_chars=1400)
    references = _reference_bullets(seed_path)
    literature_status = "skipped" if literature_result is None else f"generated {literature_result.get('reference_count', 0)} candidate references"
    write_text(
        path,
        "\n".join(
            [
                "# Authoring-Round Positioning Brief",
                "",
                "This artifact is written before manuscript drafting so the draft lane can position the paper instead of producing an isolated TeX file.",
                "",
                "## Plan anchor",
                "",
                f"- Plan gate: `{gate.reason}`",
                f"- Plan path: `{gate.plan_path or 'missing'}`",
                "",
                "```text",
                plan_excerpt.strip(),
                "```",
                "",
                "## Material anchor",
                "",
                "```text",
                idea_excerpt.strip(),
                "```",
                "",
                "## Prior-work scan",
                "",
                f"- Status: {literature_status}",
                f"- Seed path: `{seed_path}`" if seed_path else "- Seed path: not available",
                "",
                references or "No parsed prior-work entries were available; keep citation claims conservative and mark missing citations explicitly.",
                "",
                "## Drafting contract",
                "",
                "- Frame the paper against the prior-work scan before writing Related Work or Introduction claims.",
                "- Do not invent quantitative results; keep placeholders or qualitative trends when the experimental log has no final numbers.",
                "- Preserve the author-approved plan as the claim boundary.",
                "- Leave uncertain citation slots reviewable by the citation-support critic.",
                "",
            ]
        ),
    )


def _excerpt(path: str | Path | None, *, max_chars: int) -> str:
    if not path:
        return ""
    try:
        text = read_text(path)
    except OSError:
        return f"Unable to read {path}."
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n...[truncated]"


def _reference_bullets(seed_path: Path | None) -> str:
    if seed_path is None or not seed_path.exists():
        return ""
    try:
        payload = read_json(seed_path)
    except Exception:
        return "Unable to parse prior-work seed."
    references = payload.get("references") if isinstance(payload, dict) else None
    if not isinstance(references, list):
        return ""
    lines: list[str] = []
    for entry in references[:12]:
        if not isinstance(entry, dict):
            continue
        title = entry.get("title") or entry.get("paper_title") or "Untitled"
        year = entry.get("year") or entry.get("publication_year") or "n.d."
        venue = entry.get("venue") or entry.get("source") or "unknown venue"
        rationale = entry.get("relevance") or entry.get("reason") or entry.get("summary") or "positioning candidate"
        lines.append(f"- {title} ({year}, {venue}): {rationale}")
    return "\n".join(lines)


def _next_actions(*, status: str, compile_paper: bool, run_critic: bool) -> list[str]:
    actions = []
    if not compile_paper:
        actions.append("Run compile when the TeX environment is available.")
    if not run_critic:
        actions.append("Run live review before treating the draft as ready for revision.")
    if status == "completed_with_critic":
        actions.append("Use revision_suggestions.json for the next bounded edit round.")
        actions.append("Run quality-gate after citation and result placeholders are resolved.")
    return actions


def _record_authoring_round(cwd: str | Path | None, manifest_path: Path, *, status: str) -> None:
    state = load_session(cwd)
    state.current_phase = "authoring_round"
    state.active_artifact = str(manifest_path)
    state.notes.append(f"Authoring round {status}: {manifest_path}")
    save_session(cwd, state)


__all__ = ["DEFAULT_AUTHORING_ROUND_SCHEMA", "run_authoring_round"]
