from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class InputBundle:
    idea_path: str
    experimental_log_path: str
    template_path: str
    guidelines_path: str
    figures_dir: str | None = None
    cutoff_date: str | None = None
    venue: str | None = None
    page_limit: int | None = None


@dataclass
class ArtifactIndex:
    outline_json: str | None = None
    plot_manifest_json: str | None = None
    plot_captions_json: str | None = None
    plot_assets_json: str | None = None
    plot_assets_dir: str | None = None
    candidate_papers_json: str | None = None
    citation_registry_json: str | None = None
    citation_map_json: str | None = None
    references_bib: str | None = None
    intro_related_tex: str | None = None
    paper_full_tex: str | None = None
    compiled_pdf: str | None = None
    latest_review_json: str | None = None
    latest_validation_json: str | None = None
    latest_fidelity_json: str | None = None
    latest_compile_env_json: str | None = None
    latest_compile_report_json: str | None = None
    latest_runtime_parity_json: str | None = None
    latest_verification_errors_json: str | None = None
    latest_prompt_trace_dir: str | None = None
    latest_lane_summary_json: str | None = None
    latest_reproducibility_json: str | None = None
    latest_provider_identity_json: str | None = None
    latest_figure_placement_review_json: str | None = None
    latest_section_review_json: str | None = None
    narrative_plan_json: str | None = None
    claim_map_json: str | None = None
    citation_placement_plan_json: str | None = None
    source_obligations_json: str | None = None


@dataclass
class ScoreSnapshot:
    overall_score: float
    raw_path: str
    axes: dict[str, float] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)


@dataclass
class SessionState:
    session_id: str
    created_at: str
    updated_at: str
    current_phase: str
    active_artifact: str | None
    inputs: InputBundle
    artifacts: ArtifactIndex = field(default_factory=ArtifactIndex)
    refinement_iteration: int = 0
    review_history: list[ScoreSnapshot] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    notes_archive: list[str] = field(default_factory=list)
    latest_discovery_mode: str | None = None
    latest_provider_name: str | None = None
    latest_runtime_mode: str | None = None
    latest_verify_mode: str | None = None
    latest_verify_fallback_used: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionState":
        inputs = InputBundle(**data["inputs"])
        artifacts = ArtifactIndex(**data.get("artifacts", {}))
        history = [ScoreSnapshot(**item) for item in data.get("review_history", [])]
        return cls(
            session_id=data["session_id"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            current_phase=data["current_phase"],
            active_artifact=data.get("active_artifact"),
            inputs=inputs,
            artifacts=artifacts,
            refinement_iteration=data.get("refinement_iteration", 0),
            review_history=history,
            notes=data.get("notes", []),
            notes_archive=data.get("notes_archive", []),
            latest_discovery_mode=data.get("latest_discovery_mode"),
            latest_provider_name=data.get("latest_provider_name"),
            latest_runtime_mode=data.get("latest_runtime_mode"),
            latest_verify_mode=data.get("latest_verify_mode"),
            latest_verify_fallback_used=data.get("latest_verify_fallback_used"),
        )


@dataclass
class VerifiedPaper:
    paper_id: str
    title: str
    year: int | None
    publication_date: str | None
    venue: str | None
    abstract: str
    authors: list[str]
    citation_count: int | None
    external_ids: dict[str, str] = field(default_factory=dict)
    url: str | None = None
    bibtex_key: str | None = None
    alias_bibtex_keys: list[str] = field(default_factory=list)
    origin: str | None = None
    matched_query: str | None = None
    title_match_ratio: float | None = None
    is_after_cutoff: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvidenceRegistry:
    methodology: str
    confirmed_results: list[str]
    experiments: list[str] = field(default_factory=list)
    datasets: list[str] = field(default_factory=list)
    baselines: list[str] = field(default_factory=list)
    figure_preferences: list[str] = field(default_factory=list)
    discovered_sources: list[dict[str, Any]] = field(default_factory=list)
    supporting_quotes: list[str] = field(default_factory=list)
    confidence_notes: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StoryCandidate:
    candidate_id: str
    label: str
    thesis: str
    narrative: str
    supporting_points: list[str] = field(default_factory=list)
    interpretation_direction: str = ""
    recommended_figure_story: str = ""
    linked_claim_ids: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    grounding_titles: list[str] = field(default_factory=list)
    requires_user_confirmation: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ClaimCandidate:
    candidate_id: str
    text: str
    basis: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    grounding_titles: list[str] = field(default_factory=list)
    requires_user_confirmation: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PriorWorkCandidate:
    paper_id: str
    title: str
    year: int | None
    venue: str | None
    abstract: str
    matched_query: str
    url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MissingEvidenceSuggestion:
    code: str
    title: str
    rationale: str
    suggested_action: str
    priority: int = 50
    linked_prior_work_seed: str | None = None
    grounding_titles: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
