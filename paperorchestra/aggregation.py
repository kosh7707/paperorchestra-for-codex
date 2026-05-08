from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import Any

from .io_utils import write_json
from .literature import SemanticScholarError, mock_verified_paper, normalize_title, search_semantic_scholar
from .models import ClaimCandidate, EvidenceRegistry, MissingEvidenceSuggestion, PriorWorkCandidate, StoryCandidate
from .session import project_root

TEXT_EXTENSIONS = {
    ".md",
    ".txt",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".toml",
    ".csv",
    ".tsv",
    ".py",
    ".tex",
}
OMX_PRIORITY_FILES: tuple[str, ...] = (
    ".omx/notepad.md",
    ".omx/project-memory.json",
    ".omx/state/current-task-baseline.json",
    ".omx/state/session.json",
)
SKIP_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    "target",
}
MAX_SOURCE_BYTES = 120 * 1024
NUMERIC_RE = re.compile(r"\d")


def _normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        for prefix in ("- ", "* ", "• "):
            if line.startswith(prefix):
                line = line[len(prefix) :].strip()
                break
        lines.append(line)
    if len(lines) > 1:
        return lines
    if "," in text:
        parts = [part.strip() for part in text.split(",") if part.strip()]
        if len(parts) > 1:
            return parts
    return [text]


