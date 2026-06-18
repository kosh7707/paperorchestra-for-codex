from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from paperorchestra.runtime.provider_base import BaseProvider


@dataclass
class SectionWritingRun:
    cwd: str | Path | None
    provider: BaseProvider
    stage: Any
    runtime_mode: str = "compatibility"
    only_sections: list[str] | str | None = None
    output_path: str | Path | None = None
    claim_safe: bool = False
    state: Any = field(init=False)
    plan: Any = field(init=False)
    latex: str = field(init=False)
    validation_issues: list[Any] = field(init=False, default_factory=list)
    blocking_issues: list[Any] = field(init=False, default_factory=list)
    lane_notes: list[str] = field(init=False, default_factory=list)
    lane_type: str = field(init=False)
    fallback_used: bool = field(init=False)

    def run(self) -> Path:
        self._load_state_and_plan()
        self._complete_initial_draft()
        self._record_provider_metadata()
        self._repair_and_validate()
        validation_path = self._record_validation_report()
        self._raise_if_blocked()
        path = self._write_paper()
        self._record_lane_and_session(path, validation_path)
        return path

    def _load_state_and_plan(self) -> None:
        self.state = self.stage.load_session(self.cwd)
        if not self.state.artifacts.outline_json:
            raise self.stage.ContractError("Need outline.json before write-sections.")
        selected_sections = self.stage._normalize_section_selection(self.only_sections)
        self.plan = self.stage.build_section_writing_plan(
            self.cwd,
            self.state,
            selected_sections=selected_sections,
            claim_safe=self.claim_safe,
        )

    def _complete_initial_draft(self) -> None:
        response, self.lane_type, self.fallback_used, self.lane_notes = self.stage._complete_with_runtime_mode(
            self.stage._build_completion_request(
                system_prompt=self.stage.PROMPTS.render_section_writer_system(),
                user_prompt=self.plan.user_prompt,
            ),
            provider=self.provider,
            runtime_mode=self.runtime_mode,
            cwd=self.cwd,
            omx_lane_type="ralph",
            trace_stage="section_writing",
        )
        self.latex = self.stage.extract_latex(response)
        self.latex, self.citation_replacements, self.dropped_citations = self.stage.normalize_section_draft(
            self.latex,
            self.plan.draft_context,
        )

    def _record_provider_metadata(self) -> None:
        self.state.latest_provider_name = self.stage._provider_name(self.provider)
        self.state.latest_runtime_mode = self.runtime_mode
        self.stage.save_session(self.cwd, self.state)
        self.latex = self.stage._apply_mock_watermark(
            self.latex,
            self.state,
            provider_name=self.stage._provider_name(self.provider),
        )

    def _repair_and_validate(self) -> None:
        self.validation_issues = self.stage.validate_section_draft(self.latex, self.plan.validation_context)
        self.blocking_issues = self.stage._blocking_issues(self.validation_issues)
        repair = self.stage.repair_section_draft_if_possible(
            cwd=self.cwd,
            provider=self.provider,
            runtime_mode=self.runtime_mode,
            user_prompt=self.plan.user_prompt,
            latex=self.latex,
            validation_issues=self.validation_issues,
            blocking_issues=self.blocking_issues,
            draft_context=self.plan.draft_context,
            validation_context=self.plan.validation_context,
            min_citation_coverage=self.plan.min_citation_coverage,
            citation_map=self.plan.citation_map,
            plot_assets_index=self.plan.plot_assets_index,
            selected_sections=self.plan.selected_sections,
            strict_claim_safe_prompt=self.plan.strict_claim_safe_prompt,
            citation_replacements=self.citation_replacements,
            dropped_citations=self.dropped_citations,
            lane_notes=self.lane_notes,
            lane_type=self.lane_type,
            fallback_used=self.fallback_used,
        )
        self.latex = repair.latex
        self.validation_issues = repair.validation_issues
        self.blocking_issues = repair.blocking_issues
        self.lane_notes = repair.lane_notes
        self.lane_type = repair.lane_type
        self.fallback_used = repair.fallback_used

    def _record_validation_report(self) -> Path:
        validation_path, _ = self.stage._record_validation_report(
            self.cwd,
            stage="section_writing",
            issues=self.validation_issues,
            name="validation.sections.json",
            manuscript_text=self.latex,
        )
        self.state.artifacts.latest_validation_json = str(validation_path)
        if self.validation_issues:
            self.state.notes.append(
                "Section writer validation warnings: " + " | ".join(self.stage._issue_messages(self.validation_issues))
            )
        self.state.notes.append(f"Validation report recorded: {validation_path.name}")
        return validation_path

    def _raise_if_blocked(self) -> None:
        if not self.blocking_issues:
            return
        raise self.stage.ContractError(
            "Section writer produced invalid paper contract:\n- "
            + "\n- ".join(self.stage._issue_messages(self.blocking_issues))
        )

    def _write_paper(self) -> Path:
        path = Path(self.output_path).resolve() if self.output_path else self.stage.artifact_path(self.cwd, "paper.full.tex")
        self.stage.write_text(path, self.latex)
        return path

    def _record_lane_and_session(self, path: Path, validation_path: Path) -> None:
        lane_path = self.stage.record_lane_manifest(
            self.cwd,
            stage="section_writing",
            role="Section Writing Agent",
            runtime_mode=self.runtime_mode,
            lane_type=self.lane_type,
            owner=self.stage._lane_owner(self.lane_type, self.fallback_used),
            status="fallback_completed" if self.fallback_used else "completed",
            input_artifacts=[
                self.state.artifacts.outline_json or "",
                self.state.artifacts.citation_map_json or "",
                self.state.artifacts.plot_assets_json or "",
            ],
            output_artifacts=[str(path), str(validation_path)],
            fallback_used=self.fallback_used,
            notes=self.lane_notes
            + (
                [f"Section-scoped rewrite requested for: {', '.join(self.plan.selected_sections)}"]
                if self.plan.selected_sections
                else []
            ),
        )
        self.state.artifacts.paper_full_tex = str(path)
        self.state.current_phase = "iterative_content_refinement"
        self.state.active_artifact = "paper.full.tex"
        self.state.notes.append("Full paper draft generated.")
        self.state.notes.append(f"Lane manifest recorded: {lane_path.name}")
        self.stage.save_session(self.cwd, self.state)


__all__ = ["SectionWritingRun"]
