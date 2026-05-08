from __future__ import annotations

import contextlib
from dataclasses import replace
import hashlib
import io
import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from paperorchestra.cli import build_parser, main as cli_main
from paperorchestra import compile_env as compile_env_module
from paperorchestra.revisions import build_revision_suggestions
from paperorchestra.cost import estimate_run_cost
from paperorchestra.critics import (
    _citation_support_cache_key,
    _retrieved_web_evidence_is_reusable,
    build_citation_support_review,
    build_section_review,
    write_citation_support_review,
    write_section_review,
)
from paperorchestra.doctor import build_doctor_report
from paperorchestra.domains import GENERIC, available_domains, detect_domain_for_text, get_domain, register_domain
from paperorchestra.environment import (
    build_environment_inventory,
    env_example_path,
    environment_guide_path,
    operator_environment_variable_names,
)
from paperorchestra.fidelity import write_reproducibility_audit
from paperorchestra.eval import (
    write_generated_citation_titles,
    write_reference_benchmark_case,
    write_reference_case_partition_scaffold,
    write_reference_case_partitioned_citation_coverage,
    write_reference_comparison,
    write_review_gate_comparison,
    write_session_eval_summary,
)
from paperorchestra.jobs import get_job_status, list_jobs, start_run_job, tail_job_log
from paperorchestra.latex import LatexBuildError, _run_wrapped_command, compile_latex_with_report
from paperorchestra.literature import mock_verified_paper
from paperorchestra.mcp_server import TOOLS as MCP_TOOLS, TOOL_HANDLERS, tool_write_sections
from paperorchestra.omx_bridge import (
    OmxBridgeError,
    _is_retryable_omx_failure,
    _run_omx,
    cleanup_omx_tmp,
    omx_exec_completion,
    omx_exec_json_completion,
    _resolve_exec_timeout,
    _resolve_omx_model,
    _resolve_omx_reasoning_effort,
)
from paperorchestra.operator_feedback import (
    OPERATOR_PUBLIC_ENTRYPOINTS,
    _executor_failure_category,
    _operator_review_payload,
    apply_operator_feedback,
    build_operator_review_packet,
    derive_operator_issue_id,
    import_operator_feedback,
)
from paperorchestra.models import InputBundle
from paperorchestra.plot_assets import render_plot_assets
from paperorchestra.pipeline import (
    CANDIDATE_SCHEMA,
    ContractError,
    OUTLINE_SCHEMA,
    PLOT_SCHEMA,
    REVIEW_SCHEMA,
    _compact_intro_related_plan_for_prompt,
    _allow_related_citation_backfill,
    _compact_outline_for_prompt,
    _compact_plot_assets_for_prompt,
    _compact_plot_manifest_for_prompt,
    _compact_citation_map_for_prompt,
    _drop_unknown_citation_keys,
    _ensure_bibliography_hook,
    _ensure_generated_plot_usage,
    _ensure_minimum_citation_coverage,
    _remove_material_packet_sections,
    _normalize_generated_plot_paths,
    _normalize_source_figure_paths,
    _prompt_compact_text,
    _provider_identity_payload,
    _repair_inline_math_surplus_closing_brace,
    _restore_missing_referenced_labels,
    _source_critical_context_for_prompt,
    build_bib,
    discover_papers,
    generate_outline,
    generate_plots,
    import_prior_work,
    plan_narrative_and_claims,
    record_compile_environment_report,
    record_current_validation_report,
    record_fidelity_report,
    refine_current_paper,
    research_prior_work as generate_prior_work_seed,
    review_current_paper,
    run_pipeline,
    verify_papers,
    write_figure_placement_review,
    write_sections,
    write_intro_related,
)
from paperorchestra.providers import (
    CompletionRequest,
    MockProvider,
    ProviderError,
    ShellProvider,
    TransientProviderError,
    default_codex_web_provider_command,
    get_citation_support_provider,
    provider_supports_web_search,
)
from paperorchestra.transport_retry import is_retryable_transport_text
from paperorchestra.quality_loop import _next_ralph_instruction, _plan_verdict, write_quality_eval, write_quality_loop_plan
from paperorchestra.quality_loop_leakage import _leakage_markers_in_text
from paperorchestra.quality_loop_plan_logic import _quality_eval_actions
from paperorchestra.quality_loop_citation_support import ensure_final_citation_review_bound_to_quality_eval
from paperorchestra.quality_loop_history import _build_cross_iteration
from paperorchestra.quality_loop_reviews import _section_quality_check
from paperorchestra.ralph_bridge import (
    build_qa_loop_brief,
    build_ralph_start_payload,
    compute_progress_delta,
    qa_loop_exit_code,
    repair_citation_claims,
    run_qa_loop_step,
)
from paperorchestra.ralph_bridge_state import (
    MANUSCRIPT_CANDIDATE_WRITE_MARKER_FILENAME,
    guarded_replace_manuscript_text,
    recover_pending_manuscript_write,
)
from paperorchestra.runtime_parity import record_lane_manifest, record_runtime_parity_report
from paperorchestra.session import artifact_path, create_session, load_session, review_path, save_session
from paperorchestra.teach import prepare_teach_bundle
from paperorchestra.validator import validate_manuscript