def _textify(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(_normalize_list(value))
    return str(value).strip()


def _contains_numeric(values: list[str]) -> bool:
    return any(NUMERIC_RE.search(item or "") for item in values)


def _confidence_note(answers: dict[str, Any], discovered_sources: list[dict[str, Any]]) -> list[str]:
    notes: list[str] = []
    if not discovered_sources:
        notes.append("No supplemental evidence sources were aggregated; synthesis relies only on user-provided intake answers.")
    if not _contains_numeric(_normalize_list(answers.get("key_results"))):
        notes.append("Confirmed results currently lack explicit numeric signals; comparative claims should stay conservative.")
    if not _normalize_list(answers.get("baselines")):
        notes.append("No baselines were supplied; superiority framing should remain tentative until comparison targets are grounded.")
    return notes


def normalize_evidence_paths(value: Any) -> list[str]:
    paths: list[str] = []
    if value is None:
        return paths
    if isinstance(value, list):
        for item in value:
            item_text = str(item).strip()
            if item_text:
                paths.append(item_text)
        return paths
    for chunk in re.split(r"[\n,;]+", str(value)):
        chunk = chunk.strip()
        if chunk:
            paths.append(chunk)
    return paths


def _is_text_file(path: Path) -> bool:
    if path.suffix.lower() in TEXT_EXTENSIONS:
        return True
    try:
        data = path.read_bytes()[:512]
    except OSError:
        return False
    return b"\x00" not in data


def _classify_source(path: Path) -> str:
    parts = set(path.parts)
    if ".omx" in parts:
        return "omx-artifact"
    if ".claude" in parts:
        return "claude-cache"
    if ".cursor" in parts:
        return "cursor-cache"
    if ".antigravity" in parts:
        return "antigravity-cache"
    if ".openclaw" in parts:
        return "openclaw-cache"
    return "supplemental"


def _source_record(candidate: Path, root: Path) -> dict[str, Any] | None:
    if not candidate.is_file() or not _is_text_file(candidate):
        return None
    if candidate.stat().st_size > MAX_SOURCE_BYTES:
        return None
    try:
        snippet = candidate.read_text(encoding="utf-8", errors="ignore").strip()
    except OSError:
        return None
    first_lines = [line.strip() for line in snippet.splitlines() if line.strip()][:3]
    return {
        "path": str(candidate),
        "relative_path": str(candidate.relative_to(root)) if candidate.is_relative_to(root) else str(candidate),
        "source_type": _classify_source(candidate),
        "size_bytes": candidate.stat().st_size,
        "preview": " ".join(first_lines)[:400],
    }


def discover_omx_supporting_sources(cwd: str | Path | None) -> list[dict[str, Any]]:
    root = project_root(cwd).resolve()
    discovered: list[dict[str, Any]] = []
    seen: set[str] = set()
    for relative_path in OMX_PRIORITY_FILES:
        candidate = (root / relative_path).resolve()
        if not candidate.exists() or not candidate.is_relative_to(root):
            continue
        record = _source_record(candidate, root)
        if record is None:
            continue
        seen.add(record["path"])
        discovered.append(record)
    return discovered




def discover_supporting_sources_with_warnings(
    cwd: str | Path | None,
    evidence_paths: list[str],
    *,
    max_depth: int = 4,
    allow_outside_workspace: bool = False,
) -> tuple[list[dict[str, Any]], list[str]]:
    root = project_root(cwd)
    discovered = discover_omx_supporting_sources(cwd)
    seen: set[str] = {item["path"] for item in discovered}
    warnings: list[str] = []
    for raw in evidence_paths:
        resolved = (root / raw).resolve() if not Path(raw).is_absolute() else Path(raw).resolve()
        if not allow_outside_workspace:
            try:
                resolved.relative_to(root)
            except ValueError as exc:
                raise ValueError(f"evidence_paths must stay inside the workspace unless allow_outside_workspace is enabled: {resolved}") from exc
        if not resolved.exists():
            warnings.append(f"evidence_paths entry not found and was skipped: {resolved}")
            continue
        if resolved.is_file():
            candidates = [resolved]
        else:
            candidates = []
            base_depth = len(resolved.parts)
            for walk_root, dirnames, filenames in os.walk(resolved):
                current = Path(walk_root)
                if len(current.parts) - base_depth > max_depth:
                    dirnames[:] = []
                    continue
                dirnames[:] = [name for name in dirnames if name not in SKIP_DIRS]
                for filename in filenames:
                    candidates.append(current / filename)
        for candidate in candidates:
            key = str(candidate)
            if key in seen:
                continue
            record = _source_record(candidate, root)
            if record is None:
                continue
            seen.add(key)
            discovered.append(record)
    return discovered, warnings

def discover_supporting_sources(
    cwd: str | Path | None,
    evidence_paths: list[str],
    *,
    max_depth: int = 4,
    allow_outside_workspace: bool = False,
) -> list[dict[str, Any]]:
    discovered, _ = discover_supporting_sources_with_warnings(
        cwd,
        evidence_paths,
        max_depth=max_depth,
        allow_outside_workspace=allow_outside_workspace,
    )
    return discovered


def build_evidence_registry(answers: dict[str, Any], discovered_sources: list[dict[str, Any]]) -> EvidenceRegistry:
    methodology = _textify(answers.get("method_summary")) or _textify(answers.get("experiments_ran")) or "unknown"
    results = _normalize_list(answers.get("key_results"))
    experiments = _normalize_list(answers.get("experiments_ran"))
    datasets = _normalize_list(answers.get("datasets_or_benchmarks"))
    baselines = _normalize_list(answers.get("baselines"))
    figure_preferences = _normalize_list(answers.get("figure_story"))
    supporting_quotes = [entry["preview"] for entry in discovered_sources if entry.get("preview")][:5]
    open_questions = _normalize_list(answers.get("open_questions"))
    return EvidenceRegistry(
        methodology=methodology,
        confirmed_results=results,
        experiments=experiments,
        datasets=datasets,
        baselines=baselines,
        figure_preferences=figure_preferences,
        discovered_sources=discovered_sources,
        supporting_quotes=supporting_quotes,
        confidence_notes=_confidence_note(answers, discovered_sources),
        open_questions=open_questions,
    )


def build_prior_work_seeds(answers: dict[str, Any], registry: EvidenceRegistry) -> list[str]:
    seeds: list[str] = []
    method = registry.methodology if registry.methodology != "unknown" else ""
    problem = _textify(answers.get("problem_statement"))
    datasets = registry.datasets or ["benchmark"]
    baselines = registry.baselines
    venue = _textify(answers.get("venue"))
    if problem:
        seeds.append(problem)
    if method:
        seeds.append(method)
    for dataset in datasets[:3]:
        if method:
            seeds.append(f"{method} {dataset}")
        if problem:
            seeds.append(f"{problem} {dataset}")
    for baseline in baselines[:4]:
        if method:
            seeds.append(f"{baseline} comparison to {method}")
    if venue and venue != "unknown":
        seeds.append(f"{method or problem} {venue}")
    unique: list[str] = []
    seen = set()
    for seed in seeds:
        norm = re.sub(r"\s+", " ", seed).strip()
        if norm and norm not in seen:
            seen.add(norm)
            unique.append(norm)
    return unique[:10]


def build_missing_evidence_suggestions(
    answers: dict[str, Any],
    registry: EvidenceRegistry,
    prior_work_seeds: list[str],
) -> list[MissingEvidenceSuggestion]:
    suggestions: list[MissingEvidenceSuggestion] = []
    if not registry.datasets:
        suggestions.append(
            MissingEvidenceSuggestion(
                code="missing-datasets",
                title="평가 환경을 더 명확히 할 필요가 있음",
                rationale="현재 방법론/결과는 있지만 어떤 데이터셋·벤치마크에서 검증했는지가 부족합니다.",
                suggested_action="실험이 수행된 데이터셋, split, 평가 조건을 명시하세요.",
                priority=95,
                linked_prior_work_seed=prior_work_seeds[0] if prior_work_seeds else None,
                grounding_titles=[],
            )
        )
    if not registry.baselines:
        suggestions.append(
            MissingEvidenceSuggestion(
                code="missing-baselines",
                title="비교 대상이 부족함",
                rationale="강한 claim을 하려면 prior work와 연결될 baseline이 필요합니다.",
                suggested_action="직접 비교할 baseline 2~3개를 정하거나, literature search로 후보를 확정하세요.",
                priority=92,
                linked_prior_work_seed=prior_work_seeds[0] if prior_work_seeds else None,
                grounding_titles=[],
            )
        )
    if not _contains_numeric(registry.confirmed_results):
        suggestions.append(
            MissingEvidenceSuggestion(
                code="missing-numeric-results",
                title="결과 수치가 더 필요함",
                rationale="현재 결과는 정성적이라 strong claim을 지지하기 어렵습니다.",
                suggested_action="metric 값, 비교 폭, 표 형태 결과를 추가하세요.",
                priority=96,
                grounding_titles=[],
            )
        )
    if not registry.figure_preferences:
        suggestions.append(
            MissingEvidenceSuggestion(
                code="missing-figure-story",
                title="figure/table story가 아직 약함",
                rationale="논문 메시지를 빠르게 전달할 핵심 시각화가 정해지지 않았습니다.",
                suggested_action="시스템 개요, main result, ablation, qualitative example 중 우선순위를 정하세요.",
                priority=60,
                grounding_titles=[],
            )
        )
    if len(registry.experiments) <= 1:
        suggestions.append(
            MissingEvidenceSuggestion(
                code="missing-variation",
                title="실험 변주가 부족할 수 있음",
                rationale="한 종류의 실험만 있으면 해석 방향이 약해질 수 있습니다.",
                suggested_action="ablation, alternate setting, failure case, robustness check 중 하나를 고려하세요.",
                priority=55,
                grounding_titles=[],
            )
        )
    return [item.to_dict() for item in sorted(suggestions, key=lambda item: (-item.priority, item.code))]


def build_claim_candidates(
    answers: dict[str, Any],
    registry: EvidenceRegistry,
    prior_work_seeds: list[str],
    missing_suggestions: list[dict[str, Any]],
    prior_work_candidates: list[dict[str, Any]] | None = None,
) -> list[ClaimCandidate]:
    caveat_titles = [item["title"] for item in missing_suggestions[:3]]
    grounding_titles = [item["title"] for item in (prior_work_candidates or [])[:3]]
    candidates: list[ClaimCandidate] = []
    if registry.baselines and _contains_numeric(registry.confirmed_results):
        candidates.append(
            ClaimCandidate(
                candidate_id="claim-comparative",
                text="현재 결과는 제안 방법이 선택된 baseline 대비 유의미한 개선 가능성을 보인다는 비교 중심 서사를 뒷받침할 수 있다.",
                basis=registry.confirmed_results[:3] + registry.baselines[:2],
                caveats=caveat_titles or ["비교 조건과 데이터셋을 더 명확히 확인해야 합니다."],
                grounding_titles=grounding_titles,
            )
        )
    candidates.append(
        ClaimCandidate(
            candidate_id="claim-method",
            text="현재 실험은 제안한 방법론이 특정 조건에서 작동 가능하고 추가 검증할 가치가 있다는 방법론 중심 서사를 뒷받침할 수 있다.",
            basis=[registry.methodology] + registry.confirmed_results[:2],
            caveats=caveat_titles or ["해석 방향은 사용자 확인이 필요합니다."],
            grounding_titles=grounding_titles,
        )
    )
    if missing_suggestions:
        candidates.append(
            ClaimCandidate(
                candidate_id="claim-gap",
                text="현재 증거는 강한 superiority claim보다는 '어떤 조건에서 효과가 나타나는지 탐색하는 논문' 방향이 더 안전하다는 보수적 claim을 뒷받침한다.",
                basis=[item["title"] for item in missing_suggestions[:2]] or prior_work_seeds[:2],
                caveats=["추가 prior work 조사 후 stronger claim 후보를 다시 제안할 수 있습니다."],
                grounding_titles=grounding_titles,
            )
        )
    return [item.to_dict() for item in candidates]


def build_story_candidates(
    answers: dict[str, Any],
    registry: EvidenceRegistry,
    claim_candidates: list[dict[str, Any]],
    missing_suggestions: list[dict[str, Any]],
    prior_work_seeds: list[str],
    prior_work_candidates: list[dict[str, Any]] | None = None,
) -> list[StoryCandidate]:
    candidates: list[StoryCandidate] = []
    claim_ids = [item["candidate_id"] for item in claim_candidates]
    grounding_titles = [item["title"] for item in (prior_work_candidates or [])[:3]]
    candidates.append(
        StoryCandidate(
            candidate_id="story-method-centric",
            label="Method-centric framing",
            thesis="제안 방법의 설계와 왜 이 설계가 필요한지를 중심으로 논문을 전개한다.",
            narrative="문제 정의 → 방법 핵심 아이디어 → 실험 결과로 이어지는 전형적인 방법론 중심 서사입니다.",
            supporting_points=[registry.methodology] + registry.confirmed_results[:2],
            interpretation_direction="방법의 설계 선택이 어떤 장점을 주는지 설명하는 방향",
            recommended_figure_story=(registry.figure_preferences[0] if registry.figure_preferences else "시스템 개요 + 메인 결과"),
            linked_claim_ids=claim_ids[:2],
            risks=[item["title"] for item in missing_suggestions[:2]],
            grounding_titles=grounding_titles,
        )
    )
    candidates.append(
        StoryCandidate(
            candidate_id="story-evidence-centric",
            label="Evidence-centric framing",
            thesis="관측된 결과 패턴과 비교 관찰을 중심으로, 어떤 조건에서 효과가 나타나는지를 강조한다.",
            narrative="실험 설정 → 핵심 결과 → prior work 대비 해석 → 한계와 추가 검증 필요성을 잇는 보수적 empirical story입니다.",
            supporting_points=registry.confirmed_results[:3] + registry.baselines[:2],
            interpretation_direction="결과 패턴과 비교 프레이밍을 중심으로 해석하는 방향",
            recommended_figure_story=(registry.figure_preferences[0] if registry.figure_preferences else "메인 결과 표 + qualitative example"),
            linked_claim_ids=claim_ids,
            risks=[item["title"] for item in missing_suggestions[:3]],
            grounding_titles=grounding_titles,
        )
    )
    if missing_suggestions:
        candidates.append(
            StoryCandidate(
                candidate_id="story-gap-centric",
                label="Gap-driven framing",
                thesis="현재 결과를 바탕으로 무엇이 가능하고 무엇이 아직 부족한지를 prior work와 연결해 설명한다.",
                narrative="현 상태의 증거를 정직하게 요약하고, 어떤 추가 실험/비교가 있으면 더 강한 claim으로 발전할 수 있는지 제안하는 research-gap story입니다.",
                supporting_points=[item["title"] for item in missing_suggestions[:3]] + prior_work_seeds[:2],
                interpretation_direction="증거의 한계와 다음 claim 후보를 함께 제시하는 방향",
                recommended_figure_story=(registry.figure_preferences[0] if registry.figure_preferences else "gap table + next-step figure"),
                linked_claim_ids=claim_ids,
                risks=["추가 실험 없이 과한 claim으로 비칠 수 있으므로 사용자 확인이 필요합니다."],
                grounding_titles=grounding_titles,
            )
        )
    return [item.to_dict() for item in candidates]


def summarize_story_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": candidate["candidate_id"],
        "label": candidate["label"],
        "thesis": candidate["thesis"],
        "interpretation_direction": candidate["interpretation_direction"],
        "linked_claim_ids": candidate.get("linked_claim_ids", []),
        "risks": candidate.get("risks", []),
        "grounding_titles": candidate.get("grounding_titles", []),
    }


