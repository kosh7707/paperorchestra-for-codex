from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.runtime.provider_base import BaseProvider


@dataclass
class PipelineRun:
    cwd: str | Path | None
    provider: BaseProvider
    stage: Any
    discovery_mode: str = "model"
    verify_mode: str = "live"
    verify_error_policy: str = "skip"
    verify_fallback_mode: str = "none"
    require_live_verification: bool = False
    refine_iterations: int = 1
    compile_paper: bool = False
    runtime_mode: str = "compatibility"
    outputs: dict[str, Any] = field(default_factory=lambda: {"validation_reports": {}})

    def run(self) -> dict[str, Any]:
        self._validate()
        self._initialize_session_metadata()
        self._record_compile_environment()
        self._generate_outline()
        self._run_parallel_plot_and_literature()
        self._verify_and_build_bib()
        self._plan_narrative()
        self._write_draft_sections()
        self._compile_if_requested()
        self._review_and_refine()
        self._finalize_phase()
        self._write_final_reports()
        return self.outputs

    def _validate(self) -> None:
        if self.verify_fallback_mode not in {"none", "mock"}:
            raise ContractError(f"Unsupported verify fallback mode: {self.verify_fallback_mode}")

    def _initialize_session_metadata(self) -> None:
        state = self.stage.load_session(self.cwd)
        state.latest_provider_name = self.stage._provider_name(self.provider)
        state.latest_runtime_mode = self.runtime_mode
        state.latest_verify_mode = self.verify_mode
        state.latest_verify_fallback_used = None
        self.stage.save_session(self.cwd, state)
        self.outputs["runtime_mode"] = self.runtime_mode

    def _record_compile_environment(self) -> None:
        self._emit("compile_environment", "started")
        path, payload = self.stage.record_compile_environment_report(self.cwd)
        self._emit("compile_environment", "completed", path=str(path))
        self.outputs["compile_environment"] = str(path)
        self.outputs["compile_environment_report"] = payload

    def _generate_outline(self) -> None:
        self._emit("outline", "started")
        self.outputs["outline"] = str(
            self.stage.generate_outline(self.cwd, self.provider, runtime_mode=self.runtime_mode)
        )
        self._emit("outline", "completed", path=self.outputs["outline"])

    def _run_parallel_plot_and_literature(self) -> None:
        self._emit("parallel_plot_literature", "started", discovery_mode=self.discovery_mode)
        parallel_outputs = self.stage.run_parallel_plot_and_literature(
            self.cwd,
            provider=self.provider,
            discovery_mode=self.discovery_mode,
            runtime_mode=self.runtime_mode,
        )
        self._emit(
            "parallel_plot_literature",
            "completed",
            candidates=parallel_outputs["candidates"],
            plots=parallel_outputs["plots"],
        )
        self.outputs.update(
            {
                "plots": parallel_outputs["plots"],
                "plot_captions": parallel_outputs["plot_captions"],
                "plot_assets": parallel_outputs["plot_assets"],
                "candidates": parallel_outputs["candidates"],
            }
        )

    def _verify_and_build_bib(self) -> None:
        self._verify_papers()
        self._emit("build_bib", "started")
        self.outputs["bib"] = str(self.stage.build_bib(self.cwd))
        self._emit("build_bib", "completed", path=self.outputs["bib"])

    def _verify_papers(self) -> None:
        try:
            self._emit("verify", "started", mode=self.verify_mode, on_error=self.verify_error_policy)
            self.outputs["verified"] = str(
                self.stage.verify_papers(self.cwd, mode=self.verify_mode, on_error=self.verify_error_policy)
            )
            self._emit("verify", "completed", path=self.outputs["verified"], mode=self.verify_mode)
        except ContractError as exc:
            if self.verify_mode == "live" and self.verify_fallback_mode == "mock":
                self._use_mock_verification_fallback(exc)
                return
            raise

    def _use_mock_verification_fallback(self, exc: ContractError) -> None:
        self.outputs["verify_live_error"] = str(exc)
        self._emit("verify", "fallback", error=str(exc), fallback_mode="mock")
        self.outputs["verified"] = str(self.stage.verify_papers(self.cwd, mode="mock", on_error=self.verify_error_policy))
        self.outputs["verify_fallback_used"] = "mock"
        state = self.stage.load_session(self.cwd)
        state.latest_verify_fallback_used = "mock"
        self.stage.save_session(self.cwd, state)
        self._emit("verify", "completed", path=self.outputs["verified"], mode="mock")

    def _plan_narrative(self) -> None:
        self._emit("narrative_planning", "started")
        narrative_paths = self.stage.plan_narrative_and_claims(self.cwd, self.provider, runtime_mode=self.runtime_mode)
        self.outputs["narrative_plan"] = str(narrative_paths["narrative_plan"])
        self.outputs["claim_map"] = str(narrative_paths["claim_map"])
        self.outputs["citation_placement_plan"] = str(narrative_paths["citation_placement_plan"])
        self._emit("narrative_planning", "completed", path=self.outputs["narrative_plan"])

    def _write_draft_sections(self) -> None:
        self._emit("intro_related", "started")
        self.outputs["intro_related"] = str(
            self.stage.write_intro_related(self.cwd, self.provider, runtime_mode=self.runtime_mode)
        )
        self._emit("intro_related", "completed", path=self.outputs["intro_related"])
        self.outputs["validation_reports"]["intro_related"] = self.stage.load_session(
            self.cwd
        ).artifacts.latest_validation_json

        self._emit("write_sections", "started")
        self.outputs["paper"] = str(self.stage.write_sections(self.cwd, self.provider, runtime_mode=self.runtime_mode))
        self._emit("write_sections", "completed", path=self.outputs["paper"])
        self.outputs["validation_reports"]["section_writing"] = self.stage.load_session(
            self.cwd
        ).artifacts.latest_validation_json

    def _compile_if_requested(self) -> None:
        if not self.compile_paper:
            return
        self._emit("compile", "started")
        self.outputs["compiled_pdf"] = str(self.stage.compile_current_paper(self.cwd))
        self._emit("compile", "completed", path=self.outputs["compiled_pdf"])

    def _review_and_refine(self) -> None:
        self._emit("review", "started")
        self.outputs["review"] = str(self.stage.review_current_paper(self.cwd, self.provider, runtime_mode=self.runtime_mode))
        self._emit("review", "completed", path=self.outputs["review"])

        self._emit("refine", "started", iterations=self.refine_iterations)
        self.outputs["refine"] = self.stage.refine_current_paper(
            self.cwd,
            self.provider,
            iterations=self.refine_iterations,
            require_compile_for_accept=self.compile_paper,
            runtime_mode=self.runtime_mode,
        )
        self.outputs["validation_reports"]["refinement"] = [
            item.get("validation_report_path") for item in self.outputs["refine"] if item.get("validation_report_path")
        ]
        self._emit(
            "refine",
            "completed",
            accepted=sum(1 for item in self.outputs["refine"] if item.get("accepted")),
            total=len(self.outputs["refine"]),
        )

    def _finalize_phase(self) -> None:
        state = self.stage.load_session(self.cwd)
        blocked = (
            self.refine_iterations > 0
            and bool(self.outputs["refine"])
            and not any(item.get("accepted", False) for item in self.outputs["refine"])
        )
        if blocked:
            state.current_phase = "blocked"
            state.notes.append("Pipeline run halted because refinement was rejected.")
            self.outputs["status"] = "blocked"
        elif self.compile_paper and state.artifacts.compiled_pdf:
            state.current_phase = "complete"
            state.notes.append("Pipeline run completed with compiled output.")
            self.outputs["status"] = "complete"
        else:
            state.current_phase = "draft_complete"
            state.notes.append("Pipeline run completed at draft stage without compiled output.")
            self.outputs["status"] = "draft_complete"
        self.stage.save_session(self.cwd, state)

    def _write_final_reports(self) -> None:
        runtime_parity_path, runtime_parity_payload = self.stage.record_runtime_parity_report(self.cwd)
        state = self.stage.load_session(self.cwd)
        state.artifacts.latest_runtime_parity_json = str(runtime_parity_path)
        self.stage.save_session(self.cwd, state)
        self.outputs["runtime_parity_report"] = str(runtime_parity_path)
        self.outputs["runtime_parity"] = runtime_parity_payload

        fidelity_path, fidelity_payload = self.stage.record_fidelity_report(self.cwd)
        self.outputs["fidelity_report"] = str(fidelity_path)
        self.outputs["fidelity"] = fidelity_payload

        if self.stage.load_session(self.cwd).artifacts.paper_full_tex:
            figure_review_path, figure_review_payload = self.stage.write_figure_placement_review(self.cwd)
            self.outputs["figure_placement_review"] = str(figure_review_path)
            self.outputs["figure_placement"] = figure_review_payload

        reproducibility_path, reproducibility_payload = self.stage.write_reproducibility_audit(
            self.cwd,
            require_live_verification=self.require_live_verification,
        )
        self.outputs["reproducibility_report"] = str(reproducibility_path)
        self.outputs["reproducibility"] = reproducibility_payload
        self._emit(
            "pipeline",
            "completed",
            status=self.outputs.get("status"),
            reproducibility_verdict=reproducibility_payload.get("verdict"),
        )

    def _emit(self, stage: str, event: str, **payload: Any) -> None:
        self.stage._emit_stage_event(stage, event, **payload)


__all__ = ["PipelineRun"]