class PipelineTestCase(unittest.TestCase):
    def _init_session_with_minimal_inputs(self, root: Path):
        files = {
            "idea.md": "## Problem Statement\nDemo\n",
            "experimental_log.md": "# Experimental Log\n\n## 1. Experimental Setup\n* **Datasets:** DemoSet\n",
            "template.tex": "\\documentclass{article}\n\\usepackage{graphicx}\n\\begin{document}\n\\section{Introduction}\n\\section{Related Work}\n\\section{Method}\n\\end{document}\n",
            "guidelines.md": "Target venue: DemoConf\n",
        }
        for name, content in files.items():
            (root / name).write_text(content, encoding="utf-8")
        (root / "figures").mkdir()
        return create_session(
            root,
            InputBundle(
                idea_path=str(root / "idea.md"),
                experimental_log_path=str(root / "experimental_log.md"),
                template_path=str(root / "template.tex"),
                guidelines_path=str(root / "guidelines.md"),
                figures_dir=str(root / "figures"),
                cutoff_date="2024-11-01",
            ),
        )

    def _write_terminal_human_needed_plan(self, root: Path, *, verdict: str = "human_needed") -> Path:
        state = load_session(root)
        manuscript_sha = None
        if state.artifacts.paper_full_tex and Path(state.artifacts.paper_full_tex).exists():
            manuscript_sha = "sha256:" + hashlib.sha256(Path(state.artifacts.paper_full_tex).read_bytes()).hexdigest()
        quality_path = artifact_path(root, "quality-eval.json")
        quality_path.write_text(
            json.dumps(
                {
                    "schema_version": "quality-eval/1",
                    "session_id": state.session_id,
                    "manuscript_hash": manuscript_sha,
                    "mode": "claim_safe",
                    "tiers": {"tier_4_human_finalization": {"status": "never_automated"}},
                }
            ),
            encoding="utf-8",
        )
        plan_path = artifact_path(root, "qa-loop.plan.json")
        plan_path.write_text(
            json.dumps(
                {
                    "schema_version": "qa-loop-plan/2",
                    "session_id": state.session_id,
                    "verdict": verdict,
                    "repair_actions": [],
                    "reads": {"quality_eval": str(quality_path)},
                    "quality_eval_summary": {"manuscript_hash": manuscript_sha},
                }
            ),
            encoding="utf-8",
        )
        return plan_path

    def _execution_source_sha(self, payload: dict) -> str:
        payload_for_hash = json.loads(json.dumps(payload, sort_keys=True))
        payload_for_hash.get("candidate_approval", {}).pop("source_execution_sha256", None)
        return "sha256:" + hashlib.sha256(
            json.dumps(payload_for_hash, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest()


__all__ = [name for name in globals() if not name.startswith("__")]