def build_review_summary(
    registry: EvidenceRegistry,
    story_candidates: list[dict[str, Any]],
    claim_candidates: list[dict[str, Any]],
    missing_suggestions: list[dict[str, Any]],
    prior_work_candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "methodology": registry.methodology,
        "confirmed_results_count": len(registry.confirmed_results),
        "story_candidates": [summarize_story_candidate(item) for item in story_candidates],
        "claim_candidates": claim_candidates,
        "missing_evidence_suggestions": missing_suggestions,
        "prior_work_candidates": prior_work_candidates or [],
    }


def render_idea_from_selection(
    answers: dict[str, Any],
    selected_story: dict[str, Any] | None,
    selected_claims: list[dict[str, Any]],
) -> str:
    problem_statement = _textify(answers.get("problem_statement")) or "실험에서 드러난 문제와 동기를 review 단계에서 정제해야 합니다."
    method_summary = _textify(answers.get("method_summary")) or _textify(answers.get("experiments_ran")) or "unknown"
    contributions = _normalize_list(answers.get("core_contributions"))
    if not contributions:
        contributions = [item["text"] for item in selected_claims] or ["[REVIEW REQUIRED] contribution claim selection pending"]
    story_thesis = selected_story["thesis"] if selected_story else "User review is required before a final story direction is locked in."
    lines = [
        "# Idea Summary",
        "",
        "## Problem Statement",
        problem_statement,
        "",
        "## Method Summary",
        method_summary,
        "",
        "## Story Thesis",
        story_thesis,
        "",
        "## Core Contributions",
    ]
    lines.extend(f"- {item}" for item in contributions)
    lines.extend(["", "## Target User / Setting", _textify(answers.get("target_user_or_setting")) or "unknown", ""])
    return "\n".join(lines)


