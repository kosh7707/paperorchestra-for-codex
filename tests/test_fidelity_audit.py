from __future__ import annotations

import hashlib
import json
from pathlib import Path

from paperorchestra.core.models import ArtifactIndex, InputBundle, SessionState
from paperorchestra.core.session import save_session, set_current_session
from paperorchestra.reviews.fidelity import run_fidelity_audit


EXPECTED_FIDELITY_CHECK_CODES = [
    "paper_source_present",
    "appendix_f_prompt_fidelity_assets",
    "outline_json_contract",
    "parallel_step_2_3_semantics",
    "verified_citation_lane",
    "plot_generation_depth",
    "generated_plot_assets_used_in_manuscript",
    "section_writing_pipeline",
    "iterative_refinement_gate",
    "submission_ready_output",
    "compile_environment_ready",
    "runtime_parity",
    "agentreview_substitute_surface",
    "review_gate_comparison_surface",
    "search_grounding_substitute_surface",
    "benchmark_eval_surface",
    "generated_citation_title_surface",
    "citation_partition_scaffold_surface",
]

def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _save_current_session(tmp_path: Path, artifacts: ArtifactIndex | None = None) -> None:
    state = SessionState(
        session_id="session-1",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        current_phase="test",
        active_artifact=None,
        inputs=InputBundle(
            idea_path="idea.md",
            experimental_log_path="experimental.md",
            template_path="template.tex",
            guidelines_path="guidelines.md",
        ),
        artifacts=artifacts or ArtifactIndex(),
    )
    save_session(tmp_path, state)
    set_current_session(tmp_path, state.session_id)


def test_fidelity_audit_empty_session_preserves_contract(tmp_path: Path) -> None:
    _save_current_session(tmp_path)

    payload = run_fidelity_audit(tmp_path)

    assert payload["session_id"] == "session-1"
    assert payload["overall_status"] == "partial"
    assert payload["summary_descriptor"] == "partial"
    assert payload["status_histogram"] == {"missing": 15, "partial": 3, "implemented": 0}
    assert [check["code"] for check in payload["checks"]] == EXPECTED_FIDELITY_CHECK_CODES
    assert payload["checks"][-1]["next_step"] == (
        "Run `paperorchestra quality-gate --no-fail-on-block` after adding partitioned coverage evidence to the session artifacts."
    )


def test_fidelity_audit_recognizes_file_based_implemented_surfaces(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    paper_tex = artifacts_dir / "paper.tex"
    paper_pdf = artifacts_dir / "paper.pdf"
    paper_tex.parent.mkdir(parents=True, exist_ok=True)
    paper_tex.write_text("Body with fig_a.png and citation \\cite{Key2024}.", encoding="utf-8")
    paper_pdf.write_bytes(b"%PDF")

    outline_json = _write_json(
        artifacts_dir / "outline.json",
        {"plotting_plan": [], "intro_related_work_plan": [], "section_plan": []},
    )
    plot_assets_json = _write_json(artifacts_dir / "plot_assets.json", {"assets": [{"filename": "fig_a.png"}]})
    citation_map_json = _write_json(artifacts_dir / "citation_map.json", {"Key2024": {"title": "Useful Paper"}})
    compile_report_json = _write_json(
        artifacts_dir / "compile.json",
        {
            "clean": True,
            "pdf_exists": True,
            "pdf_path": str(paper_pdf),
            "manuscript_sha256": _sha256(paper_tex),
            "pdf_sha256": _sha256(paper_pdf),
        },
    )
    compile_env_json = _write_json(artifacts_dir / "compile-env.json", {"ready_for_compile": True})
    runtime_parity_json = _write_json(artifacts_dir / "runtime-parity.json", {"overall_status": "implemented"})
    _write_json(artifacts_dir / "session_eval_summary.json", {})
    _write_json(artifacts_dir / "reference_comparison.json", {})
    _write_json(
        artifacts_dir / "reference_case_partitioned_citation_coverage.json",
        {"coverage": {"partition_coverage": {"p0": 1}}},
    )

    _save_current_session(
        tmp_path,
        ArtifactIndex(
            outline_json=str(outline_json),
            plot_manifest_json=str(artifacts_dir / "plot_manifest.json"),
            plot_captions_json=str(artifacts_dir / "plot_captions.json"),
            plot_assets_json=str(plot_assets_json),
            citation_map_json=str(citation_map_json),
            intro_related_tex=str(artifacts_dir / "intro_related.tex"),
            paper_full_tex=str(paper_tex),
            latest_compile_report_json=str(compile_report_json),
            latest_compile_env_json=str(compile_env_json),
            latest_runtime_parity_json=str(runtime_parity_json),
        ),
    )

    payload = run_fidelity_audit(tmp_path)
    statuses = {check["code"]: check["status"] for check in payload["checks"]}

    assert payload["status_histogram"] == {"missing": 6, "partial": 3, "implemented": 9}
    assert statuses["outline_json_contract"] == "implemented"
    assert statuses["plot_generation_depth"] == "implemented"
    assert statuses["generated_plot_assets_used_in_manuscript"] == "implemented"
    assert statuses["section_writing_pipeline"] == "implemented"
    assert statuses["submission_ready_output"] == "implemented"
    assert statuses["compile_environment_ready"] == "implemented"
    assert statuses["runtime_parity"] == "implemented"
    assert statuses["benchmark_eval_surface"] == "implemented"
    assert statuses["citation_partition_scaffold_surface"] == "implemented"
    assert (artifacts_dir / "citation_partition_request.json").exists()
