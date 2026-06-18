from __future__ import annotations

from pathlib import Path

from paperorchestra.core.io import read_json
from paperorchestra.core.models import SessionState
from paperorchestra.reviews.fidelity_types import FidelityCheck
from paperorchestra.reviews.reproducibility_artifacts import _file_sha256


def _submission_output_check(state: SessionState) -> FidelityCheck:
    submission_status = "partial"
    if state.artifacts.latest_compile_report_json and Path(state.artifacts.latest_compile_report_json).exists():
        compile_report = read_json(state.artifacts.latest_compile_report_json)
        current_manuscript_sha = _file_sha256(state.artifacts.paper_full_tex)
        current_pdf_sha = _file_sha256(compile_report.get("pdf_path"))
        compile_report_current = (
            bool(current_manuscript_sha)
            and compile_report.get("manuscript_sha256") == current_manuscript_sha
            and bool(current_pdf_sha)
            and (not compile_report.get("pdf_sha256") or compile_report.get("pdf_sha256") == current_pdf_sha)
        )
        if compile_report.get("clean") and compile_report.get("pdf_exists") and compile_report_current:
            submission_status = "implemented"
        elif compile_report.get("pdf_exists"):
            submission_status = "partial"
    elif state.artifacts.compiled_pdf:
        submission_status = "implemented"
    return FidelityCheck(
        code="submission_ready_output",
        status=submission_status,
        rationale="The paper's final output is a LaTeX manuscript plus compiled PDF; draft-only output is partial fidelity.",
    )


def _compile_environment_check(state: SessionState) -> FidelityCheck:
    compile_env_status = "missing"
    if state.artifacts.latest_compile_env_json and Path(state.artifacts.latest_compile_env_json).exists():
        compile_env_payload = read_json(state.artifacts.latest_compile_env_json)
        compile_env_status = "implemented" if compile_env_payload.get("ready_for_compile") else "partial"
    return FidelityCheck(
        code="compile_environment_ready",
        status=compile_env_status,
        rationale="Submission-ready output requires both a TeX engine and a sandboxed compile wrapper path.",
    )


def _runtime_parity_check(state: SessionState) -> FidelityCheck:
    runtime_parity_status = "missing"
    if state.artifacts.latest_runtime_parity_json and Path(state.artifacts.latest_runtime_parity_json).exists():
        runtime_parity_payload = read_json(state.artifacts.latest_runtime_parity_json)
        runtime_parity_status = runtime_parity_payload.get("overall_status", "partial")
    return FidelityCheck(
        code="runtime_parity",
        status=runtime_parity_status,
        rationale="A true multi-agent implementation should preserve OMX lane evidence for each paper agent stage.",
    )