def render_experimental_log_from_registry(
    registry: EvidenceRegistry | dict[str, Any],
    answers: dict[str, Any],
    missing_suggestions: list[dict[str, Any]],
) -> str:
    if isinstance(registry, dict):
        registry = EvidenceRegistry(**registry)
    lines = [
        "# Experimental Log",
        "",
        "## 1. Experimental Setup",
        "",
        f"* **Methodology:** {registry.methodology}",
        f"* **Datasets / Benchmarks:** {', '.join(registry.datasets) if registry.datasets else 'unknown'}",
        f"* **Baselines:** {', '.join(registry.baselines) if registry.baselines else 'unknown'}",
        "",
        "## 2. Experiments Run",
        "",
    ]
    lines.extend(f"- {item}" for item in (registry.experiments or ["unknown"]))
    lines.extend(["", "## 3. Confirmed Results", ""])
    lines.extend(f"- {item}" for item in (registry.confirmed_results or ["unknown"]))
    lines.extend(["", "## 4. Suggested Figure / Table Story", ""])
    lines.extend(f"- {item}" for item in (registry.figure_preferences or ["unknown"]))
    lines.extend(["", "## 5. Missing Evidence Suggestions", ""])
    lines.extend(f"- {item['title']}: {item['suggested_action']}" for item in missing_suggestions) if missing_suggestions else lines.append("- none")
    if registry.open_questions:
        lines.extend(["", "## 6. Open Questions", ""])
        lines.extend(f"- {item}" for item in registry.open_questions)
    return "\n".join(lines) + "\n"


def aggregate_intake(
    cwd: str | Path | None,
    *,
    answers: dict[str, Any],
    output_dir: str | Path,
    allow_outside_workspace: bool = False,
) -> dict[str, Any]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    evidence_paths = normalize_evidence_paths(answers.get("evidence_paths"))
    discovered_sources, warnings = discover_supporting_sources_with_warnings(cwd, evidence_paths, allow_outside_workspace=allow_outside_workspace)
    registry = build_evidence_registry(answers, discovered_sources)
    prior_work_seeds = build_prior_work_seeds(answers, registry)
    missing_suggestions = build_missing_evidence_suggestions(answers, registry, prior_work_seeds)
    claim_candidates = build_claim_candidates(answers, registry, prior_work_seeds, missing_suggestions)
    story_candidates = build_story_candidates(answers, registry, claim_candidates, missing_suggestions, prior_work_seeds)

    paths = {
        "evidence_registry_path": str(destination / "evidence_registry.json"),
        "source_inventory_path": str(destination / "source_inventory.json"),
        "story_candidates_path": str(destination / "story_candidates.json"),
        "claim_candidates_path": str(destination / "claim_candidates.json"),
        "missing_evidence_suggestions_path": str(destination / "missing_evidence_suggestions.json"),
        "prior_work_seeds_path": str(destination / "prior_work_seeds.json"),
        "prior_work_candidates_path": str(destination / "prior_work_candidates.json"),
        "grounded_gap_suggestions_path": str(destination / "grounded_gap_suggestions.json"),
        "review_summary_path": str(destination / "review_summary.json"),
        "warnings_path": str(destination / "warnings.json"),
    }
    write_json(paths["evidence_registry_path"], registry.to_dict())
    write_json(paths["source_inventory_path"], {"sources": discovered_sources})
    write_json(paths["story_candidates_path"], story_candidates)
    write_json(paths["claim_candidates_path"], claim_candidates)
    write_json(paths["missing_evidence_suggestions_path"], missing_suggestions)
    write_json(paths["prior_work_seeds_path"], {"queries": prior_work_seeds})
    write_json(paths["prior_work_candidates_path"], [])
    write_json(paths["grounded_gap_suggestions_path"], missing_suggestions)
    write_json(paths["review_summary_path"], build_review_summary(registry, story_candidates, claim_candidates, missing_suggestions))
    write_json(paths["warnings_path"], {"warnings": warnings})

    return {
        "evidence_registry": registry.to_dict(),
        "discovered_sources": discovered_sources,
        "story_candidates": story_candidates,
        "claim_candidates": claim_candidates,
        "missing_evidence_suggestions": missing_suggestions,
        "prior_work_seeds": prior_work_seeds,
        "warnings": warnings,
        "artifact_paths": paths,
    }


def search_prior_work_candidates(
    prior_work_seeds: list[str],
    *,
    mode: str = "live",
    max_per_seed: int = 2,
    cutoff_date: str | None = None,
) -> list[dict[str, Any]]:
    candidates: list[PriorWorkCandidate] = []
    seen_titles: set[str] = set()
    for seed in prior_work_seeds:
        if mode == "mock":
            mock = mock_verified_paper(
                f"{seed} Prior Work",
                abstract_hint=f"Mock prior work candidate for query: {seed}",
                cutoff_date=cutoff_date,
                query_hint=seed,
            )
            title_key = normalize_title(mock.title)
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)
            candidates.append(
                PriorWorkCandidate(
                    paper_id=mock.paper_id,
                    title=mock.title,
                    year=mock.year,
                    venue=mock.venue,
                    abstract=mock.abstract,
                    matched_query=seed,
                    url=mock.url,
                )
            )
            continue
        try:
            results = search_semantic_scholar(seed, limit=max_per_seed)
        except SemanticScholarError:
            continue
        for item in results:
            title = item.get("title", "").strip()
            title_key = normalize_title(title)
            if not title or title_key in seen_titles:
                continue
            seen_titles.add(title_key)
            candidates.append(
                PriorWorkCandidate(
                    paper_id=item.get("paperId", f"seed-{len(candidates)+1}"),
                    title=title,
                    year=item.get("year"),
                    venue=item.get("venue"),
                    abstract=item.get("abstract") or "",
                    matched_query=seed,
                    url=item.get("url"),
                )
            )
    return [item.to_dict() for item in candidates]


def build_grounded_gap_suggestions(
    registry: EvidenceRegistry,
    prior_work_candidates: list[dict[str, Any]],
    existing_suggestions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    top_titles = [item["title"] for item in prior_work_candidates[:3]]
    grounded: list[dict[str, Any]] = []
    for suggestion in existing_suggestions:
        enriched = dict(suggestion)
        if not enriched.get("grounding_titles"):
            enriched["grounding_titles"] = top_titles
        rationale = enriched.get("rationale", "")
        if top_titles:
            rationale = f"{rationale} 관련 prior work 예시: " + ", ".join(top_titles[:2]) + "."
        enriched["rationale"] = rationale.strip()
        grounded.append(enriched)
    if prior_work_candidates and not registry.baselines:
        grounded.append(
            MissingEvidenceSuggestion(
                code="prior-work-baseline-alignment",
                title="선행연구 기준 비교 실험이 더 필요함",
                rationale=f"검색된 prior work ({', '.join(top_titles[:2])})와 직접 비교할 baseline 정렬이 아직 약합니다.",
                suggested_action="검색된 prior work 중 1~2개를 baseline 후보로 채택해 직접 비교 표를 준비하세요.",
                priority=97,
                linked_prior_work_seed=prior_work_candidates[0]["matched_query"],
                grounding_titles=top_titles,
            ).to_dict()
        )
    if prior_work_candidates and len(registry.experiments) <= 1:
        grounded.append(
            MissingEvidenceSuggestion(
                code="prior-work-ablation-gap",
                title="선행연구 대비 추가 실험이 필요할 수 있음",
                rationale=f"검색된 prior work ({', '.join(top_titles[:2])})와 비교했을 때, 현재는 variation/ablation evidence가 부족합니다.",
                suggested_action="가장 핵심 구성요소를 제거/변형한 ablation 또는 robustness 실험을 추가하는 것을 고려하세요.",
                priority=88,
                linked_prior_work_seed=prior_work_candidates[0]["matched_query"],
                grounding_titles=top_titles,
            ).to_dict()
        )
    grounded.sort(key=lambda item: (-int(item.get("priority", 0)), item.get("code", "")))
    deduped: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for item in grounded:
        code = item.get("code", "")
        if code in seen_codes:
            continue
        seen_codes.add(code)
        deduped.append(item)
    return deduped


def enrich_with_prior_work(
    cwd: str | Path | None,
    *,
    answers: dict[str, Any],
    output_dir: str | Path,
    mode: str = "live",
    allow_outside_workspace: bool = False,
    max_per_seed: int = 2,
) -> dict[str, Any]:
    payload = aggregate_intake(cwd, answers=answers, output_dir=output_dir, allow_outside_workspace=allow_outside_workspace)
    registry = EvidenceRegistry(**payload["evidence_registry"])
    prior_work_candidates = search_prior_work_candidates(
        payload["prior_work_seeds"],
        mode=mode,
        max_per_seed=max_per_seed,
        cutoff_date=answers.get("cutoff_date"),
    )
    grounded_suggestions = build_grounded_gap_suggestions(registry, prior_work_candidates, payload["missing_evidence_suggestions"])
    claim_candidates = build_claim_candidates(
        answers,
        registry,
        payload["prior_work_seeds"],
        grounded_suggestions,
        prior_work_candidates=prior_work_candidates,
    )
    story_candidates = build_story_candidates(
        answers,
        registry,
        claim_candidates,
        grounded_suggestions,
        payload["prior_work_seeds"],
        prior_work_candidates=prior_work_candidates,
    )
    paths = payload["artifact_paths"]
    write_json(paths["prior_work_candidates_path"], prior_work_candidates)
    write_json(paths["grounded_gap_suggestions_path"], grounded_suggestions)
    write_json(paths["claim_candidates_path"], claim_candidates)
    write_json(paths["story_candidates_path"], story_candidates)
    write_json(paths["missing_evidence_suggestions_path"], grounded_suggestions)
    write_json(paths["review_summary_path"], build_review_summary(registry, story_candidates, claim_candidates, grounded_suggestions, prior_work_candidates))
    payload["prior_work_candidates"] = prior_work_candidates
    payload["grounded_gap_suggestions"] = grounded_suggestions
    payload["claim_candidates"] = claim_candidates
    payload["story_candidates"] = story_candidates
    payload["missing_evidence_suggestions"] = grounded_suggestions
    return payload
