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


class PipelineLatexRepairTests(unittest.TestCase):
    def test_repair_inline_math_surplus_closing_brace_from_advantage_expression(self) -> None:
        latex = r"incurring at most $\mathbf{Adv}^{\mathrm{prp}}_{E}(\mathcal{D})}$ by switching."

        repaired = _repair_inline_math_surplus_closing_brace(latex)

        self.assertIn(r"$\mathbf{Adv}^{\mathrm{prp}}_{E}(\mathcal{D})$", repaired)
        self.assertNotIn(r"(\mathcal{D})}$", repaired)

    def test_repair_inline_math_surplus_closing_brace_leaves_balanced_math_unchanged(self) -> None:
        latex = r"The term $\frac{a}{b}$ and escaped brace $\{x\}$ remain."

        self.assertEqual(_repair_inline_math_surplus_closing_brace(latex), latex)

    def test_repair_inline_math_surplus_closing_brace_leaves_display_math_unchanged(self) -> None:
        latex = r"$$\mathbf{Adv}^{\mathrm{prp}}_{E}(\mathcal{D})}$$"

        self.assertEqual(_repair_inline_math_surplus_closing_brace(latex), latex)

    def test_repair_inline_math_surplus_closing_brace_leaves_non_trailing_extra_brace_unchanged(self) -> None:
        latex = r"The malformed term $a} + b$ should stay visible to compile diagnostics."

        self.assertEqual(_repair_inline_math_surplus_closing_brace(latex), latex)

    def test_repair_inline_math_surplus_closing_brace_leaves_multiple_extra_braces_unchanged(self) -> None:
        latex = r"The malformed term $a}}$ should stay visible to compile diagnostics."

        self.assertEqual(_repair_inline_math_surplus_closing_brace(latex), latex)


class PipelineCitationCoverageTests(unittest.TestCase):
    def test_ensure_minimum_citation_coverage_adds_bounded_related_work_bridge(self) -> None:
        citation_map = {f"Ref{i}": {"title": f"Reference {i}"} for i in range(1, 7)}
        latex = (
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "\\section{Introduction}\n"
            "Intro cites~\\cite{Ref1}.\n"
            "\\section{Related Work}\n"
            "Prior work includes~\\cite{Ref2}.\n"
            "\\section{Method}\n"
            "Method.\n"
            "\\end{document}\n"
        )

        rendered = _ensure_minimum_citation_coverage(latex, citation_map, target=4)

        self.assertIn("\\paragraph{Additional related context.}", rendered)
        self.assertIn("\\cite{Ref3,Ref4}", rendered)
        self.assertLess(rendered.index("\\paragraph{Additional related context.}"), rendered.index("\\section{Method}"))
        self.assertNotIn("Ref5", rendered)

    def test_ensure_minimum_citation_coverage_leaves_satisfied_draft_unchanged(self) -> None:
        citation_map = {f"Ref{i}": {"title": f"Reference {i}"} for i in range(1, 4)}
        latex = "\\section{Related Work}\nCovered~\\cite{Ref1,Ref2}.\n"

        self.assertEqual(_ensure_minimum_citation_coverage(latex, citation_map, target=2), latex)

    def test_ensure_minimum_citation_coverage_leaves_large_shortfall_unchanged(self) -> None:
        citation_map = {f"Ref{i}": {"title": f"Reference {i}"} for i in range(1, 41)}
        latex = "\\section{Related Work}\nCovered~\\cite{Ref1,Ref2,Ref3,Ref4,Ref5}.\n"

        self.assertEqual(_ensure_minimum_citation_coverage(latex, citation_map, target=40), latex)

    def test_ensure_minimum_citation_coverage_requires_related_work_surface(self) -> None:
        citation_map = {f"Ref{i}": {"title": f"Reference {i}"} for i in range(1, 6)}
        latex = "\\section{Method}\nCovered~\\cite{Ref1,Ref2,Ref3}.\n"

        self.assertEqual(_ensure_minimum_citation_coverage(latex, citation_map, target=5), latex)

    def test_allow_related_citation_backfill_respects_section_scope(self) -> None:
        self.assertTrue(_allow_related_citation_backfill([]))
        self.assertTrue(_allow_related_citation_backfill(["Related Work"]))
        self.assertTrue(_allow_related_citation_backfill(["Background and Related Work"]))
        self.assertFalse(_allow_related_citation_backfill(["Method"]))


class OmxBridgeTests(unittest.TestCase):
    def test_resolve_exec_timeout_rejects_invalid_values(self) -> None:
        key = "PAPERO_OMX_EXEC_TIMEOUT_SECONDS"
        original = os.environ.get(key)
        try:
            for raw in ["oops", "-5", "0", "nan", "inf", "-inf"]:
                os.environ[key] = raw
                self.assertEqual(_resolve_exec_timeout(key, 180.0), 180.0)
        finally:
            if original is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original

    def test_resolve_exec_timeout_clamps_large_values(self) -> None:
        key = "PAPERO_OMX_EXEC_TIMEOUT_SECONDS"
        original = os.environ.get(key)
        try:
            os.environ[key] = "7200"
            self.assertEqual(_resolve_exec_timeout(key, 180.0), 3600.0)
        finally:
            if original is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original

    def test_resolve_omx_model_and_reasoning_effort_from_environment(self) -> None:
        old_model = os.environ.get("PAPERO_OMX_MODEL")
        old_effort = os.environ.get("PAPERO_OMX_REASONING_EFFORT")
        try:
            os.environ["PAPERO_OMX_MODEL"] = "gpt-5.4"
            os.environ["PAPERO_OMX_REASONING_EFFORT"] = "xhigh"
            self.assertEqual(_resolve_omx_model(), "gpt-5.4")
            self.assertEqual(_resolve_omx_model("custom-model"), "custom-model")
            self.assertEqual(_resolve_omx_reasoning_effort(), "xhigh")
        finally:
            if old_model is None:
                os.environ.pop("PAPERO_OMX_MODEL", None)
            else:
                os.environ["PAPERO_OMX_MODEL"] = old_model
            if old_effort is None:
                os.environ.pop("PAPERO_OMX_REASONING_EFFORT", None)
            else:
                os.environ["PAPERO_OMX_REASONING_EFFORT"] = old_effort

    def test_cleanup_omx_tmp_removes_execution_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tmp_dir = root / ".paper-orchestra" / "tmp"
            tmp_dir.mkdir(parents=True)
            (tmp_dir / "omx-exec-test.json").write_text("{}", encoding="utf-8")
            (tmp_dir / "keep.txt").write_text("keep", encoding="utf-8")
            payload = cleanup_omx_tmp(root)
            self.assertEqual(payload["removed_count"], 1)
            self.assertFalse((tmp_dir / "omx-exec-test.json").exists())
            self.assertTrue((tmp_dir / "keep.txt").exists())

    def test_run_omx_uses_control_timeout_and_reports_timeouts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = os.environ.get("PAPERO_OMX_CONTROL_TIMEOUT_SECONDS")
            try:
                os.environ["PAPERO_OMX_CONTROL_TIMEOUT_SECONDS"] = "12"
                proc = subprocess.CompletedProcess(["omx", "status"], 1, stdout="", stderr="")
                with patch("paperorchestra.omx_bridge._run_with_soft_timeout", return_value=(proc, True)):
                    with self.assertRaisesRegex(OmxBridgeError, "timed out after 12"):
                        _run_omx(["status"], cwd=root)
            finally:
                if old is None:
                    os.environ.pop("PAPERO_OMX_CONTROL_TIMEOUT_SECONDS", None)
                else:
                    os.environ["PAPERO_OMX_CONTROL_TIMEOUT_SECONDS"] = old

    def test_omx_failure_uses_shell_safe_command_rendering(self) -> None:
        proc = subprocess.CompletedProcess(["omx"], 2, stdout="", stderr="bad")
        with patch("paperorchestra.omx_bridge._run_with_soft_timeout", return_value=(proc, False)):
            with self.assertRaisesRegex(OmxBridgeError, "/tmp/space dir") as cm:
                _run_omx(["explore", "--prompt", "/tmp/space dir"], cwd=".", timeout_seconds=5)
        self.assertIn("'/tmp/space dir'", str(cm.exception))

    def test_run_omx_error_includes_returncode_when_outputs_are_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc = subprocess.CompletedProcess(["omx", "status"], 137, stdout="", stderr="")
            with patch("paperorchestra.omx_bridge._run_with_soft_timeout", return_value=(proc, False)):
                with self.assertRaisesRegex(OmxBridgeError, "returned 137"):
                    _run_omx(["status"], cwd=root, timeout_seconds=5)

    def test_run_omx_does_not_retry_mutating_state_operations(self) -> None:
        old_attempts = os.environ.get("PAPERO_OMX_RETRY_ATTEMPTS")
        old_backoff = os.environ.get("PAPERO_OMX_RETRY_BACKOFF_SECONDS")
        try:
            os.environ["PAPERO_OMX_RETRY_ATTEMPTS"] = "3"
            os.environ["PAPERO_OMX_RETRY_BACKOFF_SECONDS"] = "0"
            calls = []

            def fake_soft(args, **kwargs):
                calls.append((args, kwargs))
                return subprocess.CompletedProcess(args=args, returncode=42, stdout="", stderr="Reconnecting after connection reset"), False

            with tempfile.TemporaryDirectory() as tmp, patch("paperorchestra.omx_bridge._run_with_soft_timeout", side_effect=fake_soft):
                with self.assertRaisesRegex(OmxBridgeError, "returned 42"):
                    _run_omx(["state", "write", "--json"], cwd=tmp)
                self.assertEqual(len(calls), 1)
        finally:
            if old_attempts is None:
                os.environ.pop("PAPERO_OMX_RETRY_ATTEMPTS", None)
            else:
                os.environ["PAPERO_OMX_RETRY_ATTEMPTS"] = old_attempts
            if old_backoff is None:
                os.environ.pop("PAPERO_OMX_RETRY_BACKOFF_SECONDS", None)
            else:
                os.environ["PAPERO_OMX_RETRY_BACKOFF_SECONDS"] = old_backoff

    def test_omx_retry_detection_ignores_stdout_payload(self) -> None:
        self.assertFalse(_is_retryable_omx_failure('{"note":"connection reset by user text"}', ""))
        self.assertTrue(_is_retryable_omx_failure("", "Reconnecting after connection reset"))

    def test_run_omx_does_not_retry_explore_llm_control(self) -> None:
        old_attempts = os.environ.get("PAPERO_OMX_RETRY_ATTEMPTS")
        old_backoff = os.environ.get("PAPERO_OMX_RETRY_BACKOFF_SECONDS")
        try:
            os.environ["PAPERO_OMX_RETRY_ATTEMPTS"] = "3"
            os.environ["PAPERO_OMX_RETRY_BACKOFF_SECONDS"] = "0"
            calls = []

            def fake_soft(args, **kwargs):
                calls.append((args, kwargs))
                return subprocess.CompletedProcess(args=args, returncode=42, stdout="", stderr="Reconnecting after connection reset"), False

            with tempfile.TemporaryDirectory() as tmp, patch("paperorchestra.omx_bridge._run_with_soft_timeout", side_effect=fake_soft):
                with self.assertRaisesRegex(OmxBridgeError, "returned 42"):
                    _run_omx(["explore", "--prompt", "read-only but LLM-backed"], cwd=tmp)
                self.assertEqual(len(calls), 1)
        finally:
            if old_attempts is None:
                os.environ.pop("PAPERO_OMX_RETRY_ATTEMPTS", None)
            else:
                os.environ["PAPERO_OMX_RETRY_ATTEMPTS"] = old_attempts
            if old_backoff is None:
                os.environ.pop("PAPERO_OMX_RETRY_BACKOFF_SECONDS", None)
            else:
                os.environ["PAPERO_OMX_RETRY_BACKOFF_SECONDS"] = old_backoff

    def test_run_omx_retries_read_only_team_status(self) -> None:
        old_attempts = os.environ.get("PAPERO_OMX_RETRY_ATTEMPTS")
        old_backoff = os.environ.get("PAPERO_OMX_RETRY_BACKOFF_SECONDS")
        try:
            os.environ["PAPERO_OMX_RETRY_ATTEMPTS"] = "2"
            os.environ["PAPERO_OMX_RETRY_BACKOFF_SECONDS"] = "0"
            calls = []

            def fake_soft(args, **kwargs):
                calls.append((args, kwargs))
                rc = 42 if len(calls) == 1 else 0
                stderr = "Reconnecting after connection reset" if rc else ""
                return subprocess.CompletedProcess(args=args, returncode=rc, stdout="ok" if rc == 0 else "", stderr=stderr), False

            with tempfile.TemporaryDirectory() as tmp, patch("paperorchestra.omx_bridge._run_with_soft_timeout", side_effect=fake_soft):
                proc = _run_omx(["team", "status"], cwd=tmp)
                self.assertEqual(proc.stdout, "ok")
                self.assertEqual(len(calls), 2)
        finally:
            if old_attempts is None:
                os.environ.pop("PAPERO_OMX_RETRY_ATTEMPTS", None)
            else:
                os.environ["PAPERO_OMX_RETRY_ATTEMPTS"] = old_attempts
            if old_backoff is None:
                os.environ.pop("PAPERO_OMX_RETRY_BACKOFF_SECONDS", None)
            else:
                os.environ["PAPERO_OMX_RETRY_BACKOFF_SECONDS"] = old_backoff

    def test_run_omx_retries_read_only_state_read(self) -> None:
        old_attempts = os.environ.get("PAPERO_OMX_RETRY_ATTEMPTS")
        old_backoff = os.environ.get("PAPERO_OMX_RETRY_BACKOFF_SECONDS")
        try:
            os.environ["PAPERO_OMX_RETRY_ATTEMPTS"] = "2"
            os.environ["PAPERO_OMX_RETRY_BACKOFF_SECONDS"] = "0"
            calls = []

            def fake_soft(args, **kwargs):
                calls.append((args, kwargs))
                if len(calls) == 1:
                    return subprocess.CompletedProcess(args=args, returncode=42, stdout="", stderr="Reconnecting after connection reset"), False
                return subprocess.CompletedProcess(args=args, returncode=0, stdout='{"ok": true}', stderr=""), False

            with tempfile.TemporaryDirectory() as tmp, patch("paperorchestra.omx_bridge._run_with_soft_timeout", side_effect=fake_soft):
                result = _run_omx(["state", "read", "--json"], cwd=tmp)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(len(calls), 2)
        finally:
            if old_attempts is None:
                os.environ.pop("PAPERO_OMX_RETRY_ATTEMPTS", None)
            else:
                os.environ["PAPERO_OMX_RETRY_ATTEMPTS"] = old_attempts
            if old_backoff is None:
                os.environ.pop("PAPERO_OMX_RETRY_BACKOFF_SECONDS", None)
            else:
                os.environ["PAPERO_OMX_RETRY_BACKOFF_SECONDS"] = old_backoff

    def test_omx_exec_does_not_replay_retryable_reconnecting_failure(self) -> None:
        old_attempts = os.environ.get("PAPERO_OMX_RETRY_ATTEMPTS")
        old_backoff = os.environ.get("PAPERO_OMX_RETRY_BACKOFF_SECONDS")
        try:
            os.environ["PAPERO_OMX_RETRY_ATTEMPTS"] = "3"
            os.environ["PAPERO_OMX_RETRY_BACKOFF_SECONDS"] = "0"
            calls = []

            def fake_soft(args, **kwargs):
                calls.append((args, kwargs))
                return subprocess.CompletedProcess(args=args, returncode=42, stdout="", stderr="Reconnecting after connection reset"), False

            with tempfile.TemporaryDirectory() as tmp, patch("paperorchestra.omx_bridge._run_with_soft_timeout", side_effect=fake_soft):
                with self.assertRaisesRegex(OmxBridgeError, "returned 42"):
                    omx_exec_completion("prompt", cwd=tmp)
                self.assertEqual(len(calls), 1)
        finally:
            if old_attempts is None:
                os.environ.pop("PAPERO_OMX_RETRY_ATTEMPTS", None)
            else:
                os.environ["PAPERO_OMX_RETRY_ATTEMPTS"] = old_attempts
            if old_backoff is None:
                os.environ.pop("PAPERO_OMX_RETRY_BACKOFF_SECONDS", None)
            else:
                os.environ["PAPERO_OMX_RETRY_BACKOFF_SECONDS"] = old_backoff

    def test_omx_exec_can_succeed_during_soft_timeout_grace_without_replay(self) -> None:
        calls = []

        def fake_soft(args, **kwargs):
            calls.append((args, kwargs))
            output_path = Path(args[args.index("-o") + 1])
            output_path.write_text("ok", encoding="utf-8")
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="Reconnected"), True

        with tempfile.TemporaryDirectory() as tmp, patch("paperorchestra.omx_bridge._run_with_soft_timeout", side_effect=fake_soft):
            result = omx_exec_completion("prompt", cwd=tmp)
            self.assertEqual(Path(result.output_path).read_text(encoding="utf-8"), "ok")
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][1]["timeout_seconds"], 180.0)

    def test_structured_output_schemas_are_closed_for_omx_json_mode(self) -> None:
        def assert_closed(schema, path="root"):
            if isinstance(schema, dict):
                if schema.get("type") == "object":
                    self.assertEqual(
                        schema.get("additionalProperties"),
                        False,
                        f"{path} must declare additionalProperties=false for OMX/Codex structured output",
                    )
                    properties = schema.get("properties", {})
                    if properties:
                        self.assertEqual(
                            set(schema.get("required", [])),
                            set(properties.keys()),
                            f"{path} must require every declared property for OMX/Codex structured output",
                        )
                for key, value in schema.items():
                    assert_closed(value, f"{path}.{key}")
            elif isinstance(schema, list):
                for idx, item in enumerate(schema):
                    assert_closed(item, f"{path}[{idx}]")

        for name, schema in {
            "OUTLINE_SCHEMA": OUTLINE_SCHEMA,
            "PLOT_SCHEMA": PLOT_SCHEMA,
            "CANDIDATE_SCHEMA": CANDIDATE_SCHEMA,
            "REVIEW_SCHEMA": REVIEW_SCHEMA,
        }.items():
            assert_closed(schema, name)

    def test_omx_exec_sends_large_prompt_over_stdin_not_argv(self) -> None:
        calls = []

        def fake_soft(args, **kwargs):
            calls.append((args, kwargs))
            output_path = Path(args[args.index("-o") + 1])
            output_path.write_text("ok", encoding="utf-8")
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr=""), False

        with tempfile.TemporaryDirectory() as tmp, patch("paperorchestra.omx_bridge._run_with_soft_timeout", side_effect=fake_soft):
            large_prompt = "x" * 200_000
            omx_exec_completion(large_prompt, cwd=tmp)
            args, kwargs = calls[-1]
            self.assertEqual(args[-1], "-")
            self.assertNotIn(large_prompt, args)
            self.assertEqual(kwargs.get("input_text"), large_prompt)

            omx_exec_json_completion(large_prompt, {"type": "object", "properties": {}, "additionalProperties": False}, cwd=tmp)
            args, kwargs = calls[-1]
            self.assertEqual(args[-1], "-")
            self.assertNotIn(large_prompt, args)
            self.assertEqual(kwargs.get("input_text"), large_prompt)


class MockProviderTests(unittest.TestCase):
    def test_mock_provider_outline_shape(self) -> None:
        provider = MockProvider()
        response = provider.complete(type("Req", (), {"system_prompt": "Return a single, valid JSON object with top-level keys plotting_plan", "user_prompt": "x"})())
        payload = json.loads(response)
        self.assertIn("plotting_plan", payload)

    def test_shell_provider_honors_optional_timeout(self) -> None:
        old_allowlist = os.environ.get("PAPERO_ALLOWED_PROVIDER_BINARIES")
        old_timeout = os.environ.get("PAPERO_PROVIDER_TIMEOUT_SECONDS")
        try:
            os.environ["PAPERO_ALLOWED_PROVIDER_BINARIES"] = "python3"
            os.environ["PAPERO_PROVIDER_TIMEOUT_SECONDS"] = "0.1"
            provider = ShellProvider(command='["python3","-c","import sys,time; time.sleep(0.3); sys.stdout.write(sys.stdin.read())"]')
            with self.assertRaises(ProviderError):
                provider.complete(CompletionRequest(system_prompt="system", user_prompt="user"))
        finally:
            if old_allowlist is None:
                os.environ.pop("PAPERO_ALLOWED_PROVIDER_BINARIES", None)
            else:
                os.environ["PAPERO_ALLOWED_PROVIDER_BINARIES"] = old_allowlist
            if old_timeout is None:
                os.environ.pop("PAPERO_PROVIDER_TIMEOUT_SECONDS", None)
            else:
                os.environ["PAPERO_PROVIDER_TIMEOUT_SECONDS"] = old_timeout


    def test_shell_provider_waits_grace_before_replaying_timed_out_prompt(self) -> None:
        old_values = {key: os.environ.get(key) for key in [
            "PAPERO_ALLOWED_PROVIDER_BINARIES",
            "PAPERO_PROVIDER_TIMEOUT_SECONDS",
            "PAPERO_PROVIDER_TIMEOUT_GRACE_SECONDS",
            "PAPERO_PROVIDER_RETRY_ATTEMPTS",
            "PAPERO_PROVIDER_RETRY_BACKOFF_SECONDS",
        ]}
        try:
            os.environ["PAPERO_ALLOWED_PROVIDER_BINARIES"] = "python3"
            os.environ["PAPERO_PROVIDER_TIMEOUT_SECONDS"] = "0.1"
            os.environ["PAPERO_PROVIDER_TIMEOUT_GRACE_SECONDS"] = "0.5"
            os.environ["PAPERO_PROVIDER_RETRY_ATTEMPTS"] = "1"
            os.environ["PAPERO_PROVIDER_RETRY_BACKOFF_SECONDS"] = "0"
            provider = ShellProvider(
                command=json.dumps([
                    "python3",
                    "-c",
                    "import sys,time; time.sleep(0.2); sys.stdout.write(sys.stdin.read() + 'done')",
                ])
            )
            output = provider.complete(CompletionRequest(system_prompt="system", user_prompt="user"))
            self.assertIn("[SYSTEM]", output)
            self.assertTrue(output.endswith("done"))
        finally:
            for key, value in old_values.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_shell_provider_does_not_replay_plain_timeout_without_transport_evidence(self) -> None:
        old_values = {key: os.environ.get(key) for key in [
            "PAPERO_ALLOWED_PROVIDER_BINARIES",
            "PAPERO_PROVIDER_TIMEOUT_SECONDS",
            "PAPERO_PROVIDER_TIMEOUT_GRACE_SECONDS",
            "PAPERO_PROVIDER_RETRY_ATTEMPTS",
            "PAPERO_PROVIDER_RETRY_BACKOFF_SECONDS",
            "PAPERO_PROVIDER_RETRY_SAFE",
        ]}
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "attempts.txt"
            try:
                os.environ["PAPERO_ALLOWED_PROVIDER_BINARIES"] = "python3"
                os.environ["PAPERO_PROVIDER_TIMEOUT_SECONDS"] = "0.1"
                os.environ["PAPERO_PROVIDER_TIMEOUT_GRACE_SECONDS"] = "0"
                os.environ["PAPERO_PROVIDER_RETRY_ATTEMPTS"] = "2"
                os.environ["PAPERO_PROVIDER_RETRY_BACKOFF_SECONDS"] = "0"
                os.environ["PAPERO_PROVIDER_RETRY_SAFE"] = "1"
                command = json.dumps([
                    "python3",
                    "-c",
                    (
                        "import pathlib,sys,time; "
                        f"p=pathlib.Path({str(marker)!r}); "
                        "n=int(p.read_text()) if p.exists() else 0; "
                        "p.write_text(str(n+1)); "
                        "time.sleep(1)"
                    ),
                ])
                provider = ShellProvider(command=command)
                with self.assertRaisesRegex(ProviderError, "without retryable transport evidence"):
                    provider.complete(CompletionRequest(system_prompt="system", user_prompt="user"))
                self.assertEqual(marker.read_text(), "1")
            finally:
                for key, value in old_values.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    def test_shell_provider_does_not_replay_transport_evidence_without_retry_safe(self) -> None:
        old_values = {key: os.environ.get(key) for key in [
            "PAPERO_ALLOWED_PROVIDER_BINARIES",
            "PAPERO_PROVIDER_RETRY_ATTEMPTS",
            "PAPERO_PROVIDER_RETRY_BACKOFF_SECONDS",
            "PAPERO_PROVIDER_RETRY_SAFE",
        ]}
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "attempts.txt"
            try:
                os.environ["PAPERO_ALLOWED_PROVIDER_BINARIES"] = "python3"
                os.environ["PAPERO_PROVIDER_RETRY_ATTEMPTS"] = "2"
                os.environ["PAPERO_PROVIDER_RETRY_BACKOFF_SECONDS"] = "0"
                os.environ.pop("PAPERO_PROVIDER_RETRY_SAFE", None)
                command = json.dumps([
                    "python3",
                    "-c",
                    (
                        "import pathlib,sys; "
                        f"p=pathlib.Path({str(marker)!r}); "
                        "n=int(p.read_text()) if p.exists() else 0; "
                        "p.write_text(str(n+1)); "
                        "sys.stderr.write('Reconnecting after network error'); sys.exit(42)"
                    ),
                ])
                provider = ShellProvider(command=command)
                with self.assertRaisesRegex(ProviderError, "PAPERO_PROVIDER_RETRY_SAFE is not set"):
                    provider.complete(CompletionRequest(system_prompt="system", user_prompt="user"))
                self.assertEqual(marker.read_text(), "1")
            finally:
                for key, value in old_values.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    def test_shell_provider_replays_prompt_after_retryable_reconnecting_exit(self) -> None:
        old_values = {key: os.environ.get(key) for key in [
            "PAPERO_ALLOWED_PROVIDER_BINARIES",
            "PAPERO_PROVIDER_RETRY_ATTEMPTS",
            "PAPERO_PROVIDER_RETRY_BACKOFF_SECONDS",
            "PAPERO_PROVIDER_RETRY_SAFE",
        ]}
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "attempts.txt"
            try:
                os.environ["PAPERO_ALLOWED_PROVIDER_BINARIES"] = "python3"
                os.environ["PAPERO_PROVIDER_RETRY_ATTEMPTS"] = "1"
                os.environ["PAPERO_PROVIDER_RETRY_BACKOFF_SECONDS"] = "0"
                os.environ["PAPERO_PROVIDER_RETRY_SAFE"] = "1"
                command = json.dumps([
                    "python3",
                    "-c",
                    (
                        "import pathlib,sys; "
                        f"p=pathlib.Path({str(marker)!r}); "
                        "n=int(p.read_text()) if p.exists() else 0; "
                        "p.write_text(str(n+1)); "
                        "data=sys.stdin.read(); "
                        "(sys.stderr.write('Reconnecting after network error\\n') and sys.exit(42)) if n == 0 else sys.stdout.write(data + 'replayed')"
                    ),
                ])
                provider = ShellProvider(command=command)
                output = provider.complete(CompletionRequest(system_prompt="system", user_prompt="user"))
                self.assertTrue(output.endswith("replayed"))
                self.assertEqual(marker.read_text(), "2")
            finally:
                for key, value in old_values.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    def test_shell_provider_raises_transient_error_after_retry_budget_exhausted(self) -> None:
        old_values = {key: os.environ.get(key) for key in [
            "PAPERO_ALLOWED_PROVIDER_BINARIES",
            "PAPERO_PROVIDER_RETRY_ATTEMPTS",
            "PAPERO_PROVIDER_RETRY_BACKOFF_SECONDS",
            "PAPERO_PROVIDER_RETRY_SAFE",
        ]}
        try:
            os.environ["PAPERO_ALLOWED_PROVIDER_BINARIES"] = "python3"
            os.environ["PAPERO_PROVIDER_RETRY_ATTEMPTS"] = "1"
            os.environ["PAPERO_PROVIDER_RETRY_BACKOFF_SECONDS"] = "0"
            os.environ["PAPERO_PROVIDER_RETRY_SAFE"] = "1"
            provider = ShellProvider(
                command=json.dumps([
                    "python3",
                    "-c",
                    "import sys; sys.stderr.write('stream disconnected while Reconnecting\\n'); sys.exit(55)",
                ])
            )
            with self.assertRaisesRegex(TransientProviderError, "attempt 2/2"):
                provider.complete(CompletionRequest(system_prompt="system", user_prompt="user"))
        finally:
            for key, value in old_values.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_executor_failure_category_preserves_transient_provider_failures(self) -> None:
        self.assertEqual(_executor_failure_category(TransientProviderError("retry exhausted")), "provider_transient_retry_exhausted")
        self.assertEqual(_executor_failure_category(ProviderError("auth failed")), "provider_error")

    def test_transport_retry_matcher_corpus_is_shared(self) -> None:
        positives = [
            "Reconnecting after network error",
            "connection reset by peer",
            "stream disconnected",
            "ETIMEDOUT",
            "upstream unavailable",
        ]
        negatives = [
            "model rejected request",
            "LaTeX compile failed",
            "connection reset appears only in a manuscript quote but not stderr policy context",
        ]
        for text in positives:
            self.assertTrue(is_retryable_transport_text(text), text)
        self.assertFalse(is_retryable_transport_text(negatives[0]))
        self.assertFalse(is_retryable_transport_text(negatives[1]))

    def test_web_citation_provider_requires_global_codex_search_exec_shape(self) -> None:
        good = get_citation_support_provider(
            "shell",
            command=default_codex_web_provider_command(),
            evidence_mode="web",
        )
        self.assertIsNotNone(good)
        self.assertTrue(provider_supports_web_search(good))

        with self.assertRaises(ProviderError):
            get_citation_support_provider(
                "shell",
                command='["codex","exec","--search","--skip-git-repo-check"]',
                evidence_mode="web",
            )

    def test_web_citation_provider_uses_codex_search_default_when_model_cmd_is_non_search(self) -> None:
        old_cmd = os.environ.get("PAPERO_MODEL_CMD")
        try:
            os.environ["PAPERO_MODEL_CMD"] = '["codex","exec","--skip-git-repo-check"]'
            provider = get_citation_support_provider("shell", evidence_mode="web")
            self.assertIsNotNone(provider)
            self.assertTrue(provider_supports_web_search(provider))
            self.assertEqual(provider.argv[:3], ["codex", "--search", "exec"])
        finally:
            if old_cmd is None:
                os.environ.pop("PAPERO_MODEL_CMD", None)
            else:
                os.environ["PAPERO_MODEL_CMD"] = old_cmd

    def test_shell_provider_passes_request_knobs_via_environment_only_when_set(self) -> None:
        old_allowlist = os.environ.get("PAPERO_ALLOWED_PROVIDER_BINARIES")
        old_seed = os.environ.get("PAPERO_PROVIDER_SEED")
        old_temperature = os.environ.get("PAPERO_PROVIDER_TEMPERATURE")
        old_max_output_tokens = os.environ.get("PAPERO_PROVIDER_MAX_OUTPUT_TOKENS")
        try:
            os.environ["PAPERO_ALLOWED_PROVIDER_BINARIES"] = "python3"
            os.environ.pop("PAPERO_PROVIDER_SEED", None)
            os.environ.pop("PAPERO_PROVIDER_TEMPERATURE", None)
            os.environ.pop("PAPERO_PROVIDER_MAX_OUTPUT_TOKENS", None)
            command = (
                '["python3","-c",'
                '"import json, os; '
                "print(json.dumps({"
                "\\\"seed\\\": os.environ.get(\\\"PAPERO_PROVIDER_SEED\\\"), "
                "\\\"temperature\\\": os.environ.get(\\\"PAPERO_PROVIDER_TEMPERATURE\\\"), "
                "\\\"max_output_tokens\\\": os.environ.get(\\\"PAPERO_PROVIDER_MAX_OUTPUT_TOKENS\\\")"
                "}))"
                '"]'
            )
            provider = ShellProvider(command=command)

            unset_payload = json.loads(provider.complete(CompletionRequest(system_prompt="system", user_prompt="user")))
            self.assertEqual(unset_payload, {"seed": None, "temperature": None, "max_output_tokens": None})

            set_payload = json.loads(
                provider.complete(
                    CompletionRequest(
                        system_prompt="system",
                        user_prompt="user",
                        temperature=0.2,
                        max_output_tokens=321,
                        seed=7,
                    )
                )
            )
            self.assertEqual(
                set_payload,
                {"seed": "7", "temperature": "0.2", "max_output_tokens": "321"},
            )
        finally:
            if old_allowlist is None:
                os.environ.pop("PAPERO_ALLOWED_PROVIDER_BINARIES", None)
            else:
                os.environ["PAPERO_ALLOWED_PROVIDER_BINARIES"] = old_allowlist
            if old_seed is None:
                os.environ.pop("PAPERO_PROVIDER_SEED", None)
            else:
                os.environ["PAPERO_PROVIDER_SEED"] = old_seed
            if old_temperature is None:
                os.environ.pop("PAPERO_PROVIDER_TEMPERATURE", None)
            else:
                os.environ["PAPERO_PROVIDER_TEMPERATURE"] = old_temperature
            if old_max_output_tokens is None:
                os.environ.pop("PAPERO_PROVIDER_MAX_OUTPUT_TOKENS", None)
            else:
                os.environ["PAPERO_PROVIDER_MAX_OUTPUT_TOKENS"] = old_max_output_tokens

    def test_shell_provider_drops_invalid_ambient_request_knobs(self) -> None:
        old_allowlist = os.environ.get("PAPERO_ALLOWED_PROVIDER_BINARIES")
        old_seed = os.environ.get("PAPERO_PROVIDER_SEED")
        old_temperature = os.environ.get("PAPERO_PROVIDER_TEMPERATURE")
        old_max_output_tokens = os.environ.get("PAPERO_PROVIDER_MAX_OUTPUT_TOKENS")
        try:
            os.environ["PAPERO_ALLOWED_PROVIDER_BINARIES"] = "python3"
            os.environ["PAPERO_PROVIDER_SEED"] = "not-an-int"
            os.environ["PAPERO_PROVIDER_TEMPERATURE"] = "nan"
            os.environ["PAPERO_PROVIDER_MAX_OUTPUT_TOKENS"] = "not-an-int"
            command = (
                '["python3","-c",'
                '"import json, os; '
                "print(json.dumps({"
                "\\\"seed\\\": os.environ.get(\\\"PAPERO_PROVIDER_SEED\\\"), "
                "\\\"temperature\\\": os.environ.get(\\\"PAPERO_PROVIDER_TEMPERATURE\\\"), "
                "\\\"max_output_tokens\\\": os.environ.get(\\\"PAPERO_PROVIDER_MAX_OUTPUT_TOKENS\\\")"
                "}))"
                '"]'
            )
            provider = ShellProvider(command=command)
            payload = json.loads(provider.complete(CompletionRequest(system_prompt="system", user_prompt="user")))
            self.assertEqual(payload, {"seed": None, "temperature": None, "max_output_tokens": None})
        finally:
            if old_allowlist is None:
                os.environ.pop("PAPERO_ALLOWED_PROVIDER_BINARIES", None)
            else:
                os.environ["PAPERO_ALLOWED_PROVIDER_BINARIES"] = old_allowlist
            if old_seed is None:
                os.environ.pop("PAPERO_PROVIDER_SEED", None)
            else:
                os.environ["PAPERO_PROVIDER_SEED"] = old_seed
            if old_temperature is None:
                os.environ.pop("PAPERO_PROVIDER_TEMPERATURE", None)
            else:
                os.environ["PAPERO_PROVIDER_TEMPERATURE"] = old_temperature
            if old_max_output_tokens is None:
                os.environ.pop("PAPERO_PROVIDER_MAX_OUTPUT_TOKENS", None)
            else:
                os.environ["PAPERO_PROVIDER_MAX_OUTPUT_TOKENS"] = old_max_output_tokens

class BackgroundJobTests(unittest.TestCase):
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

    def test_background_run_job_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            job = start_run_job(
                root,
                provider="mock",
                discovery_mode="model",
                verify_mode="mock",
                refine_iterations=1,
                compile_paper=False,
                runtime_mode="compatibility",
            )
            self.assertEqual(job["status"], "running")
            final_status = None
            for _ in range(100):
                status = get_job_status(root, job["job_id"])
                if status["status"] in {"succeeded", "failed", "cancelled"}:
                    final_status = status
                    break
                time.sleep(0.05)
            self.assertIsNotNone(final_status)
            self.assertEqual(final_status["status"], "succeeded")
            self.assertIn("result", final_status)
            self.assertEqual(final_status["result"]["status"], "draft_complete")
            self.assertIn("session_progress", final_status)
            self.assertEqual(final_status["session_progress"]["current_phase"], "draft_complete")
            self.assertEqual(final_status["session_progress"]["session_id"], job["session_id"])
            tail = tail_job_log(root, job["job_id"], lines=20)
            self.assertIn("job_id", tail)
            self.assertTrue("runner_started" in tail["tail"] or "\"stage\": \"outline\"" in tail["tail"])
            listing = list_jobs(root, limit=5)
            self.assertTrue(any(item["job_id"] == job["job_id"] for item in listing["jobs"]))

            alt_root = root / "alt"
            alt_root.mkdir()
            files = {
                "idea.md": "## Problem Statement\nAlt Demo\n",
                "experimental_log.md": "# Experimental Log\n\n## 1. Experimental Setup\n* **Datasets:** AltSet\n",
                "template.tex": "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\n\\end{document}\n",
                "guidelines.md": "Target venue: AltConf\n",
            }
            for name, content in files.items():
                (alt_root / name).write_text(content, encoding="utf-8")
            (alt_root / "figures").mkdir()
            create_session(
                root,
                InputBundle(
                    idea_path=str(alt_root / "idea.md"),
                    experimental_log_path=str(alt_root / "experimental_log.md"),
                    template_path=str(alt_root / "template.tex"),
                    guidelines_path=str(alt_root / "guidelines.md"),
                    figures_dir=str(alt_root / "figures"),
                    cutoff_date="2024-11-01",
                ),
            )
            rebound_status = get_job_status(root, job["job_id"])
            self.assertEqual(rebound_status["session_progress"]["session_id"], job["session_id"])

    def test_run_status_and_tail_log_aliases_match_job_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            job = start_run_job(
                root,
                provider="mock",
                discovery_mode="model",
                verify_mode="mock",
                refine_iterations=0,
                compile_paper=False,
                runtime_mode="compatibility",
            )
            for _ in range(100):
                status = get_job_status(root, job["job_id"])
                if status["status"] in {"succeeded", "failed", "cancelled"}:
                    break
                time.sleep(0.05)

            old_cwd = Path.cwd()
            status_out = io.StringIO()
            tail_out = io.StringIO()
            try:
                os.chdir(root)
                with contextlib.redirect_stdout(status_out):
                    self.assertEqual(cli_main(["run-status", "--job-id", job["job_id"]]), 0)
                with contextlib.redirect_stdout(tail_out):
                    self.assertEqual(cli_main(["run-tail-log", "--job-id", job["job_id"], "--lines", "5"]), 0)
            finally:
                os.chdir(old_cwd)
            self.assertEqual(json.loads(status_out.getvalue())["job_id"], job["job_id"])
            self.assertEqual(json.loads(tail_out.getvalue())["job_id"], job["job_id"])

    def test_job_id_path_traversal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ValueError):
                get_job_status(root, "../../escape")

class PipelineTests(unittest.TestCase):
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

    def test_run_pipeline_completes_in_mock_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            result = run_pipeline(
                root,
                provider=MockProvider(),
                discovery_mode="model",
                verify_mode="mock",
                refine_iterations=1,
                compile_paper=False,
            )
            self.assertIn("outline", result)
            self.assertIn("plots", result)
            self.assertIn("verified", result)
            self.assertIn("plot_assets", result)
            self.assertIn("compile_environment", result)
            self.assertIn("compile_environment_report", result)
            self.assertIn("runtime_parity_report", result)
            self.assertIn("runtime_parity", result)
            state = load_session(root)
            self.assertIsNotNone(state.artifacts.plot_manifest_json)
            self.assertIsNotNone(state.artifacts.plot_assets_json)
            self.assertTrue(Path(state.artifacts.plot_assets_json).exists())
            self.assertIsNotNone(state.artifacts.paper_full_tex)
            self.assertGreaterEqual(state.refinement_iteration, 1)
            self.assertEqual(result["status"], "draft_complete")
            self.assertEqual(state.current_phase, "draft_complete")
            self.assertIn("plot_captions", result)
            self.assertIn("validation_reports", result)
            self.assertIn("fidelity_report", result)
            self.assertIn("fidelity", result)
            self.assertIn("intro_related", result["validation_reports"])
            self.assertIn("section_writing", result["validation_reports"])
            self.assertTrue(result["validation_reports"]["refinement"])
            self.assertTrue(any("completed in parallel" in note.lower() for note in state.notes))
            self.assertIsNotNone(state.artifacts.latest_validation_json)
            self.assertIsNotNone(state.artifacts.latest_fidelity_json)
            self.assertIsNotNone(state.artifacts.latest_compile_env_json)
            self.assertIsNotNone(state.artifacts.latest_runtime_parity_json)
            self.assertTrue(any(check["code"] == "plot_generation_depth" and check["status"] == "implemented" for check in result["fidelity"]["checks"]))
            self.assertTrue(any(check["code"] == "generated_plot_assets_used_in_manuscript" and check["status"] == "partial" for check in result["fidelity"]["checks"]))
            self.assertNotIn("PaperOrchestra:auto-repaired figure", Path(state.artifacts.paper_full_tex).read_text(encoding="utf-8"))

    def test_plot_asset_snippets_do_not_render_prompt_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, index_path = render_plot_assets(
                {
                    "figures": [
                        {
                            "figure_id": "fig_demo",
                            "title": "Supplied source packet overview",
                            "plot_type": "diagram",
                            "aspect_ratio": "4:3",
                            "objective": "Internal generation objective that should not be rendered.",
                            "caption": "A clean caption linking claims to the supplied source packet.",
                            "source_fidelity_notes": "data-grounded; internal provenance note",
                            "rendering_brief": "Internal visual prompt.",
                        },
                        {
                            "title": "Supplied source packet fallback",
                            "plot_type": "diagram",
                            "aspect_ratio": "4:3",
                            "caption": "Fallback caption.",
                        }
                    ]
                },
                root / "build" / "plot-assets",
            )
            payload = json.loads(index_path.read_text(encoding="utf-8"))
            rendered_parts = []
            for asset in payload["assets"]:
                rendered_parts.append(Path(asset["tex_path"]).read_text(encoding="utf-8"))
                rendered_parts.append(Path(asset["path"]).read_text(encoding="utf-8"))
            rendered = "\n".join(rendered_parts)
            self.assertNotIn("Caption intent", rendered)
            self.assertNotIn("Fidelity:", rendered)
            self.assertNotIn("Internal generation objective", rendered)
            self.assertNotIn("Internal visual prompt", rendered)
            self.assertNotIn("supplied source packet", rendered)
            self.assertNotIn("Supplied source packet", rendered)
            self.assertIn("stated evidence", rendered)
            self.assertEqual(payload["assets"][0]["title"], "stated evidence overview")
            self.assertEqual(payload["assets"][0]["caption"], "A clean caption linking claims to the stated evidence.")
            self.assertEqual(payload["assets"][1]["title"], "stated evidence fallback")
            self.assertEqual(payload["assets"][1]["filename"], "stated-evidence-fallback.svg")
            self.assertEqual(payload["assets"][1]["latex_snippet_filename"], "stated-evidence-fallback.tex")

    def test_boundary_refactor_cli_facades_remain_callable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_cwd = Path.cwd()
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n"
                "\\section{Introduction}\nClean background text.\\cite{Ref2020}\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(json.dumps({"Ref2020": {"title": "Reference"}}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)
            try:
                os.chdir(root)
                for command in (["validate-current"], ["quality-eval"], ["qa-loop-plan"]):
                    with contextlib.redirect_stdout(io.StringIO()) as stdout:
                        code = cli_main(command)
                    payload = json.loads(stdout.getvalue())
                    self.assertEqual(code, 0)
                    self.assertIn("path", payload)
                    if command[0] == "validate-current":
                        self.assertIn("report", payload)
                    elif command[0] == "quality-eval":
                        self.assertIn("quality_eval", payload)
                        self.assertIn("tiers", payload["quality_eval"])
                    else:
                        self.assertIn("plan", payload)
                        self.assertIn(payload["plan"]["verdict"], {"ready_for_human_finalization", "continue", "human_needed", "failed"})
            finally:
                os.chdir(old_cwd)

    def test_quality_eval_fails_on_plot_asset_prompt_leakage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n"
                "\\section{Introduction}\nClean text.\n"
                "\\begin{figure}\\input{build/plot-assets/fig_bad.tex}\\caption{Bad}\\end{figure}\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            asset_dir = root / ".paper-orchestra" / "runs" / state.session_id / "build" / "plot-assets"
            asset_dir.mkdir(parents=True, exist_ok=True)
            bad_tex = asset_dir / "fig_bad.tex"
            bad_tex.write_text("\\textbf{Caption intent:} leaked prompt\\\\\n\\textbf{Fidelity:} leaked meta\n", encoding="utf-8")
            index = asset_dir / "plot-assets.json"
            index.write_text(
                json.dumps(
                    {
                        "assets": [
                            {
                                "figure_id": "fig_bad",
                                "latex_snippet_path": "build/plot-assets/fig_bad.tex",
                                "tex_path": str(bad_tex),
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.plot_assets_json = str(index)
            save_session(root, state)

            _, quality_eval = write_quality_eval(root, quality_mode="claim_safe")

            self.assertIn("prompt_meta_leakage", quality_eval["non_reviewable"]["failing_codes"])
            markers = quality_eval["non_reviewable"]["checks"]["prompt_meta_leakage"]["markers"]
            self.assertTrue(any("plot_asset:fig_bad.tex" in marker for marker in markers))

    def test_prompt_meta_leakage_plan_is_failed_not_human_needed(self) -> None:
        old_strict = os.environ.get("PAPERO_STRICT_CONTENT_GATES")
        os.environ["PAPERO_STRICT_CONTENT_GATES"] = "1"
        with tempfile.TemporaryDirectory() as tmp:
            try:
                root = Path(tmp)
                state = self._init_session_with_minimal_inputs(root)
                paper = artifact_path(root, "paper.full.tex")
                paper.write_text(
                    "\\documentclass{article}\n\\begin{document}\n"
                    "\\section{Introduction}\nCaption intent: internal generation note.\n"
                    "\\end{document}\n",
                    encoding="utf-8",
                )
                state.artifacts.paper_full_tex = str(paper)
                save_session(root, state)

                _, plan = write_quality_loop_plan(root, quality_mode="claim_safe")

                self.assertEqual(plan["verdict"], "failed")
                self.assertIn("non-reviewable", plan["verdict_rationale"])
                self.assertIn("prompt_meta_leakage", plan["quality_eval_summary"]["failing_codes"])
            finally:
                if old_strict is None:
                    os.environ.pop("PAPERO_STRICT_CONTENT_GATES", None)
                else:
                    os.environ["PAPERO_STRICT_CONTENT_GATES"] = old_strict

    def test_source_boundary_meta_leakage_plan_is_failed_not_human_needed(self) -> None:
        old_strict = os.environ.get("PAPERO_STRICT_CONTENT_GATES")
        os.environ["PAPERO_STRICT_CONTENT_GATES"] = "1"
        with tempfile.TemporaryDirectory() as tmp:
            try:
                root = Path(tmp)
                state = self._init_session_with_minimal_inputs(root)
                paper = artifact_path(root, "paper.full.tex")
                paper.write_text(
                    "\\documentclass{article}\n\\begin{document}\n"
                    "\\section{Discussion}\n"
                    "Within the supplied source boundary, the draft remains bounded by the supplied source material. "
                    "The statement is limited to the provided material and does not add an external claim.\n"
                    "\\end{document}\n",
                    encoding="utf-8",
                )
                state.artifacts.paper_full_tex = str(paper)
                save_session(root, state)

                _, plan = write_quality_loop_plan(root, quality_mode="claim_safe")

                self.assertEqual(plan["verdict"], "failed")
                self.assertIn("non-reviewable", plan["verdict_rationale"])
                self.assertIn("prompt_meta_leakage", plan["quality_eval_summary"]["failing_codes"])
            finally:
                if old_strict is None:
                    os.environ.pop("PAPERO_STRICT_CONTENT_GATES", None)
                else:
                    os.environ["PAPERO_STRICT_CONTENT_GATES"] = old_strict

    def test_quality_eval_fails_on_svg_plot_asset_prompt_leakage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n"
                "\\section{Introduction}\nClean text.\n"
                "\\begin{figure}\\includegraphics{build/plot-assets/fig_bad.svg}\\caption{Bad}\\end{figure}\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            asset_dir = root / ".paper-orchestra" / "runs" / state.session_id / "build" / "plot-assets"
            asset_dir.mkdir(parents=True, exist_ok=True)
            bad_svg = asset_dir / "fig_bad.svg"
            bad_svg.write_text("<svg><text>Caption intent: leaked SVG prompt</text></svg>\n", encoding="utf-8")
            index = asset_dir / "plot-assets.json"
            index.write_text(
                json.dumps({"assets": [{"figure_id": "fig_bad", "path": str(bad_svg), "latex_path": "build/plot-assets/fig_bad.svg"}]}),
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.plot_assets_json = str(index)
            save_session(root, state)

            _, quality_eval = write_quality_eval(root, quality_mode="claim_safe")

            self.assertIn("prompt_meta_leakage", quality_eval["non_reviewable"]["failing_codes"])
            markers = quality_eval["non_reviewable"]["checks"]["prompt_meta_leakage"]["markers"]
            self.assertTrue(any("plot_asset:fig_bad.svg" in marker for marker in markers))

    def test_visual_prompt_label_scanner_ignores_prose_objective_colon(self) -> None:
        prose = "This narrow guarantee matches the workflow's design objective: integrity of artifact-governed promotion."

        self.assertFalse(_leakage_markers_in_text(prose, source="pdftotext", visual_context=True))
        self.assertIn(
            "visual_objective_label (svg)",
            _leakage_markers_in_text("<svg><text>Objective: leaked plotting prompt</text></svg>", source="svg", visual_context=True),
        )

    def test_placeholder_plot_assets_force_failed_non_reviewable_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n"
                "\\section{Introduction}\nClean text.\n"
                "\\begin{figure}\\input{build/plot-assets/fig_demo.tex}\\caption{Demo}\\end{figure}\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            asset_dir = root / ".paper-orchestra" / "runs" / state.session_id / "build" / "plot-assets"
            asset_dir.mkdir(parents=True, exist_ok=True)
            fig_tex = asset_dir / "fig_demo.tex"
            fig_tex.write_text("\\textbf{Demo}\\\\\n", encoding="utf-8")
            index = asset_dir / "plot-assets.json"
            index.write_text(
                json.dumps(
                    {
                        "assets": [
                            {
                                "figure_id": "fig_demo",
                                "latex_snippet_path": "build/plot-assets/fig_demo.tex",
                                "tex_path": str(fig_tex),
                                "asset_kind": "generated_placeholder",
                                "review_status": "human_final_artwork_required",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.plot_assets_json = str(index)
            save_session(root, state)

            _, plan = write_quality_loop_plan(root, quality_mode="claim_safe")

            self.assertEqual(plan["verdict"], "failed")
            self.assertIn("non-reviewable", plan["verdict_rationale"])
            self.assertIn("final_figure_assets_non_reviewable", [action["code"] for action in plan["repair_actions"]])

    def test_pipeline_populates_completion_request_knobs_from_environment(self) -> None:
        class ObservingOutlineProvider(MockProvider):
            def __init__(self) -> None:
                self.requests: list[CompletionRequest] = []

            def complete(self, request: CompletionRequest) -> str:
                self.requests.append(request)
                return super().complete(request)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            provider = ObservingOutlineProvider()
            old_seed = os.environ.get("PAPERO_PROVIDER_SEED")
            old_temperature = os.environ.get("PAPERO_PROVIDER_TEMPERATURE")
            old_max_output_tokens = os.environ.get("PAPERO_PROVIDER_MAX_OUTPUT_TOKENS")
            try:
                os.environ["PAPERO_PROVIDER_SEED"] = "7"
                os.environ["PAPERO_PROVIDER_TEMPERATURE"] = "0.2"
                os.environ["PAPERO_PROVIDER_MAX_OUTPUT_TOKENS"] = "321"
                generate_outline(root, provider)
            finally:
                if old_seed is None:
                    os.environ.pop("PAPERO_PROVIDER_SEED", None)
                else:
                    os.environ["PAPERO_PROVIDER_SEED"] = old_seed
                if old_temperature is None:
                    os.environ.pop("PAPERO_PROVIDER_TEMPERATURE", None)
                else:
                    os.environ["PAPERO_PROVIDER_TEMPERATURE"] = old_temperature
                if old_max_output_tokens is None:
                    os.environ.pop("PAPERO_PROVIDER_MAX_OUTPUT_TOKENS", None)
                else:
                    os.environ["PAPERO_PROVIDER_MAX_OUTPUT_TOKENS"] = old_max_output_tokens

            self.assertTrue(provider.requests)
            request = provider.requests[0]
            self.assertEqual(request.seed, 7)
            self.assertEqual(request.temperature, 0.2)
            self.assertEqual(request.max_output_tokens, 321)
            state = load_session(root)
            provider_identity = json.loads(Path(state.artifacts.latest_provider_identity_json).read_text(encoding="utf-8"))
            self.assertEqual(provider_identity["request_controls"]["seed"], 7)
            self.assertFalse(provider_identity["generation_determinism"]["byte_identical_generation_claimed"])
            prompt_meta_files = sorted(Path(state.artifacts.latest_prompt_trace_dir).glob("*.meta.json"))
            self.assertTrue(prompt_meta_files)
            prompt_meta = json.loads(prompt_meta_files[-1].read_text(encoding="utf-8"))
            self.assertEqual(prompt_meta["stage"], "outline")
            self.assertEqual(prompt_meta["provider_identity"]["stage"], "outline")
            self.assertEqual(prompt_meta["request_controls"]["max_output_tokens"], 321)
            self.assertFalse(prompt_meta["deterministic_generation_guaranteed"])

    def test_runtime_parity_accepts_grounded_literature_substitute_under_omx_native(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(
                root,
                provider=MockProvider(),
                discovery_mode="model",
                verify_mode="mock",
                refine_iterations=1,
                compile_paper=False,
            )
            state = load_session(root)
            artifacts_dir = Path(state.artifacts.outline_json).parent
            record_lane_manifest(
                root,
                stage="literature",
                role="Literature Review Agent",
                runtime_mode="omx_native",
                lane_type="python",
                owner="python",
                status="completed",
                input_artifacts=[state.artifacts.outline_json or ""],
                output_artifacts=[str(artifacts_dir / "candidate_papers.json")],
                fallback_used=False,
                notes=[
                    "Semantic Scholar grounded query completed: Single Agent",
                    "OpenAlex grounded query completed: Single Agent",
                    "Exact grounded seed preserved without matching live result: Single Agent",
                ],
            )
            _, payload = record_runtime_parity_report(root)
            literature = next(item for item in payload["checks"] if item["stage"] == "literature")
            self.assertEqual(literature["status"], "implemented")

    def test_runtime_parity_accepts_curated_prior_work_import_for_literature_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(
                root,
                provider=MockProvider(),
                discovery_mode="model",
                verify_mode="mock",
                refine_iterations=1,
                compile_paper=False,
            )
            state = load_session(root)
            artifacts_dir = Path(state.artifacts.outline_json).parent
            record_lane_manifest(
                root,
                stage="literature",
                role="Curated Prior Work Import",
                runtime_mode="curated_seed",
                lane_type="manual",
                owner="operator",
                status="completed",
                input_artifacts=[str(root / "refs.bib")],
                output_artifacts=[str(artifacts_dir / "citation_registry.json")],
                fallback_used=False,
                notes=[
                    "Imported 12 curated prior-work entries from refs.bib.",
                    "Entries are curated seed metadata, not live Semantic Scholar verification unless the source says so.",
                ],
            )
            _, payload = record_runtime_parity_report(root)
            literature = next(item for item in payload["checks"] if item["stage"] == "literature")
            self.assertEqual(literature["status"], "implemented")

    def test_data_block_escaping_handles_literal_closing_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "figures").mkdir()
            (root / "idea.md").write_text("## Problem\nLiteral marker </DATA_BLOCK> should be treated as data.\n", encoding="utf-8")
            (root / "experimental_log.md").write_text("# Experimental Log\n\n## 1. Experimental Setup\n* **Datasets:** DemoSet\n", encoding="utf-8")
            (root / "template.tex").write_text("\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\n\\end{document}\n", encoding="utf-8")
            (root / "guidelines.md").write_text("Target venue: DemoConf\n", encoding="utf-8")
            create_session(
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
            path = generate_outline(root, MockProvider())
            self.assertTrue(Path(path).exists())

    def test_scholar_only_discovery_handles_query_errors_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            (root / "template.tex").write_text(
                "\\documentclass{article}\n"
                "\\usepackage{graphicx}\n"
                "\\begin{document}\n"
                "\\begin{abstract}\n"
                "% PaperOrchestra writes this.\n"
                "\\end{abstract}\n"
                "\\section{Introduction}\n"
                "\\section{Related Work}\n"
                "\\section{Method}\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            generate_outline(root, MockProvider())
            with patch("paperorchestra.pipeline.search_semantic_scholar", side_effect=RuntimeError("rate limited")):
                path = discover_papers(root, MockProvider(), mode="scholar-only")
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            state = load_session(root)
            lane_manifest = json.loads((Path(state.artifacts.outline_json).parent / "lane-manifest.literature.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["macro_candidates"], [])
            self.assertEqual(payload["micro_candidates"], [])
            self.assertEqual(state.latest_discovery_mode, "scholar-only")
            self.assertTrue(any("Scholar-only query failed" in note for note in lane_manifest.get("notes", [])))


    def test_research_prior_work_generates_seed_and_can_import(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            output = root / "prior_work_seed.json"
            old_cwd = Path.cwd()
            stdout = io.StringIO()
            try:
                os.chdir(root)
                with contextlib.redirect_stdout(stdout):
                    code = cli_main([
                        "research-prior-work",
                        "--provider", "mock",
                        "--output", str(output),
                        "--source", "codex_web_seed",
                        "--import",
                    ])
            finally:
                os.chdir(old_cwd)
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["reference_count"], 2)
            self.assertTrue(output.exists())
            rendered_seed = output.read_text(encoding="utf-8")
            self.assertNotIn("Transport Layer Security", rendered_seed)
            self.assertNotIn("Protected Channels", rendered_seed)
            self.assertIn("imported", payload)
            state = load_session(root)
            self.assertIsNotNone(state.artifacts.references_bib)
            citation_map = json.loads(Path(state.artifacts.citation_map_json).read_text(encoding="utf-8"))
            self.assertTrue(any(entry.get("provenance", {}).get("source") == "codex_web_seed" for entry in citation_map.values()))

    def test_import_prior_work_seed_writes_registry_map_and_bib(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            seed_path = root / "prior_work.json"
            seed_path.write_text(
                json.dumps(
                    {
                        "references": [
                            {
                                "title": "The Transport Layer Security Protocol Version 1.3",
                                "authors": ["Eric Rescorla"],
                                "year": 2018,
                                "venue": "RFC",
                                "url": "https://www.rfc-editor.org/rfc/rfc8446",
                                "source": "codex_web_seed",
                                "notes": "Official TLS 1.3 standard.",
                            },
                            {
                                "title": "Using TLS to Secure QUIC",
                                "authors": "Martin Thomson and Sean Turner",
                                "year": 2021,
                                "venue": "RFC",
                                "doi": "10.17487/RFC9001",
                                "source": "codex_web_seed",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            result = import_prior_work(root, seed_file=seed_path, source="codex_web_seed")
            state = load_session(root)
            citation_map = json.loads(Path(result["citation_map_json"]).read_text(encoding="utf-8"))
            bib = Path(result["references_bib"]).read_text(encoding="utf-8")
            candidates = json.loads(Path(result["candidate_papers_json"]).read_text(encoding="utf-8"))

            self.assertEqual(len(citation_map), 2)
            self.assertIn("The Transport Layer Security Protocol Version 1.3", bib)
            self.assertEqual(candidates["macro_candidates"][0]["discovery_source"], "codex_web_seed")
            self.assertEqual(state.artifacts.references_bib, result["references_bib"])
            self.assertEqual(state.latest_discovery_mode, "codex_web_seed")

    def test_import_prior_work_cli_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            seed_path = root / "prior_work.md"
            seed_path.write_text(
                "- [Protected Channel Interfaces](https://example.test/protected-channel) — 2002\n"
                "- BLAKE3: one function, fast everywhere — 2020\n",
                encoding="utf-8",
            )
            old_cwd = Path.cwd()
            stdout = io.StringIO()
            try:
                os.chdir(root)
                with contextlib.redirect_stdout(stdout):
                    code = cli_main(["import-prior-work", "--seed-file", str(seed_path), "--source", "manual_seed"])
            finally:
                os.chdir(old_cwd)

            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertTrue(Path(payload["references_bib"]).exists())
            state = load_session(root)
            self.assertIsNotNone(state.artifacts.citation_map_json)

    def test_import_prior_work_from_bibtex_preserves_original_keys_for_existing_manuscripts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            seed_path = root / "refs.bib"
            seed_path.write_text(
                "@techreport{RFC8446,\n"
                "  title = {The Transport Layer Security ({TLS}) Protocol Version 1.3},\n"
                "  author = {Eric Rescorla},\n"
                "  year = {2018},\n"
                "  url = {https://www.rfc-editor.org/info/rfc8446}\n"
                "}\n",
                encoding="utf-8",
            )
            result = import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
            citation_map = json.loads(Path(result["citation_map_json"]).read_text(encoding="utf-8"))
            self.assertIn("RFC8446", citation_map)
            self.assertEqual(citation_map["RFC8446"]["url"], "https://www.rfc-editor.org/info/rfc8446")

    def test_import_prior_work_merges_research_seed_without_dropping_source_bibtex_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            manual_seed = root / "manual_refs.bib"
            manual_seed.write_text(
                "@techreport{RFC8446,\n"
                "  title = {The Transport Layer Security ({TLS}) Protocol Version 1.3},\n"
                "  author = {Eric Rescorla},\n"
                "  year = {2018},\n"
                "  url = {https://www.rfc-editor.org/info/rfc8446}\n"
                "}\n"
                "@article{BLAKE3,\n"
                "  title = {BLAKE3: One Function, Fast Everywhere},\n"
                "  author = {Jack O'Connor and Jean-Philippe Aumasson and Samuel Neves and Zooko Wilcox-O'Hearn},\n"
                "  year = {2020},\n"
                "  url = {https://github.com/BLAKE3-team/BLAKE3-specs/blob/master/blake3.pdf}\n"
                "}\n",
                encoding="utf-8",
            )
            research_seed = root / "research_seed.json"
            research_seed.write_text(
                json.dumps(
                    {
                        "references": [
                            {
                                "title": "Protected Channel Interfaces",
                                "authors": ["Phillip Rogaway"],
                                "year": 2002,
                                "venue": "ACM CCS",
                                "source": "codex_web_seed",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            import_prior_work(root, seed_file=manual_seed, source="manual_bibtex")
            result = import_prior_work(root, seed_file=research_seed, source="codex_web_seed")

            citation_map = json.loads(Path(result["citation_map_json"]).read_text(encoding="utf-8"))
            self.assertIn("RFC8446", citation_map)
            self.assertIn("BLAKE3", citation_map)
            self.assertTrue(
                any(
                    str(entry.get("title", "")).lower().startswith("protected channel interfaces")
                    for entry in citation_map.values()
                )
            )
            state = load_session(root)
            self.assertTrue(
                any("merged with and preserved the existing citation registry" in note for note in state.notes)
            )

    def test_verify_papers_live_skips_candidate_errors_and_records_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            candidate_path = artifact_path(root, "candidate_papers.json")
            candidate_path.write_text(
                json.dumps(
                    {
                        "macro_candidates": [
                            {"title_guess": "Rate Limited Paper", "origin_query": "rate limited"},
                            {"title_guess": "Verified Paper", "origin_query": "verified"},
                        ],
                        "micro_candidates": [],
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.candidate_papers_json = str(candidate_path)
            save_session(root, state)
            verified = mock_verified_paper("Verified Paper", abstract_hint="verified", cutoff_date="2024-11-01")

            with patch(
                "paperorchestra.pipeline.verify_candidate_title",
                side_effect=[RuntimeError("Semantic Scholar rate-limited the request (HTTP 429)"), verified],
            ):
                registry_path = verify_papers(root, mode="live", on_error="skip")

            payload = json.loads(Path(registry_path).read_text(encoding="utf-8"))
            state = load_session(root)
            errors = json.loads(Path(state.artifacts.latest_verification_errors_json).read_text(encoding="utf-8"))
            self.assertEqual(len(payload), 1)
            self.assertEqual(errors["error_count"], 1)
            self.assertEqual(errors["errors"][0]["action"], "skipped")
            self.assertIn("SEMANTIC_SCHOLAR_API_KEY", " ".join(errors["recovery_hints"]))

    def test_verify_papers_live_preserves_existing_registry_when_skip_probe_regresses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            seed_path = root / "refs.bib"
            seed_path.write_text(
                "@techreport{RFC8446,\n"
                "  title = {The Transport Layer Security ({TLS}) Protocol Version 1.3},\n"
                "  author = {Eric Rescorla},\n"
                "  year = {2018}\n"
                "}\n\n"
                "@techreport{RFC9001,\n"
                "  title = {Using {TLS} to Secure {QUIC}},\n"
                "  author = {Martin Thomson and Sean Turner},\n"
                "  year = {2021}\n"
                "}\n",
                encoding="utf-8",
            )
            import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
            state = load_session(root)
            candidate_path = artifact_path(root, "candidate_papers.json")
            candidate_path.write_text(
                json.dumps(
                    {
                        "macro_candidates": [
                            {"title_guess": "The Transport Layer Security ({TLS}) Protocol Version 1.3", "origin_query": "tls"},
                            {"title_guess": "Using {TLS} to Secure {QUIC}", "origin_query": "quic"},
                        ],
                        "micro_candidates": [],
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.candidate_papers_json = str(candidate_path)
            save_session(root, state)
            verified = mock_verified_paper("Using {TLS} to Secure {QUIC}", abstract_hint="verified", cutoff_date="2024-11-01")

            with patch(
                "paperorchestra.pipeline.verify_candidate_title",
                side_effect=[RuntimeError("Semantic Scholar rate-limited the request (HTTP 429)"), verified],
            ):
                registry_path = verify_papers(root, mode="live", on_error="skip")

            payload = json.loads(Path(registry_path).read_text(encoding="utf-8"))
            state = load_session(root)
            errors = json.loads(Path(state.artifacts.latest_verification_errors_json).read_text(encoding="utf-8"))
            self.assertEqual(len(payload), 2)
            citation_map = json.loads(Path(state.artifacts.citation_map_json).read_text(encoding="utf-8"))
            self.assertIn("RFC8446", citation_map)
            self.assertIn("RFC9001", citation_map)
            self.assertEqual(errors["error_count"], 1)
            self.assertEqual(state.latest_verify_mode, "live")
            self.assertTrue(any("preserved the prior registry artifacts" in note for note in state.notes))

    def test_verify_papers_live_blocks_when_all_candidates_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            candidate_path = artifact_path(root, "candidate_papers.json")
            candidate_path.write_text(
                json.dumps({"macro_candidates": [{"title_guess": "Only Candidate"}], "micro_candidates": []}),
                encoding="utf-8",
            )
            state.artifacts.candidate_papers_json = str(candidate_path)
            save_session(root, state)

            with patch("paperorchestra.pipeline.verify_candidate_title", side_effect=RuntimeError("HTTP 429")):
                with self.assertRaises(ContractError) as ctx:
                    verify_papers(root, mode="live", on_error="skip")

            state = load_session(root)
            self.assertEqual(state.current_phase, "blocked")
            self.assertIsNotNone(state.artifacts.latest_verification_errors_json)
            self.assertIn("--verify-mode mock", str(ctx.exception))

    def test_verify_papers_live_fail_policy_raises_on_first_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            candidate_path = artifact_path(root, "candidate_papers.json")
            candidate_path.write_text(
                json.dumps(
                    {
                        "macro_candidates": [
                            {"title_guess": "Fail Fast"},
                            {"title_guess": "Never Reached"},
                        ],
                        "micro_candidates": [],
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.candidate_papers_json = str(candidate_path)
            save_session(root, state)

            with patch("paperorchestra.pipeline.verify_candidate_title", side_effect=RuntimeError("HTTP 429")) as verifier:
                with self.assertRaises(ContractError):
                    verify_papers(root, mode="live", on_error="fail")

            self.assertEqual(verifier.call_count, 1)

    def test_verify_papers_live_success_uses_s2_metadata_and_citation_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            candidate_path = artifact_path(root, "candidate_papers.json")
            candidate_path.write_text(
                json.dumps(
                    {
                        "macro_candidates": [
                            {
                                "title_guess": "Protected Channel Interfaces: Relations among Notions and Analysis of Generic Composition",
                                "origin_query": "Bellare Namprempre 2000 protected-channel design",
                            }
                        ],
                        "micro_candidates": [],
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.candidate_papers_json = str(candidate_path)
            save_session(root, state)
            s2_result = {
                "paperId": "s2-paper-id",
                "title": "Protected Channel Interfaces: Relations among Notions and Analysis of Generic Composition",
                "year": 2000,
                "publicationDate": "2000-12-01",
                "venue": "ASIACRYPT",
                "abstract": "Defines protected-channel design notions and analyzes generic composition.",
                "authors": [{"name": "Mihir Bellare"}, {"name": "Chanathip Namprempre"}],
                "citationCount": 1000,
                "externalIds": {"DOI": "10.example/protected-channel"},
                "url": "https://example.test/protected-channel",
            }

            with patch("paperorchestra.literature.search_semantic_scholar", return_value=[s2_result]) as search, patch(
                "paperorchestra.literature.time.sleep", return_value=None
            ) as sleep:
                registry_path = verify_papers(root, mode="live", on_error="fail")

            registry = json.loads(Path(registry_path).read_text(encoding="utf-8"))
            state = load_session(root)
            citation_map = json.loads(Path(state.artifacts.citation_map_json).read_text(encoding="utf-8"))

            self.assertEqual(search.call_count, 1)
            self.assertEqual(sleep.call_count, 1)
            self.assertEqual(len(registry), 1)
            self.assertEqual(registry[0]["paper_id"], "s2-paper-id")
            self.assertEqual(registry[0]["venue"], "ASIACRYPT")
            self.assertEqual(registry[0]["external_ids"]["DOI"], "10.example/protected-channel")
            self.assertEqual(state.latest_verify_mode, "live")
            self.assertIn(registry[0]["bibtex_key"], citation_map)
            self.assertEqual(citation_map[registry[0]["bibtex_key"]]["paper_id"], "s2-paper-id")

    def test_verify_papers_live_filters_after_cutoff_and_deduplicates_paper_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            candidate_path = artifact_path(root, "candidate_papers.json")
            candidate_path.write_text(
                json.dumps(
                    {
                        "macro_candidates": [
                            {"title_guess": "Kept Paper", "origin_query": "Kept Paper 2020"},
                            {"title_guess": "Duplicate Paper", "origin_query": "Duplicate Paper 2020"},
                            {"title_guess": "Too New Paper", "origin_query": "Too New Paper 2025"},
                        ],
                        "micro_candidates": [],
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.candidate_papers_json = str(candidate_path)
            save_session(root, state)
            results = [
                [
                    {
                        "paperId": "shared-id",
                        "title": "Kept Paper",
                        "year": 2020,
                        "publicationDate": "2020-01-01",
                        "abstract": "Abstract.",
                        "authors": [{"name": "A. Author"}],
                    }
                ],
                [
                    {
                        "paperId": "shared-id",
                        "title": "Duplicate Paper",
                        "year": 2020,
                        "publicationDate": "2020-01-01",
                        "abstract": "Abstract.",
                        "authors": [{"name": "B. Author"}],
                    }
                ],
                [
                    {
                        "paperId": "too-new",
                        "title": "Too New Paper",
                        "year": 2025,
                        "publicationDate": "2025-01-02",
                        "abstract": "Abstract.",
                        "authors": [{"name": "C. Author"}],
                    }
                ],
            ]

            with patch("paperorchestra.literature.search_semantic_scholar", side_effect=results), patch(
                "paperorchestra.literature.time.sleep", return_value=None
            ):
                registry_path = verify_papers(root, mode="live", on_error="fail")

            registry = json.loads(Path(registry_path).read_text(encoding="utf-8"))

            self.assertEqual(len(registry), 1)
            self.assertEqual(registry[0]["paper_id"], "shared-id")
            self.assertEqual(registry[0]["title"], "Kept Paper")

    def test_run_pipeline_can_fallback_to_mock_verification_after_live_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            with patch("paperorchestra.pipeline.verify_candidate_title", side_effect=RuntimeError("HTTP 429")):
                result = run_pipeline(
                    root,
                    provider=MockProvider(),
                    discovery_mode="model",
                    verify_mode="live",
                    verify_fallback_mode="mock",
                    refine_iterations=1,
                    compile_paper=False,
                )

            state = load_session(root)
            self.assertEqual(result["verify_fallback_used"], "mock")
            self.assertIn("Live verification produced no verified papers", result["verify_live_error"])
            self.assertIsNotNone(state.artifacts.latest_verification_errors_json)
            self.assertEqual(result["status"], "draft_complete")

    def test_strict_omx_native_disallows_python_fallback(self) -> None:
        old = os.environ.get("PAPERO_STRICT_OMX_NATIVE")
        try:
            os.environ["PAPERO_STRICT_OMX_NATIVE"] = "1"
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self._init_session_with_minimal_inputs(root)
                with patch("paperorchestra.pipeline.omx_exec_json_completion", side_effect=RuntimeError("omx down")):
                    with self.assertRaises(ContractError):
                        generate_outline(root, MockProvider(), runtime_mode="omx_native")
        finally:
            if old is None:
                os.environ.pop("PAPERO_STRICT_OMX_NATIVE", None)
            else:
                os.environ["PAPERO_STRICT_OMX_NATIVE"] = old

    def test_cli_strict_omx_native_returns_distinct_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            old_cwd = Path.cwd()
            err = io.StringIO()
            try:
                os.chdir(root)
                with patch("paperorchestra.pipeline.omx_exec_json_completion", side_effect=RuntimeError("omx down")):
                    with contextlib.redirect_stderr(err):
                        code = cli_main(
                            [
                                "run",
                                "--provider",
                                "mock",
                                "--verify-mode",
                                "mock",
                                "--runtime-mode",
                                "omx_native",
                                "--strict-omx-native",
                                "--refine-iterations",
                                "0",
                            ]
                        )
            finally:
                os.chdir(old_cwd)

            self.assertEqual(code, 2)
            self.assertIn("Strict OMX-native mode forbids fallback", err.getvalue())

    def test_outline_cli_accepts_strict_omx_native_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            old_cwd = Path.cwd()
            err = io.StringIO()
            try:
                os.chdir(root)
                with patch("paperorchestra.pipeline.omx_exec_json_completion", side_effect=RuntimeError("omx down")):
                    with contextlib.redirect_stderr(err):
                        code = cli_main(
                            [
                                "outline",
                                "--provider",
                                "mock",
                                "--runtime-mode",
                                "omx_native",
                                "--strict-omx-native",
                            ]
                        )
            finally:
                os.chdir(old_cwd)
            self.assertEqual(code, 2)
            self.assertIn("Strict OMX-native mode forbids fallback", err.getvalue())

    def test_doctor_report_includes_recovery_hint_for_literature_stall(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            outline_path = artifact_path(root, "outline.json")
            plot_path = artifact_path(root, "plot_manifest.json")
            candidate_path = artifact_path(root, "candidate_papers.json")
            outline_path.write_text("{}", encoding="utf-8")
            plot_path.write_text("{}", encoding="utf-8")
            candidate_path.write_text(json.dumps({"macro_candidates": [], "micro_candidates": []}), encoding="utf-8")
            state.artifacts.outline_json = str(outline_path)
            state.artifacts.plot_manifest_json = str(plot_path)
            state.artifacts.candidate_papers_json = str(candidate_path)
            state.current_phase = "literature_review"
            save_session(root, state)

            report = build_doctor_report(root)
            recovery = report["session_recovery"]
            self.assertEqual(recovery["status"], "actionable")
            self.assertTrue(any("verify-papers --mode live --on-error skip" in command for command in recovery["next_commands"]))

    def test_doctor_treats_compiled_pdf_artifact_as_recovered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper_path = artifact_path(root, "paper.full.tex")
            paper_path.write_text("\\documentclass{article}\\begin{document}ok\\end{document}", encoding="utf-8")
            pdf_path = root / ".paper-orchestra" / "runs" / state.session_id / "build" / "compiled" / "paper.full.pdf"
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            pdf_path.write_bytes(b"%PDF-1.5\n")
            state.artifacts.paper_full_tex = str(paper_path)
            state.artifacts.compiled_pdf = str(pdf_path)
            state.current_phase = "iterative_content_refinement"
            save_session(root, state)

            recovery = build_doctor_report(root)["session_recovery"]
            self.assertEqual(recovery["status"], "ok")
            self.assertFalse(recovery["next_commands"])

    def test_refinement_with_compile_acceptance_marks_session_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            old_compile = os.environ.get("PAPERO_ALLOW_TEX_COMPILE")
            try:
                os.environ["PAPERO_ALLOW_TEX_COMPILE"] = "1"
                run_pipeline(
                    root,
                    provider=MockProvider(),
                    discovery_mode="model",
                    verify_mode="mock",
                    refine_iterations=1,
                    compile_paper=True,
                )
            finally:
                if old_compile is None:
                    os.environ.pop("PAPERO_ALLOW_TEX_COMPILE", None)
                else:
                    os.environ["PAPERO_ALLOW_TEX_COMPILE"] = old_compile
            state = load_session(root)
            self.assertEqual(state.current_phase, "complete")
            self.assertIsNotNone(state.artifacts.compiled_pdf)

    def test_auto_inserted_plot_usage_escapes_percent_in_captions(self) -> None:
        latex = "\\documentclass{article}\n\\begin{document}\n\\end{document}\n"
        plot_assets_index = {
            "assets": [
                {
                    "figure_id": "fig_margin",
                    "caption": "Margin improved from 50% to 68%.",
                    "latex_snippet_path": "build/plot-assets/fig_margin.tex",
                    "filename": "fig_margin.svg",
                }
            ]
        }
        rendered = _ensure_generated_plot_usage(latex, plot_assets_index)
        self.assertIn(r"\caption{Margin improved from 50\% to 68\%.}", rendered)

    def test_auto_inserted_plot_usage_prefers_in_section_anchor_before_conclusion(self) -> None:
        latex = (
            "\\documentclass{article}\n\\begin{document}\n"
            "\\section{Method}\n"
            "We summarize the pipeline in Figure~\\ref{fig_framework_overview}.\n"
            "\\section{Conclusion}\n"
            "Done.\n"
            "\\end{document}\n"
        )
        plot_assets_index = {
            "assets": [
                {
                    "figure_id": "fig_framework_overview",
                    "caption": "Pipeline overview.",
                    "latex_snippet_path": "build/plot-assets/fig_framework_overview.tex",
                    "filename": "fig_framework_overview.svg",
                }
            ]
        }
        rendered = _ensure_generated_plot_usage(latex, plot_assets_index)
        self.assertIn("% PaperOrchestra:auto-repaired figure:fig_framework_overview", rendered)
        self.assertIn("\\begin{figure}[t]", rendered)
        self.assertLess(rendered.index("\\label{fig_framework_overview}"), rendered.index("\\section{Conclusion}"))

    def test_auto_inserted_plot_usage_skips_generated_placeholders(self) -> None:
        latex = "\\documentclass{article}\n\\begin{document}\n\\section{Method}\nDraft.\n\\end{document}\n"
        plot_assets_index = {
            "assets": [
                {
                    "figure_id": "fig_placeholder",
                    "caption": "Placeholder should not be inserted.",
                    "latex_snippet_path": "build/plot-assets/fig_placeholder.tex",
                    "filename": "fig_placeholder.svg",
                    "asset_kind": "generated_placeholder",
                    "review_status": "human_final_artwork_required",
                }
            ]
        }
        rendered = _ensure_generated_plot_usage(latex, plot_assets_index)
        self.assertNotIn("fig_placeholder", rendered)
        issues = validate_manuscript(
            rendered,
            citation_map={},
            figures_dir=None,
            plot_manifest={"figures": [{"figure_id": "fig_placeholder", "caption": "Placeholder should not be inserted."}]},
            plot_assets_index=plot_assets_index,
        )
        self.assertFalse(any(issue.code == "generated_plot_asset_not_used" for issue in issues))

    def test_source_figure_paths_normalize_to_snapshotted_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            figures = Path(tmp) / "figures"
            figures.mkdir()
            (figures / "overview.pdf").write_bytes(b"%PDF-1.5\n")
            latex = r"\includegraphics{figures/overview.pdf}\includegraphics{figs/overview.pdf}\includegraphics{overview.pdf}"
            normalized = _normalize_source_figure_paths(latex, str(figures))
            self.assertEqual(normalized.count("inputs/figures/overview.pdf"), 3)
            self.assertEqual(_normalize_source_figure_paths(normalized, str(figures)), normalized)

    def test_generated_plot_paths_normalize_svg_includegraphics_to_snippet(self) -> None:
        plot_assets_index = {
            "assets": [
                {
                    "figure_id": "fig_speedup",
                    "title": "Speedup",
                    "caption": "Speedup figure.",
                    "latex_snippet_path": "build/plot-assets/fig_speedup.tex",
                    "filename": "fig_speedup.svg",
                }
            ]
        }
        latex = r"\includegraphics[width=0.8\linewidth]{fig_speedup.svg}\includegraphics{build/plot-assets/fig_speedup.tex}"
        normalized = _normalize_generated_plot_paths(latex, plot_assets_index)
        self.assertEqual(
            normalized,
            r"\input{build/plot-assets/fig_speedup.tex}\input{build/plot-assets/fig_speedup.tex}",
        )

    def test_generated_plot_paths_normalize_stem_matched_pdf_include_to_snippet(self) -> None:
        plot_assets_index = {
            "assets": [
                {
                    "figure_id": "fig_encrypt_performance_by_message_size",
                    "title": "Encryption cost across message sizes",
                    "caption": "Cycles per byte across message sizes.",
                    "latex_snippet_path": "build/plot-assets/fig_encrypt_performance_by_message_size.tex",
                    "filename": "fig_encrypt_performance_by_message_size.svg",
                }
            ]
        }
        latex = r"\includegraphics[width=\columnwidth]{figures/fig_encrypt_performance_by_message_size.pdf}"
        normalized = _normalize_generated_plot_paths(latex, plot_assets_index)
        self.assertEqual(
            normalized,
            r"\input{build/plot-assets/fig_encrypt_performance_by_message_size.tex}",
        )

    def test_generated_plot_paths_normalize_label_matched_source_figure_to_snippet(self) -> None:
        plot_assets_index = {
            "assets": [
                {
                    "figure_id": "fig_relative_speedup_short_messages",
                    "title": "Relative speedup of MethodX over standardized protected-channel baselines",
                    "caption": "Short-message speedup comparison.",
                    "latex_snippet_path": "build/plot-assets/fig_relative_speedup_short_messages.tex",
                    "filename": "fig_relative_speedup_short_messages.svg",
                }
            ]
        }
        latex = (
            "\\begin{figure}[t]\n"
            "\\includegraphics[width=\\columnwidth]{inputs/figures/snm_record_protection_overview.pdf}\n"
            "\\caption{Relative speedup of MethodX over standardized protected-channel baselines for short messages.}\n"
            "\\label{fig:relative-speedup-short-messages}\n"
            "\\end{figure}\n"
        )
        normalized = _normalize_generated_plot_paths(latex, plot_assets_index)
        self.assertIn(r"\input{build/plot-assets/fig_relative_speedup_short_messages.tex}", normalized)
        self.assertNotIn("inputs/figures/snm_record_protection_overview.pdf", normalized)

    def test_auto_inserted_plot_usage_skips_when_matching_caption_already_exists(self) -> None:
        latex = (
            "\\documentclass{article}\n\\begin{document}\n"
            "\\section{Experiments}\n"
            "\\begin{figure}[t]\n"
            "\\caption{Cycles per byte across message sizes for standardized protected-channel baselines and MethodX variants at adlen=0.}\n"
            "\\label{fig:encrypt-cost-size}\n"
            "\\end{figure}\n"
            "\\end{document}\n"
        )
        plot_assets_index = {
            "assets": [
                {
                    "figure_id": "fig_encrypt_performance_by_message_size",
                    "caption": "Cycles per byte across message sizes for standardized protected-channel baselines and MethodX variants at adlen=0.",
                    "latex_snippet_path": "build/plot-assets/fig_encrypt_performance_by_message_size.tex",
                    "filename": "fig_encrypt_performance_by_message_size.svg",
                }
            ]
        }
        rendered = _ensure_generated_plot_usage(latex, plot_assets_index)
        self.assertNotIn("PaperOrchestra:auto-repaired figure:fig_encrypt_performance_by_message_size", rendered)

    def test_discover_papers_propagates_runtime_mode_to_lane_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            generate_outline(root, MockProvider())
            payload = {"macro_candidates": [], "micro_candidates": []}
            with patch("paperorchestra.pipeline._build_candidate_payload", return_value=(payload, "python", False, ["stub"])):
                path = discover_papers(root, MockProvider(), mode="model", runtime_mode="omx_native")
            self.assertTrue(Path(path).exists())
            state = load_session(root)
            lane_manifest = json.loads((Path(state.artifacts.outline_json).parent / "lane-manifest.literature.json").read_text(encoding="utf-8"))
            self.assertEqual(lane_manifest["runtime_mode"], "omx_native")

    def test_intro_related_retries_after_citation_contract_failure(self) -> None:
        class CitationRepairProvider(MockProvider):
            def __init__(self, keys: list[str]):
                self.keys = keys
                self.calls = 0

            def complete(self, request: CompletionRequest) -> str:
                self.calls += 1
                if self.calls == 1:
                    cited = self.keys[:1]
                else:
                    cited = self.keys
                cites = ",".join(cited)
                return (
                    "```latex\n"
                    "\\section{Introduction}\n"
                    f"Grounded framing \\\\cite{{{cites}}}.\n"
                    "\\section{Related Work}\n"
                    f"Prior work comparison \\\\cite{{{cites}}}.\n"
                    "```"
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            generate_outline(root, MockProvider())
            discover_papers(root, MockProvider(), mode="model")
            verify_papers(root, mode="mock")
            build_bib(root)
            plan_narrative_and_claims(root, MockProvider())
            state = load_session(root)
            citation_map = json.loads(Path(state.artifacts.citation_map_json).read_text(encoding="utf-8"))
            provider = CitationRepairProvider(list(citation_map.keys()))
            path = write_intro_related(root, provider)
            state = load_session(root)
            validation = json.loads(Path(state.artifacts.latest_validation_json).read_text(encoding="utf-8"))

            self.assertTrue(Path(path).exists())
            self.assertEqual(provider.calls, 2)
            self.assertTrue(validation["ok"])

    def test_intro_related_allows_second_repair_attempt_for_near_miss_citation_coverage(self) -> None:
        class TwoStepCitationRepairProvider(MockProvider):
            def __init__(self, keys: list[str]):
                self.keys = keys
                self.calls = 0

            def complete(self, request: CompletionRequest) -> str:
                self.calls += 1
                if self.calls == 1:
                    cited = self.keys[:1]
                elif self.calls == 2:
                    cited = self.keys[: max(1, len(self.keys) - 1)]
                else:
                    cited = self.keys
                cites = ",".join(cited)
                return (
                    "```latex\n"
                    "\\section{Introduction}\n"
                    f"Grounded framing \\\\cite{{{cites}}}.\n"
                    "\\section{Related Work}\n"
                    f"Prior work comparison \\\\cite{{{cites}}}.\n"
                    "```"
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            generate_outline(root, MockProvider())
            discover_papers(root, MockProvider(), mode="model")
            verify_papers(root, mode="mock")
            build_bib(root)
            plan_narrative_and_claims(root, MockProvider())
            state = load_session(root)
            citation_map = json.loads(Path(state.artifacts.citation_map_json).read_text(encoding="utf-8"))
            provider = TwoStepCitationRepairProvider(list(citation_map.keys()))
            path = write_intro_related(root, provider)
            state = load_session(root)
            validation = json.loads(Path(state.artifacts.latest_validation_json).read_text(encoding="utf-8"))

            self.assertTrue(Path(path).exists())
            self.assertEqual(provider.calls, 3)
            self.assertTrue(validation["ok"])
            lane_manifest = json.loads((artifact_path(root, "placeholder").parent / "lane-manifest.intro_related.json").read_text(encoding="utf-8"))
            self.assertTrue(
                any("repair attempt 2" in note for note in lane_manifest.get("notes") or []),
                lane_manifest.get("notes"),
            )

    def test_intro_related_retries_after_numeric_grounding_failure(self) -> None:
        class NumericRepairProvider(MockProvider):
            def __init__(self, keys: list[str]):
                self.keys = keys
                self.calls = 0

            def complete(self, request: CompletionRequest) -> str:
                self.calls += 1
                cites = ",".join(self.keys)
                numeric = "99.9%" if self.calls == 1 else "grounded"
                return (
                    "```latex\n"
                    "\\section{Introduction}\n"
                    f"Grounded framing {numeric} \\\\cite{{{cites}}}.\n"
                    "\\section{Related Work}\n"
                    f"Prior work comparison {numeric} \\\\cite{{{cites}}}.\n"
                    "```"
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            generate_outline(root, MockProvider())
            discover_papers(root, MockProvider(), mode="model")
            verify_papers(root, mode="mock")
            build_bib(root)
            plan_narrative_and_claims(root, MockProvider())
            state = load_session(root)
            citation_map = json.loads(Path(state.artifacts.citation_map_json).read_text(encoding="utf-8"))
            provider = NumericRepairProvider(list(citation_map.keys()))
            path = write_intro_related(root, provider)
            state = load_session(root)
            validation = json.loads(Path(state.artifacts.latest_validation_json).read_text(encoding="utf-8"))

            self.assertTrue(Path(path).exists())
            self.assertEqual(provider.calls, 2)
            self.assertTrue(validation["ok"])

    def test_intro_related_allows_source_template_numbers_outside_rewrite_scope(self) -> None:
        class SourceNumberIntroProvider(MockProvider):
            def __init__(self, keys: list[str]):
                self.keys = keys

            def complete(self, request: CompletionRequest) -> str:
                cites = ",".join(self.keys)
                return (
                    "```latex\n"
                    "\\documentclass{article}\n"
                    "\\usepackage{graphicx}\n"
                    "\\begin{document}\n"
                    "\\section{Introduction}\n"
                    f"Grounded framing \\\\cite{{{cites}}}.\n"
                    "\\section{Related Work}\n"
                    f"Prior work comparison \\\\cite{{{cites}}}.\n"
                    "\\section{Method}\n"
                    "Human source benchmark value 24.04 must be preserved.\n"
                    "\\end{document}\n"
                    "```"
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            state = load_session(root)
            Path(state.inputs.template_path).write_text(
                "\\documentclass{article}\n"
                "\\usepackage{graphicx}\n"
                "\\begin{document}\n"
                "\\section{Introduction}\n"
                "\\section{Related Work}\n"
                "\\section{Method}\n"
                "Human source benchmark value 24.04 must be preserved.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            generate_outline(root, MockProvider())
            discover_papers(root, MockProvider(), mode="model")
            verify_papers(root, mode="mock")
            build_bib(root)
            plan_narrative_and_claims(root, MockProvider())
            state = load_session(root)
            citation_map = json.loads(Path(state.artifacts.citation_map_json).read_text(encoding="utf-8"))
            path = write_intro_related(root, SourceNumberIntroProvider(list(citation_map.keys())))
            latex = Path(path).read_text(encoding="utf-8")
            validation = json.loads(Path(load_session(root).artifacts.latest_validation_json).read_text(encoding="utf-8"))

            self.assertTrue(validation["ok"])
            self.assertIn("24.04", latex)

    def test_material_packet_sections_are_removed_but_macros_are_preserved(self) -> None:
        latex = (
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "\\section{00 core macros}\n"
            "\\newcommand{\\METHODX}{\\mathsf{MethodX}}\n"
            "\\newcommand{\\EncKey}{K_E}\n"
            "\\newcommand{\\AuthKey}{K_A}\n"
            "Visible macro notes.\n"
            "\\section{Method}\n"
            "Use \\METHODX{} with \\EncKey{} and \\AuthKey{} here.\n"
            "\\section{Claim Boundaries for the MethodX Draft}\n"
            "This draft is not camera-ready.\n"
            "\\section{Author Notes for Positioning and Framing}\n"
            "Operator-only note.\n"
            "\\section{Conclusion}\n"
            "Done.\n"
            "\\end{document}\n"
        )

        cleaned = _remove_material_packet_sections(latex)

        self.assertIn("\\newcommand{\\METHODX}", cleaned)
        self.assertIn("\\newcommand{\\EncKey}{\\ensuremath{K_E}}", cleaned)
        self.assertIn("\\newcommand{\\AuthKey}{\\ensuremath{K_A}}", cleaned)
        self.assertNotIn("\\section{00 core macros}", cleaned)
        self.assertNotIn("Visible macro notes", cleaned)
        self.assertNotIn("Claim Boundaries for the MethodX Draft", cleaned)
        self.assertNotIn("Author Notes for Positioning and Framing", cleaned)
        self.assertIn("\\section{Method}", cleaned)
        self.assertIn("\\section{Conclusion}", cleaned)

    def test_domain_neutral_material_packet_sections_are_removed(self) -> None:
        latex = (
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "\\section{Method}\n"
            "Method text.\n"
            "\\section{Claim Boundaries for the Example Draft}\n"
            "Operator-only boundary notes.\n"
            "\\section{Author Notes for Example Framing}\n"
            "Operator-only author notes.\n"
            "\\section{Conclusion}\n"
            "Done.\n"
            "\\end{document}\n"
        )

        cleaned = _remove_material_packet_sections(latex)

        self.assertNotIn("Claim Boundaries for the Example Draft", cleaned)
        self.assertNotIn("Author Notes for Example Framing", cleaned)
        self.assertNotIn("Operator-only", cleaned)
        self.assertIn("\\section{Method}", cleaned)
        self.assertIn("\\section{Conclusion}", cleaned)

    def test_intro_related_preserves_non_target_sections_from_template(self) -> None:
        class OvereagerIntroProvider(MockProvider):
            def __init__(self, keys: list[str]):
                self.keys = keys
                self.calls = 0

            def complete(self, request: CompletionRequest) -> str:
                self.calls += 1
                cites = ",".join(self.keys)
                return (
                    "```latex\n"
                    "\\documentclass{article}\n"
                    "\\usepackage{graphicx}\n"
                    "\\begin{document}\n"
                    "\\section{Introduction}\n"
                    f"Grounded framing \\\\cite{{{cites}}}.\n"
                    "\\section{Related Work}\n"
                    f"Prior work comparison \\\\cite{{{cites}}}.\n"
                    "\\section{Method}\n"
                    "This off-scope section should be discarded along with 99.9% and 120.9.\n"
                    "\\end{document}\n"
                    "```"
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            generate_outline(root, MockProvider())
            discover_papers(root, MockProvider(), mode="model")
            verify_papers(root, mode="mock")
            build_bib(root)
            plan_narrative_and_claims(root, MockProvider())
            state = load_session(root)
            citation_map = json.loads(Path(state.artifacts.citation_map_json).read_text(encoding="utf-8"))
            provider = OvereagerIntroProvider(list(citation_map.keys()))
            path = write_intro_related(root, provider)
            latex = Path(path).read_text(encoding="utf-8")
            validation = json.loads(Path(load_session(root).artifacts.latest_validation_json).read_text(encoding="utf-8"))

            self.assertTrue(Path(path).exists())
            self.assertEqual(provider.calls, 1)
            self.assertTrue(validation["ok"])
            self.assertNotIn("99.9", latex)
            self.assertNotIn("120.9", latex)
            self.assertNotIn("This off-scope section should be discarded", latex)
            self.assertNotIn("PaperOrchestra writes this", latex)
            self.assertIn("\\section{Method}\n", latex)

    def test_section_writer_retries_after_citation_contract_failure(self) -> None:
        class SectionCitationRepairProvider(MockProvider):
            def __init__(self):
                self.calls = 0

            def complete(self, request: CompletionRequest) -> str:
                self.calls += 1
                if self.calls == 1:
                    return """```latex
\\documentclass{article}
\\usepackage{graphicx}
\\begin{document}
\\section{Introduction}
Minimal framing.
\\section{Related Work}
Minimal comparison.
\\section{Method}
The pipeline references Figure~\\ref{fig_framework_overview}.
\\begin{figure}
\\input{build/plot-assets/fig_framework_overview.tex}
\\caption{Overview of the staged pipeline.}
\\label{fig_framework_overview}
\\end{figure}
\\section{Experiments}
Grounded evaluation.
\\section{Conclusion}
Done \\cite{bogus_key}.
\\end{document}
```"""
                return super().complete(request)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            Path(state.inputs.idea_path).write_text(
                "The method pipeline converts inputs into an outline, then plot and literature lanes feed the writer.\n",
                encoding="utf-8",
            )
            generate_outline(root, MockProvider())
            generate_plots(root, MockProvider())
            discover_papers(root, MockProvider(), mode="model")
            verify_papers(root, mode="mock")
            build_bib(root)
            plan_narrative_and_claims(root, MockProvider())
            provider = SectionCitationRepairProvider()
            path = write_sections(root, provider)
            state = load_session(root)
            validation = json.loads(Path(state.artifacts.latest_validation_json).read_text(encoding="utf-8"))

            self.assertTrue(Path(path).exists())
            self.assertEqual(provider.calls, 2)
            self.assertTrue(validation["ok"])

    def test_refinement_rejects_score_regression(self) -> None:
        class RegressiveProvider(MockProvider):
            def complete(self, request: CompletionRequest) -> str:
                if "content refinement agent" in request.system_prompt.lower():
                    return """```json
{
  "addressed_weaknesses": ["None"],
  "integrated_answers": ["None"],
  "actions_taken": ["Made it worse"]
}
```
```latex
\\documentclass{article}
\\begin{document}
Regressed mock paper.
\\section{Method}
The regressed mock paper keeps enough method text to satisfy structural validation while still losing review score. It mentions a staged pipeline, artifacts, validation, and review gates without improving the manuscript.
\\end{document}
```
"""
                return super().complete(request)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            provider = MockProvider()
            generate_outline(root, provider)
            generate_plots(root, provider)
            plan_narrative_and_claims(root, provider)
            write_sections(root, provider)
            review_current_paper(root, provider)
            result = refine_current_paper(root, RegressiveProvider(), iterations=1)
            self.assertFalse(result[0]["accepted"])
            state = load_session(root)
            self.assertEqual(state.refinement_iteration, 0)

    def test_run_pipeline_preserves_previous_draft_when_refinement_regresses_contract(self) -> None:
        class RegressiveProvider(MockProvider):
            def complete(self, request: CompletionRequest) -> str:
                if "content refinement agent" in request.system_prompt.lower():
                    return """```json
{
  "addressed_weaknesses": ["None"],
  "integrated_answers": ["None"],
  "actions_taken": ["Made it worse"]
}
```
```latex
\\documentclass{article}
\\begin{document}
Regressed mock paper.
\\end{document}
```
"""
                return super().complete(request)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            result = run_pipeline(
                root,
                provider=RegressiveProvider(),
                discovery_mode="model",
                verify_mode="mock",
                refine_iterations=1,
                compile_paper=False,
            )
            self.assertEqual(result["status"], "draft_complete")
            state = load_session(root)
            self.assertEqual(state.current_phase, "draft_complete")

    def test_refinement_accepts_after_small_regression_retry_confirms_non_regression(self) -> None:
        class RetryTolerantProvider(MockProvider):
            def __init__(self) -> None:
                self.review_calls = 0

            def complete(self, request: CompletionRequest) -> str:
                system = request.system_prompt.lower()
                if "skeptical academic reviewer" in system:
                    self.review_calls += 1
                    if self.review_calls == 1:
                        return json.dumps(
                            {
                                "paper_title": "Demo",
                                "citation_statistics": {
                                    "estimated_unique_citations": 10,
                                    "citation_density_assessment": "appropriate",
                                    "breadth_across_subareas": "moderate",
                                    "comparison_to_baseline": "baseline",
                                    "notes": "baseline review",
                                },
                                "axis_scores": {"coverage_and_completeness": {"score": 6, "justification": "baseline review"}},
                                "penalties": [],
                                "summary": {"strengths": [], "weaknesses": [], "top_improvements": []},
                                "questions": [],
                                "overall_score": 6,
                            }
                        )
                    if self.review_calls == 2:
                        return json.dumps(
                            {
                                "paper_title": "Demo",
                                "citation_statistics": {
                                    "estimated_unique_citations": 10,
                                    "citation_density_assessment": "appropriate",
                                    "breadth_across_subareas": "moderate",
                                    "comparison_to_baseline": "temporary drop",
                                    "notes": "temporary noisy drop",
                                },
                                "axis_scores": {"coverage_and_completeness": {"score": 5, "justification": "temporary noisy drop"}},
                                "penalties": [],
                                "summary": {"strengths": [], "weaknesses": [], "top_improvements": []},
                                "questions": [],
                                "overall_score": 5,
                            }
                        )
                    return json.dumps(
                        {
                            "paper_title": "Demo",
                            "citation_statistics": {
                                "estimated_unique_citations": 10,
                                "citation_density_assessment": "appropriate",
                                "breadth_across_subareas": "moderate",
                                "comparison_to_baseline": "retry confirms parity",
                                "notes": "retry confirms parity",
                            },
                            "axis_scores": {"coverage_and_completeness": {"score": 6, "justification": "retry confirms parity"}},
                            "penalties": [],
                            "summary": {"strengths": [], "weaknesses": [], "top_improvements": []},
                            "questions": [],
                            "overall_score": 6,
                        }
                    )
                if "content refinement agent" in system:
                    return """```json
{
  "addressed_weaknesses": ["Clarified novelty"],
  "integrated_answers": ["Stayed conservative"],
  "actions_taken": ["Revised introduction"]
}
```
```latex
\\documentclass{article}
\\begin{document}
Refined but valid paper.
\\section{Method}
This refinement keeps the method section substantive by restating the staged artifact flow, the validated citation contract, and the generated-asset handoff in enough detail to satisfy section-coverage validation.
\\end{document}
```"""
                return super().complete(request)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            provider = RetryTolerantProvider()
            generate_outline(root, provider)
            generate_plots(root, provider)
            plan_narrative_and_claims(root, provider)
            write_sections(root, provider)
            review_current_paper(root, provider)
            result = refine_current_paper(root, provider, iterations=1)
            self.assertTrue(result[0]["accepted"])
            self.assertEqual(result[0]["score_before"], 6.0)
            self.assertEqual(result[0]["score_after"], 6.0)
            self.assertEqual(result[0]["review_retry_scores"], [6.0])

    def test_cli_refine_returns_nonzero_on_compile_required_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(
                root,
                provider=MockProvider(),
                discovery_mode="model",
                verify_mode="mock",
                refine_iterations=1,
                compile_paper=False,
            )
            old_cwd = Path.cwd()
            old_compile_env = os.environ.get("PAPERO_ALLOW_TEX_COMPILE")
            try:
                os.environ.pop("PAPERO_ALLOW_TEX_COMPILE", None)
                os.chdir(root)
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    code = cli_main(["refine", "--provider", "mock", "--iterations", "1", "--require-compile-for-accept"])
            finally:
                os.chdir(old_cwd)
                if old_compile_env is None:
                    os.environ.pop("PAPERO_ALLOW_TEX_COMPILE", None)
                else:
                    os.environ["PAPERO_ALLOW_TEX_COMPILE"] = old_compile_env
            self.assertEqual(code, 1)

    def test_refine_result_includes_validation_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(
                root,
                provider=MockProvider(),
                discovery_mode="model",
                verify_mode="mock",
                refine_iterations=1,
                compile_paper=False,
            )
            result = refine_current_paper(root, MockProvider(), iterations=1)
            self.assertIn("validation_report_path", result[0])
            self.assertIn("validation_report", result[0])
            self.assertTrue(Path(result[0]["validation_report_path"]).exists())

    def test_refinement_accepts_latex_only_response_with_synthesized_worklog(self) -> None:
        class LatexOnlyRefinementProvider(MockProvider):
            def complete(self, request: CompletionRequest) -> str:
                system = request.system_prompt.lower()
                if "content refinement agent" in system or "two distinct code blocks" in system:
                    return self._mock_latex_document(request, refined=True)
                return super().complete(request)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(
                root,
                provider=MockProvider(),
                discovery_mode="model",
                verify_mode="mock",
                refine_iterations=1,
                compile_paper=False,
            )
            result = refine_current_paper(root, LatexOnlyRefinementProvider(), iterations=1)
            self.assertTrue(result[0]["accepted"])
            worklog = json.loads(Path(result[0]["worklog_path"]).read_text(encoding="utf-8"))
            self.assertIn("actions_taken", worklog)
            self.assertIn("LaTeX-only fallback", worklog["actions_taken"][0])

    def test_refinement_preserves_previous_manuscript_when_revision_regresses_citation_contract(self) -> None:
        class CitationDroppingRefiner(MockProvider):
            def complete(self, request: CompletionRequest) -> str:
                system = request.system_prompt.lower()
                if "content refinement agent" in system or "two distinct code blocks" in system:
                    return """```latex
\\documentclass{article}
\\usepackage{graphicx}
\\begin{document}
\\section{Introduction}
Refined wording without citations.
\\section{Related Work}
Refined wording without citations.
\\section{Method}
Refined wording without citations.
\\end{document}
```"""
                return super().complete(request)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(
                root,
                provider=MockProvider(),
                discovery_mode="model",
                verify_mode="mock",
                refine_iterations=1,
                compile_paper=False,
            )
            before = load_session(root)
            original_paper = Path(before.artifacts.paper_full_tex).read_text(encoding="utf-8")
            result = refine_current_paper(root, CitationDroppingRefiner(), iterations=1)
            after = load_session(root)
            final_paper = Path(after.artifacts.paper_full_tex).read_text(encoding="utf-8")
            worklog = json.loads(Path(result[0]["worklog_path"]).read_text(encoding="utf-8"))

            self.assertTrue(result[0]["accepted"])
            self.assertEqual(final_paper, original_paper)
            self.assertTrue(
                any("Preserved the pre-refinement manuscript" in item for item in worklog.get("actions_taken", []))
            )

    def test_refinement_preserves_previous_compiled_manuscript_when_revision_fails_compile(self) -> None:
        class CompileBreakingRefiner(MockProvider):
            def complete(self, request: CompletionRequest) -> str:
                system = request.system_prompt.lower()
                if "content refinement agent" in system or "two distinct code blocks" in system:
                    return """```latex
\\documentclass{article}
\\begin{document}
\\section{Introduction}
Compile-breaking refinement.
\\end{document}
```"""
                return super().complete(request)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(
                root,
                provider=MockProvider(),
                discovery_mode="model",
                verify_mode="mock",
                refine_iterations=1,
                compile_paper=False,
            )
            state = load_session(root)
            compile_report = root / "compile-report.json"
            compile_report.write_text(
                json.dumps(
                    {
                        "pdf_path": str(root / "paper.full.pdf"),
                        "log_path": str(root / "latex-build.log"),
                        "return_code": 0,
                        "pdf_exists": True,
                        "clean": True,
                        "warning_summary": [],
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.latest_compile_report_json = str(compile_report)
            state.artifacts.compiled_pdf = str(root / "paper.full.pdf")
            from paperorchestra.session import save_session
            save_session(root, state)

            original_paper = Path(state.artifacts.paper_full_tex).read_text(encoding="utf-8")
            with patch("paperorchestra.pipeline.compile_latex", side_effect=RuntimeError("compile failed")):
                result = refine_current_paper(
                    root,
                    CompileBreakingRefiner(),
                    iterations=1,
                    require_compile_for_accept=True,
                )
            after = load_session(root)
            final_paper = Path(after.artifacts.paper_full_tex).read_text(encoding="utf-8")
            worklog = json.loads(Path(result[0]["worklog_path"]).read_text(encoding="utf-8"))

            self.assertTrue(result[0]["accepted"])
            self.assertEqual(final_paper, original_paper)
            self.assertIn("actions_taken", worklog)

    def test_refine_emits_preservation_summary_to_stderr(self) -> None:
        class RegressiveProvider(MockProvider):
            def complete(self, request: CompletionRequest) -> str:
                if "content refinement agent" in request.system_prompt.lower():
                    return """```json
{
  "addressed_weaknesses": ["None"],
  "integrated_answers": ["None"],
  "actions_taken": ["Made it worse"]
}
```
```latex
\\documentclass{article}
\\begin{document}
Regressed mock paper.
\\section{Method}
The regressed mock paper keeps enough method text to satisfy structural validation while still losing review score. It mentions a staged pipeline, artifacts, validation, and review gates without improving the manuscript.
\\end{document}
```"""
                return super().complete(request)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(
                root,
                provider=MockProvider(),
                discovery_mode="model",
                verify_mode="mock",
                refine_iterations=1,
                compile_paper=False,
            )
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result = refine_current_paper(root, RegressiveProvider(), iterations=1)
            self.assertTrue(result[0]["accepted"])
            self.assertIn("preserved prior manuscript", stderr.getvalue())

    def test_fidelity_audit_report_is_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(
                root,
                provider=MockProvider(),
                discovery_mode="model",
                verify_mode="mock",
                refine_iterations=1,
                compile_paper=False,
            )
            path, payload = record_fidelity_report(root)
            self.assertTrue(path.exists())
            self.assertIn("overall_status", payload)
            self.assertTrue(payload["checks"])
            codes = {check["code"] for check in payload["checks"]}
            self.assertIn("agentreview_substitute_surface", codes)
            self.assertIn("review_gate_comparison_surface", codes)
            self.assertIn("search_grounding_substitute_surface", codes)
            self.assertIn("benchmark_eval_surface", codes)
            self.assertIn("generated_citation_title_surface", codes)
            self.assertIn("citation_partition_scaffold_surface", codes)

    def test_fidelity_audit_detects_repo_pdf_and_eval_artifacts_after_scaffold_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(
                root,
                provider=MockProvider(),
                discovery_mode="search-grounded",
                verify_mode="mock",
                refine_iterations=1,
                compile_paper=False,
            )

            reference_dir = root / "reference"
            reference_dir.mkdir()
            (reference_dir / "seed_answers.json").write_text(
                json.dumps(
                    {
                        "baselines": ["Single Agent", "AI Scientist-v2"],
                        "datasets_or_benchmarks": ["PaperWritingBench (200 papers from CVPR 2025 and ICLR 2025)"],
                    }
                ),
                encoding="utf-8",
            )
            (reference_dir / "results.md").write_text(
                "Absolute win-rate margins of 50%–68% in literature review quality and 14%–38% in overall manuscript quality.",
                encoding="utf-8",
            )
            (reference_dir / "methodology.md").write_text("Method excerpt", encoding="utf-8")
            (reference_dir / "task_and_dataset.md").write_text("Task excerpt", encoding="utf-8")
            (reference_dir / "template.tex").write_text("\\documentclass{article}\n", encoding="utf-8")
            source_pdf = reference_dir / "paperorchestra-reference.pdf"
            source_pdf.write_bytes(b"%PDF-1.4\n% mock reference pdf\n")
            reference_case = write_reference_benchmark_case(
                reference_dir, reference_dir / "benchmark_case.json", source_pdf=source_pdf
            )

            old_reference_pdf = os.environ.get("PAPERO_REFERENCE_PDF")
            os.environ["PAPERO_REFERENCE_PDF"] = str(source_pdf)
            try:
                state = load_session(root)
                artifact_dir = Path(state.artifacts.paper_full_tex).resolve().parent
                write_session_eval_summary(root, artifact_dir / "session_eval_summary.json")
                write_review_gate_comparison(root, artifact_dir / "review_gate_comparison.json")
                write_generated_citation_titles(root, artifact_dir / "generated_citation_titles.json")
                write_reference_comparison(reference_case, root, artifact_dir / "reference_comparison.json")
                write_reference_case_partition_scaffold(reference_case, artifact_dir / "reference_case_partition_scaffold.json")
                write_reference_case_partitioned_citation_coverage(
                    reference_case, root, artifact_dir / "reference_case_partitioned_citation_coverage.json"
                )

                _, payload = record_fidelity_report(root)
                statuses = {check["code"]: check["status"] for check in payload["checks"]}
                self.assertEqual(statuses["paper_source_present"], "implemented")
                self.assertEqual(statuses["benchmark_eval_surface"], "implemented")
                self.assertEqual(statuses["generated_citation_title_surface"], "implemented")
                self.assertEqual(statuses["citation_partition_scaffold_surface"], "implemented")
                summary = json.loads(
                    write_session_eval_summary(root, artifact_dir / "session_eval_summary.json").read_text(encoding="utf-8")
                )
                self.assertEqual(summary["fidelity_overall_status"], "partial")
            finally:
                if old_reference_pdf is None:
                    os.environ.pop("PAPERO_REFERENCE_PDF", None)
                else:
                    os.environ["PAPERO_REFERENCE_PDF"] = old_reference_pdf

    def test_compile_environment_report_is_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            path, payload = record_compile_environment_report(root)
            self.assertTrue(path.exists())
            self.assertIn("ready_for_compile", payload)
            self.assertIn("install_commands", payload)
            self.assertIn("bootstrap_script_path", payload)
            self.assertIn("user_space_probe", payload)
            self.assertIn("cargo_available", payload["user_space_probe"])

    def test_check_compile_env_cli_works_without_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_cwd = Path.cwd()
            stdout = io.StringIO()
            try:
                os.chdir(root)
                with contextlib.redirect_stdout(stdout):
                    code = cli_main(["check-compile-env"])
            finally:
                os.chdir(old_cwd)
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertTrue(Path(payload["path"]).exists())
            self.assertIn(".paper-orchestra/preflight/compile-environment.json", payload["path"])
            self.assertIn("ready_for_compile", payload["report"])

    def test_status_summary_highlights_main_outputs_and_next_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\\begin{document}ok\\end{document}\n", encoding="utf-8")
            review = review_path(root, "review.latest.json")
            review.write_text('{"overall_score": 0.8}\n', encoding="utf-8")
            repro = artifact_path(root, "reproducibility.audit.json")
            repro.write_text('{"verdict": "BLOCK"}\n', encoding="utf-8")
            state.current_phase = "draft_complete"
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.latest_review_json = str(review)
            state.artifacts.latest_reproducibility_json = str(repro)
            save_session(root, state)
            old_cwd = Path.cwd()
            stdout = io.StringIO()
            try:
                os.chdir(root)
                with contextlib.redirect_stdout(stdout):
                    code = cli_main(["status", "--summary"])
            finally:
                os.chdir(old_cwd)

        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn(f"Session: {state.session_id}", output)
        self.assertIn("Phase: draft_complete", output)
        self.assertIn(str(paper), output)
        self.assertIn(str(review), output)
        self.assertIn("paperorchestra check-compile-env", output)

    def test_export_artifacts_copies_current_main_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\\begin{document}ok\\end{document}\n", encoding="utf-8")
            pdf = root / ".paper-orchestra" / "runs" / state.session_id / "build" / "compiled" / "paper.full.pdf"
            pdf.parent.mkdir(parents=True)
            pdf.write_bytes(b"%PDF-1.5\n")
            refs = artifact_path(root, "references.bib")
            refs.write_text("@article{x,title={X}}\n", encoding="utf-8")
            review = review_path(root, "review.latest.json")
            review.write_text('{"overall_score": 0.8}\n', encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.compiled_pdf = str(pdf)
            state.artifacts.references_bib = str(refs)
            state.artifacts.latest_review_json = str(review)
            save_session(root, state)
            out_dir = root / "out"
            old_cwd = Path.cwd()
            stdout = io.StringIO()
            try:
                os.chdir(root)
                with contextlib.redirect_stdout(stdout):
                    code = cli_main(["export-artifacts", "--output", str(out_dir), "--include-all-artifacts", "--json"])
            finally:
                os.chdir(old_cwd)
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["status"], "ok")
            self.assertTrue((out_dir / "paper.full.tex").exists())
            self.assertTrue((out_dir / "paper.full.pdf").exists())
            self.assertTrue((out_dir / "references.bib").exists())
            self.assertTrue((out_dir / "review.latest.json").exists())
            self.assertTrue((out_dir / "session.json").exists())
            self.assertTrue((out_dir / "artifacts" / "paper.full.tex").exists())

    def test_compile_env_bootstrap_uses_root_commands_without_sudo(self) -> None:
        def fake_which(name: str) -> str | None:
            return "/usr/bin/apt-get" if name == "apt-get" else None

        with tempfile.TemporaryDirectory() as tmp, patch("paperorchestra.compile_env.os.geteuid", return_value=0), patch(
            "paperorchestra.compile_env.shutil.which", side_effect=fake_which
        ):
            report = compile_env_module.inspect_compile_environment(tmp, auto_configure_wrapper=False)
            self.assertTrue(report.bootstrap_script_path)
            script = Path(report.bootstrap_script_path).read_text(encoding="utf-8")

        self.assertTrue(report.install_context["is_root"])
        self.assertEqual(report.install_commands[0], "apt-get update")
        self.assertTrue(all(not command.startswith("sudo ") for command in report.install_commands))
        self.assertEqual(report.fallback_install_commands, ["apt-get install -y firejail"])
        self.assertEqual(report.omx_optional_install_commands, ["apt-get install -y xz-utils"])
        self.assertIn("apt-get update", script)
        self.assertNotIn("sudo apt-get", script)

    def test_compile_env_bootstrap_warns_when_non_root_without_sudo(self) -> None:
        def fake_which(name: str) -> str | None:
            return "/usr/bin/apt-get" if name == "apt-get" else None

        with tempfile.TemporaryDirectory() as tmp, patch("paperorchestra.compile_env.os.geteuid", return_value=1000), patch(
            "paperorchestra.compile_env.shutil.which", side_effect=fake_which
        ):
            report = compile_env_module.inspect_compile_environment(tmp, auto_configure_wrapper=False)
            self.assertTrue(report.bootstrap_script_path)
            script = Path(report.bootstrap_script_path).read_text(encoding="utf-8")

        self.assertFalse(report.install_context["is_root"])
        self.assertFalse(report.install_context["sudo_available"])
        self.assertEqual(report.install_commands, [])
        self.assertTrue(any("root privileges" in note and "sudo is not available" in note for note in report.notes))
        self.assertIn("requires root privileges or sudo", script)

    def test_compile_env_bootstrap_keeps_brew_user_space_commands_without_sudo(self) -> None:
        def fake_which(name: str) -> str | None:
            return "/opt/homebrew/bin/brew" if name == "brew" else None

        with tempfile.TemporaryDirectory() as tmp, patch("paperorchestra.compile_env.os.geteuid", return_value=1000), patch(
            "paperorchestra.compile_env.shutil.which", side_effect=fake_which
        ):
            report = compile_env_module.inspect_compile_environment(tmp, auto_configure_wrapper=False)

        self.assertFalse(report.install_context["is_root"])
        self.assertFalse(report.install_context["sudo_available"])
        self.assertEqual(report.install_commands[0], "brew install --cask mactex-no-gui || brew install basictex")
        self.assertTrue(all(not command.startswith("sudo ") for command in report.install_commands))

    def test_compile_env_bootstrap_uses_sudo_when_available(self) -> None:
        def fake_which(name: str) -> str | None:
            return {
                "apt-get": "/usr/bin/apt-get",
                "sudo": "/usr/bin/sudo",
            }.get(name)

        def fake_run(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
            self.assertEqual(command, ["/usr/bin/sudo", "-n", "true"])
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as tmp, patch("paperorchestra.compile_env.os.geteuid", return_value=1000), patch(
            "paperorchestra.compile_env.shutil.which", side_effect=fake_which
        ), patch("paperorchestra.compile_env.subprocess.run", side_effect=fake_run):
            report = compile_env_module.inspect_compile_environment(tmp, auto_configure_wrapper=False)

        self.assertTrue(report.install_context["sudo_available"])
        self.assertTrue(report.install_context["sudo_usable"])
        self.assertTrue(report.install_context["can_run_install_commands_directly"])
        self.assertEqual(report.install_commands[0], "sudo apt-get update")
        self.assertEqual(report.fallback_install_commands, ["sudo apt-get install -y firejail"])
        self.assertEqual(report.omx_optional_install_commands, ["sudo apt-get install -y xz-utils"])

    def test_sandbox_detection_skips_installed_but_unusable_bwrap(self) -> None:
        def fake_which(name: str) -> str | None:
            return {
                "bwrap": "/usr/bin/bwrap",
                "firejail": "/usr/bin/firejail",
            }.get(name)

        def fake_run(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
            if command[0] == "/usr/bin/bwrap":
                return subprocess.CompletedProcess(
                    command,
                    1,
                    stdout="",
                    stderr=(
                        "bwrap: No permissions to create new namespace, "
                        "likely because the kernel does not allow non-privileged user namespaces."
                    ),
                )
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            with patch("paperorchestra.compile_env.shutil.which", side_effect=fake_which), patch(
                "paperorchestra.compile_env.subprocess.run", side_effect=fake_run
            ):
                self.assertEqual(compile_env_module.detect_sandbox_tool(), "/usr/bin/firejail")
                report = compile_env_module.inspect_compile_environment(tmp, auto_configure_wrapper=False)

        self.assertEqual(report.sandbox_tool, "/usr/bin/firejail")
        self.assertTrue(any("bwrap" in note and "failed usability probe" in note for note in report.notes))
        self.assertTrue(any("Selected sandbox tool: /usr/bin/firejail" == note for note in report.notes))

    def test_sandbox_detection_rejects_unusable_sandbox_tools(self) -> None:
        def fake_which(name: str) -> str | None:
            return "/usr/bin/bwrap" if name == "bwrap" else None

        def fake_run(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="namespace creation denied")

        with patch("paperorchestra.compile_env.shutil.which", side_effect=fake_which), patch(
            "paperorchestra.compile_env.subprocess.run", side_effect=fake_run
        ):
            self.assertIsNone(compile_env_module.detect_sandbox_tool())
            report = compile_env_module.inspect_compile_environment(Path("."), auto_configure_wrapper=False)

        self.assertIsNone(report.sandbox_tool)
        self.assertTrue(any("No supported sandbox tool passed runtime usability probe" in note for note in report.notes))

    def test_compile_latex_supports_tectonic_backend(self) -> None:
        old_allow = os.environ.get("PAPERO_ALLOW_TEX_COMPILE")
        old_sandbox = os.environ.get("PAPERO_TEX_SANDBOX_CMD")
        try:
            os.environ["PAPERO_ALLOW_TEX_COMPILE"] = "1"
            os.environ["PAPERO_TEX_SANDBOX_CMD"] = '["sandbox"]'
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / "paper.tex"
                source.write_text("\\documentclass{article}\\begin{document}ok\\end{document}\n", encoding="utf-8")
                out_dir = root / "out"
                log = root / "build.log"
                calls = []

                def fake_which(name: str):
                    return f"/fake/{name}" if name == "tectonic" else None

                def fake_run(full_cmd, *, env, cwd, timeout=30):
                    calls.append(full_cmd)
                    (out_dir / "paper.pdf").parent.mkdir(parents=True, exist_ok=True)
                    (out_dir / "paper.pdf").write_bytes(b"%PDF-1.5\n")
                    return subprocess.CompletedProcess(full_cmd, 0, stdout=b"", stderr=b"")

                with patch("paperorchestra.latex.shutil.which", side_effect=fake_which), patch(
                    "paperorchestra.latex._run_wrapped_command", side_effect=fake_run
                ):
                    report = compile_latex_with_report(source, workdir=out_dir, output_log=log)
            self.assertTrue(report.clean)
            self.assertTrue(report.pdf_exists)
            self.assertTrue(any("tectonic" in command for command in calls[0]))
        finally:
            if old_allow is None:
                os.environ.pop("PAPERO_ALLOW_TEX_COMPILE", None)
            else:
                os.environ["PAPERO_ALLOW_TEX_COMPILE"] = old_allow
            if old_sandbox is None:
                os.environ.pop("PAPERO_TEX_SANDBOX_CMD", None)
            else:
                os.environ["PAPERO_TEX_SANDBOX_CMD"] = old_sandbox

    def test_compile_latex_opt_in_error_lists_next_commands(self) -> None:
        old_allow = os.environ.get("PAPERO_ALLOW_TEX_COMPILE")
        try:
            os.environ.pop("PAPERO_ALLOW_TEX_COMPILE", None)
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / "paper.tex"
                source.write_text("\\documentclass{article}\\begin{document}ok\\end{document}\n", encoding="utf-8")
                with self.assertRaises(LatexBuildError) as ctx:
                    compile_latex_with_report(source, workdir=root / "out", output_log=root / "build.log")
            message = str(ctx.exception)
            self.assertIn("paperorchestra check-compile-env", message)
            self.assertIn("paperorchestra bootstrap-compile-env", message)
            self.assertIn("PAPERO_ALLOW_TEX_COMPILE=1 paperorchestra compile", message)
        finally:
            if old_allow is None:
                os.environ.pop("PAPERO_ALLOW_TEX_COMPILE", None)
            else:
                os.environ["PAPERO_ALLOW_TEX_COMPILE"] = old_allow

    def test_compile_latex_missing_environment_error_summarizes_engine_and_sandbox(self) -> None:
        class FakeCompileReport:
            latex_engine = None
            sandbox_tool = None
            sandbox_wrapper_path = None

        old_allow = os.environ.get("PAPERO_ALLOW_TEX_COMPILE")
        old_sandbox = os.environ.get("PAPERO_TEX_SANDBOX_CMD")
        try:
            os.environ["PAPERO_ALLOW_TEX_COMPILE"] = "1"
            os.environ.pop("PAPERO_TEX_SANDBOX_CMD", None)
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / "paper.tex"
                source.write_text("\\documentclass{article}\\begin{document}ok\\end{document}\n", encoding="utf-8")
                with patch("paperorchestra.latex.ensure_sandbox_wrapper", return_value=None), patch(
                    "paperorchestra.latex.inspect_compile_environment", return_value=FakeCompileReport()
                ):
                    with self.assertRaises(LatexBuildError) as ctx:
                        compile_latex_with_report(source, workdir=root / "out", output_log=root / "build.log")
            message = str(ctx.exception)
            self.assertIn("compile environment is not ready", message)
            self.assertIn("LaTeX engine", message)
            self.assertIn("latexmk, pdflatex, or tectonic", message)
            self.assertIn("Usable sandbox", message)
            self.assertIn("PAPERO_TEX_SANDBOX_CMD", message)
            self.assertIn("paperorchestra check-compile-env", message)
        finally:
            if old_allow is None:
                os.environ.pop("PAPERO_ALLOW_TEX_COMPILE", None)
            else:
                os.environ["PAPERO_ALLOW_TEX_COMPILE"] = old_allow
            if old_sandbox is None:
                os.environ.pop("PAPERO_TEX_SANDBOX_CMD", None)
            else:
                os.environ["PAPERO_TEX_SANDBOX_CMD"] = old_sandbox

    def test_compile_latex_missing_engine_error_lists_recovery_commands(self) -> None:
        class FakeCompileReport:
            latex_engine = None
            sandbox_tool = "/usr/bin/firejail"
            sandbox_wrapper_path = '["/tmp/tex-sandbox.sh"]'

        old_allow = os.environ.get("PAPERO_ALLOW_TEX_COMPILE")
        old_sandbox = os.environ.get("PAPERO_TEX_SANDBOX_CMD")
        try:
            os.environ["PAPERO_ALLOW_TEX_COMPILE"] = "1"
            os.environ["PAPERO_TEX_SANDBOX_CMD"] = '["sandbox"]'
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / "paper.tex"
                source.write_text("\\documentclass{article}\\begin{document}ok\\end{document}\n", encoding="utf-8")
                with patch("paperorchestra.latex.shutil.which", return_value=None), patch(
                    "paperorchestra.latex.inspect_compile_environment", return_value=FakeCompileReport()
                ):
                    with self.assertRaises(LatexBuildError) as ctx:
                        compile_latex_with_report(source, workdir=root / "out", output_log=root / "build.log")
            message = str(ctx.exception)
            self.assertIn("compile environment is not ready", message)
            self.assertIn("LaTeX engine: latexmk, pdflatex, or tectonic", message)
            self.assertIn("Usable sandbox: /usr/bin/firejail", message)
            self.assertIn("paperorchestra check-compile-env", message)
            self.assertIn("paperorchestra bootstrap-compile-env", message)
            self.assertIn("PAPERO_ALLOW_TEX_COMPILE=1 paperorchestra compile", message)
        finally:
            if old_allow is None:
                os.environ.pop("PAPERO_ALLOW_TEX_COMPILE", None)
            else:
                os.environ["PAPERO_ALLOW_TEX_COMPILE"] = old_allow
            if old_sandbox is None:
                os.environ.pop("PAPERO_TEX_SANDBOX_CMD", None)
            else:
                os.environ["PAPERO_TEX_SANDBOX_CMD"] = old_sandbox

    def test_latex_wrapped_command_timeout_defaults_to_30_seconds(self) -> None:
        old_timeout = os.environ.get("PAPERO_LATEX_TIMEOUT_SEC")
        try:
            os.environ.pop("PAPERO_LATEX_TIMEOUT_SEC", None)
            with patch("paperorchestra.latex.subprocess.run") as run:
                run.return_value = subprocess.CompletedProcess(["latexmk"], 0, stdout=b"", stderr=b"")
                _run_wrapped_command(["latexmk"], env={}, cwd=Path.cwd())
            self.assertEqual(run.call_args.kwargs["timeout"], 30)
        finally:
            if old_timeout is None:
                os.environ.pop("PAPERO_LATEX_TIMEOUT_SEC", None)
            else:
                os.environ["PAPERO_LATEX_TIMEOUT_SEC"] = old_timeout

    def test_latex_wrapped_command_uses_configured_timeout(self) -> None:
        old_timeout = os.environ.get("PAPERO_LATEX_TIMEOUT_SEC")
        try:
            os.environ["PAPERO_LATEX_TIMEOUT_SEC"] = "120"
            with patch("paperorchestra.latex.subprocess.run") as run:
                run.return_value = subprocess.CompletedProcess(["latexmk"], 0, stdout=b"", stderr=b"")
                _run_wrapped_command(["latexmk"], env={}, cwd=Path.cwd())
            self.assertEqual(run.call_args.kwargs["timeout"], 120)
        finally:
            if old_timeout is None:
                os.environ.pop("PAPERO_LATEX_TIMEOUT_SEC", None)
            else:
                os.environ["PAPERO_LATEX_TIMEOUT_SEC"] = old_timeout

    def test_latex_wrapped_command_rejects_invalid_timeout(self) -> None:
        old_timeout = os.environ.get("PAPERO_LATEX_TIMEOUT_SEC")
        try:
            os.environ["PAPERO_LATEX_TIMEOUT_SEC"] = "not-a-number"
            with self.assertRaisesRegex(LatexBuildError, "PAPERO_LATEX_TIMEOUT_SEC"):
                _run_wrapped_command(["latexmk"], env={}, cwd=Path.cwd())
            os.environ["PAPERO_LATEX_TIMEOUT_SEC"] = "0"
            with self.assertRaisesRegex(LatexBuildError, "between 1 and 3600"):
                _run_wrapped_command(["latexmk"], env={}, cwd=Path.cwd())
            os.environ["PAPERO_LATEX_TIMEOUT_SEC"] = "nan"
            with self.assertRaisesRegex(LatexBuildError, "finite number"):
                _run_wrapped_command(["latexmk"], env={}, cwd=Path.cwd())
            os.environ["PAPERO_LATEX_TIMEOUT_SEC"] = "inf"
            with self.assertRaisesRegex(LatexBuildError, "finite number"):
                _run_wrapped_command(["latexmk"], env={}, cwd=Path.cwd())
        finally:
            if old_timeout is None:
                os.environ.pop("PAPERO_LATEX_TIMEOUT_SEC", None)
            else:
                os.environ["PAPERO_LATEX_TIMEOUT_SEC"] = old_timeout

    def test_compile_latex_sets_bib_and_bst_search_paths(self) -> None:
        old_allow = os.environ.get("PAPERO_ALLOW_TEX_COMPILE")
        old_sandbox = os.environ.get("PAPERO_TEX_SANDBOX_CMD")
        old_texinputs = os.environ.get("TEXINPUTS")
        try:
            os.environ["PAPERO_ALLOW_TEX_COMPILE"] = "1"
            os.environ["PAPERO_TEX_SANDBOX_CMD"] = '["sandbox"]'
            os.environ["TEXINPUTS"] = "/tmp/custom-bst:"
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / "paper.tex"
                source.write_text(
                    "\\documentclass{article}\n\\begin{document}\nX\\bibliographystyle{IEEEtran}\\bibliography{references}\\end{document}\n",
                    encoding="utf-8",
                )
                (root / "references.bib").write_text("@article{a,title={A},author={B},year={2024}}\n", encoding="utf-8")
                out_dir = root / "out"
                log = root / "build.log"
                seen_env = {}

                def fake_run(full_cmd, *, env, cwd, timeout=30):
                    seen_env.update(env)
                    (out_dir / "paper.pdf").parent.mkdir(parents=True, exist_ok=True)
                    (out_dir / "paper.pdf").write_bytes(b"%PDF-1.5\n")
                    return subprocess.CompletedProcess(full_cmd, 0, stdout=b"", stderr=b"")

                with patch("paperorchestra.latex.shutil.which", side_effect=lambda name: f"/fake/{name}" if name == "latexmk" else None), patch(
                    "paperorchestra.latex._run_wrapped_command", side_effect=fake_run
                ):
                    report = compile_latex_with_report(source, workdir=out_dir, output_log=log)
            self.assertTrue(report.clean)
            self.assertIn(str(out_dir), seen_env["BIBINPUTS"])
            self.assertIn(str(root), seen_env["BIBINPUTS"])
            self.assertIn("/tmp/custom-bst", seen_env["BSTINPUTS"])
            self.assertTrue(seen_env["BSTINPUTS"].endswith(os.pathsep))
        finally:
            if old_allow is None:
                os.environ.pop("PAPERO_ALLOW_TEX_COMPILE", None)
            else:
                os.environ["PAPERO_ALLOW_TEX_COMPILE"] = old_allow
            if old_sandbox is None:
                os.environ.pop("PAPERO_TEX_SANDBOX_CMD", None)
            else:
                os.environ["PAPERO_TEX_SANDBOX_CMD"] = old_sandbox
            if old_texinputs is None:
                os.environ.pop("TEXINPUTS", None)
            else:
                os.environ["TEXINPUTS"] = old_texinputs

    def test_compile_latex_copies_safe_relative_bibliographies(self) -> None:
        old_allow = os.environ.get("PAPERO_ALLOW_TEX_COMPILE")
        old_sandbox = os.environ.get("PAPERO_TEX_SANDBOX_CMD")
        try:
            os.environ["PAPERO_ALLOW_TEX_COMPILE"] = "1"
            os.environ["PAPERO_TEX_SANDBOX_CMD"] = '["sandbox"]'
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / ".paper-orchestra" / "runs" / "po-demo" / "artifacts" / "paper.full.tex"
                source.parent.mkdir(parents=True)
                source.write_text(
                    "\\documentclass{article}\n\\begin{document}\n"
                    "X\\bibliographystyle{plain}\\bibliography { inputs/reference_metadata_seed, inputs/custom_seed }\\end{document}\n",
                    encoding="utf-8",
                )
                (root / "inputs").mkdir()
                (root / "inputs" / "reference_metadata_seed.bib").write_text(
                    "@article{a,title={A},author={B},year={2024}}\n",
                    encoding="utf-8",
                )
                (root / "inputs" / "custom_seed.bib").write_text(
                    "@article{c,title={C},author={D},year={2025}}\n",
                    encoding="utf-8",
                )
                out_dir = source.parent.parent / "build"
                log = source.parent.parent / "latex-build.log"

                def fake_run(full_cmd, *, env, cwd, timeout=30):
                    for name in ["reference_metadata_seed.bib", "custom_seed.bib"]:
                        self.assertTrue(
                            (out_dir / "inputs" / name).exists(),
                            "compile workdir should preserve safe bibliography paths emitted in \\bibliography{...}",
                        )
                    self.assertIn(str(out_dir), env["BIBINPUTS"])
                    (out_dir / "paper.full.pdf").parent.mkdir(parents=True, exist_ok=True)
                    (out_dir / "paper.full.pdf").write_bytes(b"%PDF-1.5\n")
                    return subprocess.CompletedProcess(full_cmd, 0, stdout=b"", stderr=b"")

                with patch("paperorchestra.latex.shutil.which", side_effect=lambda name: f"/fake/{name}" if name == "latexmk" else None), patch(
                    "paperorchestra.latex._run_wrapped_command", side_effect=fake_run
                ):
                    report = compile_latex_with_report(source, workdir=out_dir, output_log=log)
            self.assertTrue(report.clean)
            self.assertTrue(report.pdf_exists)
        finally:
            if old_allow is None:
                os.environ.pop("PAPERO_ALLOW_TEX_COMPILE", None)
            else:
                os.environ["PAPERO_ALLOW_TEX_COMPILE"] = old_allow
            if old_sandbox is None:
                os.environ.pop("PAPERO_TEX_SANDBOX_CMD", None)
            else:
                os.environ["PAPERO_TEX_SANDBOX_CMD"] = old_sandbox

    def test_compile_latex_does_not_copy_unsafe_bibliography_paths_or_symlinks(self) -> None:
        old_allow = os.environ.get("PAPERO_ALLOW_TEX_COMPILE")
        old_sandbox = os.environ.get("PAPERO_TEX_SANDBOX_CMD")
        try:
            os.environ["PAPERO_ALLOW_TEX_COMPILE"] = "1"
            os.environ["PAPERO_TEX_SANDBOX_CMD"] = '["sandbox"]'
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / ".paper-orchestra" / "runs" / "po-demo" / "artifacts" / "paper.full.tex"
                source.parent.mkdir(parents=True)
                source.write_text(
                    "\\documentclass{article}\n\\begin{document}\n"
                    "\\bibliographystyle{plain}\\bibliography{../secret,/tmp/secret,inputs/symlinked_seed,linked_inputs/parent_seed}\\end{document}\n",
                    encoding="utf-8",
                )
                (root / "inputs").mkdir()
                outside = root.parent / f"{root.name}-outside.bib"
                outside.write_text("@article{x,title={X}}\n", encoding="utf-8")
                (root / "inputs" / "symlinked_seed.bib").symlink_to(outside)
                real_inputs = root / "real_inputs"
                real_inputs.mkdir()
                (real_inputs / "parent_seed.bib").write_text("@article{p,title={P}}\n", encoding="utf-8")
                (root / "linked_inputs").symlink_to(real_inputs, target_is_directory=True)
                out_dir = source.parent.parent / "build"
                log = source.parent.parent / "latex-build.log"

                def fake_run(full_cmd, *, env, cwd, timeout=30):
                    self.assertFalse((out_dir / "secret.bib").exists())
                    self.assertFalse((out_dir / "tmp" / "secret.bib").exists())
                    self.assertFalse((out_dir / "inputs" / "symlinked_seed.bib").exists())
                    self.assertFalse((out_dir / "linked_inputs" / "parent_seed.bib").exists())
                    (out_dir / "paper.full.pdf").parent.mkdir(parents=True, exist_ok=True)
                    (out_dir / "paper.full.pdf").write_bytes(b"%PDF-1.5\n")
                    return subprocess.CompletedProcess(full_cmd, 0, stdout=b"", stderr=b"")

                with patch("paperorchestra.latex.shutil.which", side_effect=lambda name: f"/fake/{name}" if name == "latexmk" else None), patch(
                    "paperorchestra.latex._run_wrapped_command", side_effect=fake_run
                ):
                    report = compile_latex_with_report(source, workdir=out_dir, output_log=log)
            self.assertTrue(report.clean)
        finally:
            if old_allow is None:
                os.environ.pop("PAPERO_ALLOW_TEX_COMPILE", None)
            else:
                os.environ["PAPERO_ALLOW_TEX_COMPILE"] = old_allow
            if old_sandbox is None:
                os.environ.pop("PAPERO_TEX_SANDBOX_CMD", None)
            else:
                os.environ["PAPERO_TEX_SANDBOX_CMD"] = old_sandbox

    def test_compile_latex_forces_latexmk_rerun_after_bibtex_and_reference_recovery(self) -> None:
        old_allow = os.environ.get("PAPERO_ALLOW_TEX_COMPILE")
        old_sandbox = os.environ.get("PAPERO_TEX_SANDBOX_CMD")
        try:
            os.environ["PAPERO_ALLOW_TEX_COMPILE"] = "1"
            os.environ["PAPERO_TEX_SANDBOX_CMD"] = '["sandbox"]'
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / "paper.tex"
                source.write_text(
                    "\\documentclass{article}\n\\begin{document}\nX\\bibliographystyle{plain}\\bibliography{references}\\end{document}\n",
                    encoding="utf-8",
                )
                (root / "references.bib").write_text("@article{a,title={A},author={B},year={2024}}\n", encoding="utf-8")
                out_dir = root / "out"
                log = root / "build.log"
                calls = []

                def fake_run(full_cmd, *, env, cwd, timeout=30):
                    calls.append(list(full_cmd))
                    (out_dir / "paper.pdf").parent.mkdir(parents=True, exist_ok=True)
                    (out_dir / "paper.pdf").write_bytes(b"%PDF-1.5\n")
                    if "bibtex" in full_cmd:
                        return subprocess.CompletedProcess(full_cmd, 0, stdout=b"", stderr=b"")
                    return subprocess.CompletedProcess(
                        full_cmd,
                        0,
                        stdout=b"undefined citations detected\nundefined reference\n",
                        stderr=b"",
                    )

                with patch("paperorchestra.latex.shutil.which", side_effect=lambda name: f"/fake/{name}" if name in {"latexmk", "bibtex"} else None), patch(
                    "paperorchestra.latex._run_wrapped_command", side_effect=fake_run
                ):
                    compile_latex_with_report(source, workdir=out_dir, output_log=log)
            latexmk_calls = [call for call in calls if "latexmk" in call]
            self.assertTrue(any("-g" in call for call in latexmk_calls[1:]))
        finally:
            if old_allow is None:
                os.environ.pop("PAPERO_ALLOW_TEX_COMPILE", None)
            else:
                os.environ["PAPERO_ALLOW_TEX_COMPILE"] = old_allow
            if old_sandbox is None:
                os.environ.pop("PAPERO_TEX_SANDBOX_CMD", None)
            else:
                os.environ["PAPERO_TEX_SANDBOX_CMD"] = old_sandbox

    def test_compile_latex_does_not_report_citations_from_reference_summary_heading(self) -> None:
        old_allow = os.environ.get("PAPERO_ALLOW_TEX_COMPILE")
        old_sandbox = os.environ.get("PAPERO_TEX_SANDBOX_CMD")
        try:
            os.environ["PAPERO_ALLOW_TEX_COMPILE"] = "1"
            os.environ["PAPERO_TEX_SANDBOX_CMD"] = '["sandbox"]'
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / "paper.tex"
                source.write_text(
                    "\\documentclass{article}\n\\begin{document}\n"
                    "See Section~\\ref{sec:missing} and prior work~\\cite{a}."
                    "\\bibliographystyle{plain}\\bibliography{references}\\end{document}\n",
                    encoding="utf-8",
                )
                (root / "references.bib").write_text("@article{a,title={A},author={B},year={2024}}\n", encoding="utf-8")
                out_dir = root / "out"
                log = root / "build.log"
                latexmk_outputs = [
                    b"undefined citations detected\nundefined reference\n",
                    b"Latexmk: ====Undefined refs and citations with line #s in .tex file:\n"
                    b"  Reference `sec:missing' on page 1 undefined on input line 2\n"
                    b"Latexmk: Summary of warnings from last run of *latex:\n"
                    b"  Latex failed to resolve 1 reference(s)\n",
                    b"Latexmk: ====Undefined refs and citations with line #s in .tex file:\n"
                    b"  Reference `sec:missing' on page 1 undefined on input line 2\n"
                    b"Latexmk: Summary of warnings from last run of *latex:\n"
                    b"  Latex failed to resolve 1 reference(s)\n",
                ]

                def fake_run(full_cmd, *, env, cwd, timeout=30):
                    calls_pdf = out_dir / "paper.pdf"
                    calls_pdf.parent.mkdir(parents=True, exist_ok=True)
                    calls_pdf.write_bytes(b"%PDF-1.5\n")
                    if "bibtex" in full_cmd:
                        return subprocess.CompletedProcess(full_cmd, 0, stdout=b"", stderr=b"")
                    output = latexmk_outputs.pop(0)
                    return subprocess.CompletedProcess(full_cmd, 0, stdout=output, stderr=b"")

                with patch("paperorchestra.latex.shutil.which", side_effect=lambda name: f"/fake/{name}" if name in {"latexmk", "bibtex"} else None), patch(
                    "paperorchestra.latex._run_wrapped_command", side_effect=fake_run
                ):
                    report = compile_latex_with_report(source, workdir=out_dir, output_log=log)
            self.assertEqual(report.warning_summary, ["undefined references detected"])
        finally:
            if old_allow is None:
                os.environ.pop("PAPERO_ALLOW_TEX_COMPILE", None)
            else:
                os.environ["PAPERO_ALLOW_TEX_COMPILE"] = old_allow
            if old_sandbox is None:
                os.environ.pop("PAPERO_TEX_SANDBOX_CMD", None)
            else:
                os.environ["PAPERO_TEX_SANDBOX_CMD"] = old_sandbox

    def test_write_sections_can_rewrite_only_selected_sections_and_write_custom_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(root, provider=MockProvider(), discovery_mode="model", verify_mode="mock", refine_iterations=0)
            state = load_session(root)
            current_paper = Path(state.artifacts.paper_full_tex)
            current_paper.write_text(
                "\\documentclass{article}\n"
                "\\begin{document}\n"
                "\\section{Introduction}\nPreserve this introduction.\n"
                "\\section{Related Work}\nPreserve this related work.\n"
                "\\section{Method}\nOLD METHOD BODY.\n"
                "\\section{Experiments}\nPreserve these experiment notes.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            output_path = root / "rewritten-method-only.tex"
            result = write_sections(root, MockProvider(), only_sections=["Method"], output_path=output_path)
            self.assertEqual(result, output_path)
            rewritten = output_path.read_text(encoding="utf-8")
            self.assertIn("Preserve this introduction.", rewritten)
            self.assertIn("Preserve these experiment notes.", rewritten)
            self.assertNotIn("OLD METHOD BODY.", rewritten)
            self.assertIn("The pipeline follows staged orchestration", rewritten)
            updated = load_session(root)
            self.assertEqual(updated.artifacts.paper_full_tex, str(output_path))

    def test_mcp_write_sections_supports_section_scope_and_custom_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(root, provider=MockProvider(), discovery_mode="model", verify_mode="mock", refine_iterations=0)
            state = load_session(root)
            Path(state.artifacts.paper_full_tex).write_text(
                "\\documentclass{article}\n"
                "\\begin{document}\n"
                "\\section{Introduction}\nKeep intro.\n"
                "\\section{Related Work}\nKeep related.\n"
                "\\section{Method}\nOLD METHOD BODY.\n"
                "\\section{Experiments}\nKeep experiments.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            output_path = root / "mcp-rewritten.tex"
            payload = json.loads(
                tool_write_sections(
                    {
                        "cwd": str(root),
                        "provider": "mock",
                        "only_sections": ["Method"],
                        "output_path": str(output_path),
                    }
                )["content"][0]["text"]
            )
            self.assertEqual(payload["path"], str(output_path))
            rewritten = output_path.read_text(encoding="utf-8")
            self.assertIn("Keep intro.", rewritten)
            self.assertNotIn("OLD METHOD BODY.", rewritten)

    def test_write_sections_rejects_unknown_only_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(root, provider=MockProvider(), discovery_mode="model", verify_mode="mock", refine_iterations=0)
            state = load_session(root)
            Path(state.artifacts.paper_full_tex).write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\nA.\n\\section{Method}\nB.\n\\end{document}\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ContractError, "Unknown section name"):
                write_sections(root, MockProvider(), only_sections=["Nonexistent Section"])

    def test_bibliography_hook_retargets_template_seed_to_generated_references(self) -> None:
        latex = (
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "Generated claim \\cite{generatedKey}.\n"
            "\\bibliographystyle{plain}\n"
            "\\bibliography{inputs/reference_metadata_seed}\n"
            "\\end{document}\n"
        )
        normalized = _ensure_bibliography_hook(latex, {"generatedKey": {"title": "Generated"}})
        self.assertIn("\\bibliography{references}", normalized)
        self.assertNotIn("reference_metadata_seed", normalized)
        self.assertEqual(normalized.count("\\bibliographystyle{plain}"), 1)

    def test_bibliography_hook_adds_style_when_retargeting_styleless_seed(self) -> None:
        latex = (
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "Generated claim \\cite{generatedKey}.\n"
            "\\bibliography { inputs/reference_metadata_seed, inputs/custom_seed }\n"
            "\\end{document}\n"
        )
        normalized = _ensure_bibliography_hook(latex, {"generatedKey": {"title": "Generated"}})
        self.assertIn("\\bibliographystyle{plain}\n\\bibliography{references}", normalized)
        self.assertNotIn("reference_metadata_seed", normalized)
        self.assertNotIn("custom_seed", normalized)

    def test_bibliography_hook_preserves_manual_thebibliography(self) -> None:
        latex = (
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "Manual citation \\cite{manual}.\n"
            "\\begin{thebibliography}{9}\n"
            "\\bibitem{manual} Author. Title.\n"
            "\\end{thebibliography}\n"
            "\\end{document}\n"
        )
        self.assertEqual(_ensure_bibliography_hook(latex, {"manual": {"title": "Manual"}}), latex)

    def test_bibliography_hook_replaces_incomplete_manual_thebibliography(self) -> None:
        latex = (
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "Generated claim \\cite{manual,generatedKey}.\n"
            "\\begin{thebibliography}{9}\n"
            "\\bibitem{manual} Author. Title.\n"
            "\\end{thebibliography}\n"
            "\\end{document}\n"
        )
        normalized = _ensure_bibliography_hook(
            latex,
            {"manual": {"title": "Manual"}, "generatedKey": {"title": "Generated"}},
        )
        self.assertNotIn("\\begin{thebibliography}", normalized)
        self.assertIn("\\bibliographystyle{plain}\n\\bibliography{references}", normalized)
        self.assertIn("\\cite{manual,generatedKey}", normalized)

    def test_bibliography_hook_preserves_existing_style_when_retargeting(self) -> None:
        latex = (
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "Generated claim \\cite{generatedKey}.\n"
            "\\bibliographystyle{IEEEtran}\n"
            "\\bibliography{inputs/reference_metadata_seed}\n"
            "\\end{document}\n"
        )
        normalized = _ensure_bibliography_hook(latex, {"generatedKey": {"title": "Generated"}})
        self.assertIn("\\bibliographystyle{IEEEtran}\n\\bibliography{references}", normalized)
        self.assertNotIn("\\bibliographystyle{plain}", normalized)
        self.assertNotIn("reference_metadata_seed", normalized)

    def test_bibliography_hook_collapses_duplicate_bibliography_commands(self) -> None:
        latex = (
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "\\bibliography{inputs/reference_metadata_seed}\n"
            "Body.\n"
            "\\bibliography{inputs/extra_seed}\n"
            "\\end{document}\n"
        )
        normalized = _ensure_bibliography_hook(latex, {"generatedKey": {"title": "Generated"}})
        self.assertEqual(normalized.count("\\bibliography{references}"), 1)
        self.assertNotIn("reference_metadata_seed", normalized)
        self.assertNotIn("extra_seed", normalized)

    def test_write_sections_uses_full_template_when_intro_related_artifact_exists(self) -> None:
        testcase = self

        class TemplateAssertingProvider(MockProvider):
            def complete(self, request: CompletionRequest) -> str:
                testcase.assertIn("\\section{Introduction}", request.user_prompt)
                testcase.assertIn("\\section{Related Work}", request.user_prompt)
                testcase.assertIn("\\section{Security Analysis}", request.user_prompt)
                testcase.assertIn("citation_coverage_target.json", request.user_prompt)
                testcase.assertIn("Do NOT invent meta sections such as checklists", request.user_prompt)
                testcase.assertNotIn('"authors": [', request.user_prompt)
                return r"""```latex
\\documentclass{article}
\\begin{document}
\\section{Introduction}
Intro \\cite{alpha}.
\\section{Related Work}
Related \\cite{alpha}.
\\section{Security Analysis}
Security analysis discusses adversary capabilities, run-token handling, proof obligations, transcript scope, and the precise assumptions needed for the integrity and confidentiality arguments in a materially substantive way. \\cite{alpha}
\\section{Conclusion}
The conclusion summarizes the validated contribution, the proof limits, the benchmark constraints, and the remaining deployment caveats in enough detail to exceed the shallow-section threshold. \\cite{alpha}
\\bibliographystyle{plain}
\\bibliography{references}
\\end{document}
```"""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            state = load_session(root)
            Path(state.inputs.template_path).write_text(
                "\\documentclass{article}\n"
                "\\begin{document}\n"
                "\\section{Introduction}\nOld intro.\n"
                "\\section{Related Work}\nOld related.\n"
                "\\section{Security Analysis}\nOld security.\n"
                "\\section{Conclusion}\nOld conclusion.\n"
                "\\bibliographystyle{plain}\n\\bibliography{references}\n\\end{document}\n",
                encoding="utf-8",
            )
            intro_related = artifact_path(root, "introduction_related_work.tex")
            intro_related.write_text(
                "\\section{Introduction}\nNew intro.\n\\section{Related Work}\nNew related.\n",
                encoding="utf-8",
            )
            outline_path = artifact_path(root, "outline.json")
            outline_path.write_text(
                json.dumps(
                    {
                        "plotting_plan": [],
                        "intro_related_work_plan": {},
                        "section_plan": [
                            {"section_title": "Security Analysis", "subsections": []},
                            {"section_title": "Conclusion", "subsections": []},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            citation_map_path = artifact_path(root, "citation_map.json")
            citation_map_path.write_text(json.dumps({"alpha": {"title": "Alpha"}}), encoding="utf-8")
            state.artifacts.intro_related_tex = str(intro_related)
            state.artifacts.outline_json = str(outline_path)
            state.artifacts.citation_map_json = str(citation_map_path)
            save_session(root, state)
            plan_narrative_and_claims(root, MockProvider())
            path = write_sections(root, TemplateAssertingProvider())
            self.assertTrue(Path(path).exists())

    def test_write_sections_compacts_large_prompt_inputs(self) -> None:
        testcase = self

        class SectionPromptAssertingProvider(MockProvider):
            def complete(self, request: CompletionRequest) -> str:
                testcase.assertIn("[...truncated for prompt budget...]", request.user_prompt)
                testcase.assertNotIn('"authors": [', request.user_prompt)
                return r"""```latex
\\documentclass{article}
\\begin{document}
\\section{Introduction}
Intro \\cite{alpha}.
\\section{Related Work}
Related \\cite{alpha}.
\\section{Method}
Method details with citations \\cite{alpha}. This section now contains enough substantive explanation about pipeline stages, artifact flow, validation gates, and manuscript assembly decisions to exceed the shallow-section threshold comfortably.
\\section{Experiments}
Experiments \\cite{alpha}. This section contains enough substantive benchmark, setup, evaluation, and interpretation prose to avoid being treated as a heading-only placeholder by the manuscript validator.
\\section{Conclusion}
Done \\cite{alpha}. This conclusion summarizes the validated outcome, limits, and remaining caveats in enough detail to satisfy the substantive-body requirement as part of the prompt-compaction regression test.
\\bibliographystyle{plain}
\\bibliography{references}
\\end{document}
```"""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            state = load_session(root)
            Path(state.inputs.idea_path).write_text("A" * 20000, encoding="utf-8")
            Path(state.inputs.experimental_log_path).write_text("B" * 30000, encoding="utf-8")
            Path(state.inputs.template_path).write_text("C" * 22000, encoding="utf-8")
            outline_path = artifact_path(root, "outline.json")
            outline_path.write_text(
                json.dumps(
                    {
                        "plotting_plan": [],
                        "intro_related_work_plan": {},
                        "section_plan": [
                            {"section_title": "Method", "subsections": []},
                            {"section_title": "Experiments", "subsections": []},
                            {"section_title": "Conclusion", "subsections": []},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            citation_map_path = artifact_path(root, "citation_map.json")
            citation_map_path.write_text(
                json.dumps(
                    {
                        "alpha": {
                            "title": "Alpha",
                            "authors": ["A1", "A2"],
                            "year": 2024,
                            "venue": "Conf",
                            "abstract": "Z" * 1500,
                            "origin": "manual",
                            "matched_query": "alpha query",
                            "provenance": {"source": "manual_seed"},
                        }
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.outline_json = str(outline_path)
            state.artifacts.citation_map_json = str(citation_map_path)
            save_session(root, state)
            plan_narrative_and_claims(root, MockProvider())
            path = write_sections(root, SectionPromptAssertingProvider())
            self.assertTrue(Path(path).exists())

    def test_source_critical_context_preserves_deep_proof_material(self) -> None:
        context = _source_critical_context_for_prompt(
            {
                "idea": "A" * 6000 + "\nGame 0 replaces the PRP/PRF stream under P1 and P2 before the forgery bound.\n",
                "experimental_log": "",
                "template": "",
            }
        )
        joined = json.dumps(context, ensure_ascii=False)
        self.assertIn("Game 0", joined)
        self.assertIn("PRP/PRF", joined)
        self.assertIn("P1", joined)
        self.assertIn("P2", joined)

    def test_write_sections_strict_prompt_includes_citation_metadata_and_deep_source_context(self) -> None:
        testcase = self

        class StrictPromptAssertingProvider(MockProvider):
            def complete(self, request: CompletionRequest) -> str:
                testcase.assertIn("&quot;abstract&quot;:", request.user_prompt)
                testcase.assertIn("&quot;year&quot;: 2024", request.user_prompt)
                testcase.assertIn("&quot;venue&quot;: &quot;Conf&quot;", request.user_prompt)
                testcase.assertNotIn("&quot;provenance&quot;", request.user_prompt)
                testcase.assertNotIn("manual_seed", request.user_prompt)
                testcase.assertIn("source_critical_context.json", request.user_prompt)
                testcase.assertIn("Game 0", request.user_prompt)
                testcase.assertIn("PRP/PRF", request.user_prompt)
                return r"""```latex
\documentclass{article}
\begin{document}
\section{Method}
Method details use verified support \cite{alpha}. This section has enough grounded content about construction, security context, and implementation choices to pass the shallow-section validator.
\section{Security Analysis}
Game 0 replaces the PRP/PRF stream under P1 and P2 \cite{alpha}. This section includes enough proof detail and caveats to avoid placeholder behavior in strict prompt tests.
\section{Experiments}
Benchmarks are discussed qualitatively \cite{alpha}. This section has enough benchmark setup and interpretation prose to satisfy the section-depth contract without invented numbers.
\section{Conclusion}
The draft remains human-finalized \cite{alpha}. This conclusion is substantive enough for validation and states limits without unsupported claims.
\bibliographystyle{plain}
\bibliography{references}
\end{document}
```"""

        old = os.environ.get("PAPERO_STRICT_CONTENT_GATES")
        try:
            os.environ["PAPERO_STRICT_CONTENT_GATES"] = "1"
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self._init_session_with_minimal_inputs(root)
                state = load_session(root)
                Path(state.inputs.idea_path).write_text(
                    "A" * 9000 + "\nGame 0 replaces the PRP/PRF stream under P1 and P2 before the forgery bound.\n",
                    encoding="utf-8",
                )
                outline_path = artifact_path(root, "outline.json")
                outline_path.write_text(
                    json.dumps(
                        {
                            "section_plan": [
                                {"section_title": "Method", "subsections": []},
                                {"section_title": "Security Analysis", "subsections": []},
                                {"section_title": "Experiments", "subsections": []},
                                {"section_title": "Conclusion", "subsections": []},
                            ]
                        }
                    ),
                    encoding="utf-8",
                )
                citation_map_path = artifact_path(root, "citation_map.json")
                citation_map_path.write_text(
                    json.dumps(
                        {
                            "alpha": {
                                "title": "Alpha",
                                "year": 2024,
                                "venue": "Conf",
                                "abstract": "Alpha supports the proof context.",
                                "provenance": {"source": "manual_seed"},
                            }
                        }
                    ),
                    encoding="utf-8",
                )
                state.artifacts.outline_json = str(outline_path)
                state.artifacts.citation_map_json = str(citation_map_path)
                save_session(root, state)
                plan_narrative_and_claims(root, MockProvider())
                self.assertTrue(Path(write_sections(root, StrictPromptAssertingProvider())).exists())
        finally:
            if old is None:
                os.environ.pop("PAPERO_STRICT_CONTENT_GATES", None)
            else:
                os.environ["PAPERO_STRICT_CONTENT_GATES"] = old

    def test_write_sections_strict_blocks_unknown_citation_keys_instead_of_dropping(self) -> None:
        class UnknownCitationProvider(MockProvider):
            def complete(self, request: CompletionRequest) -> str:
                return r"""```latex
\documentclass{article}
\begin{document}
\section{Method}
Method details cite an unmapped source \cite{missing}. This section is otherwise long enough to avoid shallow-section handling and should fail because the citation key is not verified.
\section{Conclusion}
Done \cite{missing}. This conclusion is long enough but intentionally cites the missing key.
\bibliographystyle{plain}
\bibliography{references}
\end{document}
```"""

        old = os.environ.get("PAPERO_STRICT_CONTENT_GATES")
        try:
            os.environ["PAPERO_STRICT_CONTENT_GATES"] = "1"
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self._init_session_with_minimal_inputs(root)
                state = load_session(root)
                outline_path = artifact_path(root, "outline.json")
                outline_path.write_text(json.dumps({"section_plan": [{"section_title": "Method"}, {"section_title": "Conclusion"}]}), encoding="utf-8")
                citation_map_path = artifact_path(root, "citation_map.json")
                citation_map_path.write_text(json.dumps({"alpha": {"title": "Alpha"}}), encoding="utf-8")
                state.artifacts.outline_json = str(outline_path)
                state.artifacts.citation_map_json = str(citation_map_path)
                save_session(root, state)
                plan_narrative_and_claims(root, MockProvider())
                with self.assertRaises(ContractError) as cm:
                    write_sections(root, UnknownCitationProvider())
                self.assertIn("unknown citation", str(cm.exception).lower())
        finally:
            if old is None:
                os.environ.pop("PAPERO_STRICT_CONTENT_GATES", None)
            else:
                os.environ["PAPERO_STRICT_CONTENT_GATES"] = old

    def test_write_sections_claim_safe_blocks_unmapped_source_citations_without_env_flag(self) -> None:
        class ShouldNotCallProvider(MockProvider):
            def complete(self, request: CompletionRequest) -> str:  # pragma: no cover - failure path
                raise AssertionError("claim-safe source citation preflight should run before the writer")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            state = load_session(root)
            Path(state.inputs.idea_path).write_text("Human source says this matters \\cite{missingSourceKey}.\n", encoding="utf-8")
            outline_path = artifact_path(root, "outline.json")
            outline_path.write_text(json.dumps({"section_plan": [{"section_title": "Method"}, {"section_title": "Conclusion"}]}), encoding="utf-8")
            citation_map_path = artifact_path(root, "citation_map.json")
            citation_map_path.write_text(json.dumps({"alpha": {"title": "Alpha"}}), encoding="utf-8")
            state.artifacts.outline_json = str(outline_path)
            state.artifacts.citation_map_json = str(citation_map_path)
            save_session(root, state)
            plan_narrative_and_claims(root, MockProvider())
            with self.assertRaises(ContractError) as cm:
                write_sections(root, ShouldNotCallProvider(), claim_safe=True)
            self.assertIn("source packet contains citation keys", str(cm.exception))
            self.assertIn("missingSourceKey", str(cm.exception))

    def test_intro_related_claim_safe_prompt_includes_metadata_and_source_context(self) -> None:
        testcase = self

        class IntroPromptAssertingProvider(MockProvider):
            def complete(self, request: CompletionRequest) -> str:
                testcase.assertIn("&quot;abstract&quot;:", request.user_prompt)
                testcase.assertIn("&quot;year&quot;: 2024", request.user_prompt)
                testcase.assertIn("source_critical_context.json", request.user_prompt)
                testcase.assertIn("Game 0", request.user_prompt)
                return r"""```latex
\documentclass{article}
\begin{document}
\section{Introduction}
This introduction frames the method with verified context \cite{alpha}. It is long enough to satisfy the validation contract while avoiding unsupported novelty claims.
\section{Related Work}
Related work compares the surrounding area using verified metadata \cite{alpha}. It remains cautious and does not invent external findings beyond the provided citation map.
\section{Method}
\end{document}
```"""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            state = load_session(root)
            Path(state.inputs.idea_path).write_text("A" * 6000 + "\nGame 0 proof context.\n", encoding="utf-8")
            outline_path = artifact_path(root, "outline.json")
            outline_path.write_text(
                json.dumps(
                    {
                        "intro_related_work_plan": {"positioning": "demo"},
                        "section_plan": [{"section_title": "Introduction"}, {"section_title": "Related Work"}, {"section_title": "Method"}],
                    }
                ),
                encoding="utf-8",
            )
            citation_map_path = artifact_path(root, "citation_map.json")
            citation_map_path.write_text(
                json.dumps({"alpha": {"title": "Alpha", "year": 2024, "venue": "Conf", "abstract": "Alpha abstract", "provenance": {"source": "manual_seed"}}}),
                encoding="utf-8",
            )
            state.artifacts.outline_json = str(outline_path)
            state.artifacts.citation_map_json = str(citation_map_path)
            save_session(root, state)
            plan_narrative_and_claims(root, MockProvider())
            self.assertTrue(Path(write_intro_related(root, IntroPromptAssertingProvider(), claim_safe=True)).exists())

    def test_refine_claim_safe_prompt_includes_metadata_and_source_context(self) -> None:
        testcase = self

        class RefinePromptAssertingProvider(MockProvider):
            def complete(self, request: CompletionRequest) -> str:
                if "source_critical_context.json" not in request.user_prompt:
                    return json.dumps(
                        {
                            "schema_version": "paper-review/1",
                            "overall_score": 70,
                            "axis_scores": {"clarity": 70, "technical_depth": 70},
                            "summary": {"weaknesses": ["none"], "top_improvements": ["none"]},
                        }
                    )
                testcase.assertIn("&quot;abstract&quot;:", request.user_prompt)
                testcase.assertIn("&quot;year&quot;: 2024", request.user_prompt)
                testcase.assertIn("source_critical_context.json", request.user_prompt)
                testcase.assertIn("Game 0", request.user_prompt)
                return r"""```latex
\documentclass{article}
\begin{document}
\section{Introduction}
Intro \cite{alpha}. This preserved introduction explains the paper context, stated evidence, and cautious claim boundary in enough detail to satisfy the substantive-section validation threshold.
\section{Method}
Game 0 proof context \cite{alpha}. This method section remains substantive enough to preserve the validated current manuscript.
\section{Conclusion}
Conclusion \cite{alpha}. The conclusion remains cautious and human-finalized, summarizing that the draft is an evidence-grounded intermediate manuscript rather than an automated final paper.
\bibliographystyle{plain}
\bibliography{references}
\end{document}
```"""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            state = load_session(root)
            Path(state.inputs.idea_path).write_text("A" * 6000 + "\nGame 0 proof context.\n", encoding="utf-8")
            paper_path = artifact_path(root, "paper.full.tex")
            paper_text = RefinePromptAssertingProvider().complete(CompletionRequest(system_prompt="", user_prompt='&quot;abstract&quot;:\n&quot;year&quot;: 2024\nsource_critical_context.json\nGame 0'))
            paper_path.write_text(paper_text.replace("```latex\n", "").replace("\n```", ""), encoding="utf-8")
            citation_map_path = artifact_path(root, "citation_map.json")
            citation_map_path.write_text(
                json.dumps({"alpha": {"title": "Alpha", "year": 2024, "venue": "Conf", "abstract": "Alpha abstract", "provenance": {"source": "manual_seed"}}}),
                encoding="utf-8",
            )
            outline_path = artifact_path(root, "outline.json")
            outline_path.write_text(
                json.dumps({"section_plan": [{"section_title": "Introduction"}, {"section_title": "Method"}, {"section_title": "Conclusion"}]}),
                encoding="utf-8",
            )
            review_path_ = review_path(root, "review.latest.json")
            review_path_.write_text(json.dumps({"overall_score": 70, "axis_scores": {"clarity": 70}}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper_path)
            state.artifacts.outline_json = str(outline_path)
            state.artifacts.citation_map_json = str(citation_map_path)
            state.artifacts.latest_review_json = str(review_path_)
            save_session(root, state)
            plan_narrative_and_claims(root, MockProvider())
            result = refine_current_paper(root, RefinePromptAssertingProvider(), iterations=1, claim_safe=True)
            self.assertTrue(result)
            self.assertTrue(result[0]["accepted"])

    def test_expected_section_titles_from_outline_skips_meta_sections(self) -> None:
        outline = {
            "section_plan": [
                {"section_title": "Abstract"},
                {"section_title": "\\begin{abstract}...\\end{abstract}"},
                {"section_title": "Introduction"},
                {"section_title": "Cross-cutting Citation Coverage Checklist"},
                {"section_title": "Security Analysis"},
                {"section_title": "Appendix"},
                {"section_title": "Appendix (optional post-template extension)"},
                {"section_title": "Appendix A: Supplementary Proof Details"},
                {"section_title": "\\appendix"},
                {"section_title": r"\\appendix"},
            ]
        }
        from paperorchestra.pipeline import _expected_section_titles_from_outline

        self.assertEqual(
            _expected_section_titles_from_outline(outline),
            ["Introduction", "Security Analysis"],
        )

    def test_generate_outline_compacts_large_prompt_inputs(self) -> None:
        testcase = self

        class OutlinePromptAssertingProvider(MockProvider):
            def complete(self, request: CompletionRequest) -> str:
                testcase.assertIn("[...truncated for prompt budget...]", request.user_prompt)
                return super().complete(request)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            state = load_session(root)
            Path(state.inputs.idea_path).write_text("A" * 20000, encoding="utf-8")
            Path(state.inputs.experimental_log_path).write_text("B" * 22000, encoding="utf-8")
            Path(state.inputs.template_path).write_text("C" * 18000, encoding="utf-8")
            path = generate_outline(root, OutlinePromptAssertingProvider())
            self.assertTrue(Path(path).exists())

    def test_generate_plots_compacts_large_prompt_inputs(self) -> None:
        testcase = self

        class PlotPromptAssertingProvider(MockProvider):
            def complete(self, request: CompletionRequest) -> str:
                testcase.assertIn("[...truncated for prompt budget...]", request.user_prompt)
                return super().complete(request)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            state = load_session(root)
            Path(state.inputs.idea_path).write_text("A" * 15000, encoding="utf-8")
            Path(state.inputs.experimental_log_path).write_text("B" * 25000, encoding="utf-8")
            outline_path = artifact_path(root, "outline.json")
            outline_path.write_text(
                json.dumps(
                    {
                        "plotting_plan": [
                            {
                                "figure_id": "fig_example",
                                "title": "Example",
                                "plot_type": "diagram",
                                "data_source": "both",
                                "objective": "Explain the system.",
                                "aspect_ratio": "16:9",
                            }
                        ],
                        "intro_related_work_plan": {},
                        "section_plan": [],
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.outline_json = str(outline_path)
            save_session(root, state)
            path = generate_plots(root, PlotPromptAssertingProvider())
            self.assertTrue(Path(path).exists())

    def test_compact_outline_for_prompt_trims_section_plan_details(self) -> None:
        outline = {
            "section_plan": [
                {
                    "section_title": "Method",
                    "subsections": [
                        {
                            "subsection_title": "One",
                            "content_bullets": ["a", "b", "c", "d"],
                            "citation_hints": ["c1", "c2", "c3", "c4"],
                        },
                        {
                            "subsection_title": "Two",
                            "content_bullets": ["e"],
                            "citation_hints": ["c5"],
                        },
                    ],
                }
            ]
        }
        compact = _compact_outline_for_prompt(outline)
        subsection = compact["section_plan"][0]["subsections"][0]
        self.assertEqual(subsection["content_bullets"], ["a"])
        self.assertEqual(subsection["citation_hints"], ["c1"])
        self.assertEqual(len(compact["section_plan"][0]["subsections"]), 2)

    def test_compact_intro_related_plan_for_prompt_trims_queries_and_subsections(self) -> None:
        plan = {
            "introduction_strategy": {
                "hook_hypothesis": "hook",
                "problem_gap_hypothesis": "gap",
                "search_directions": ["q1", "q2", "q3", "q4"],
            },
            "related_work_strategy": {
                "overview": "overview",
                "subsections": [
                    {
                        "subsection_title": "S1",
                        "methodology_cluster": "M",
                        "sota_investigation_mission": "mission",
                        "limitation_hypothesis": "limit",
                        "limitation_search_queries": ["a", "b", "c"],
                        "bridge_to_our_method": "bridge",
                    },
                    {"subsection_title": "S2", "limitation_search_queries": ["d", "e", "f"]},
                    {"subsection_title": "S3", "limitation_search_queries": ["g"]},
                    {"subsection_title": "S4", "limitation_search_queries": ["h"]},
                    {"subsection_title": "S5", "limitation_search_queries": ["i"]},
                ],
            },
        }
        compact = _compact_intro_related_plan_for_prompt(plan)
        rendered = json.dumps(compact, ensure_ascii=False)
        self.assertEqual(compact["introduction_strategy"]["background_topics"], ["q1", "q2", "q3"])
        self.assertEqual(len(compact["related_work_strategy"]["subsections"]), 4)
        self.assertEqual(compact["related_work_strategy"]["subsections"][0]["comparative_context_goal"], "mission")
        self.assertEqual(compact["related_work_strategy"]["subsections"][0]["limitations_to_discuss"], "limit")
        for forbidden in ("hook_hypothesis", "problem_gap_hypothesis", "search_directions", "sota_investigation_mission", "limitation_hypothesis", "limitation_search_queries"):
            self.assertNotIn(forbidden, rendered)

    def test_compact_plot_manifest_and_assets_for_prompt_trim_fields(self) -> None:
        manifest = {
            "figures": [
                {
                    "figure_id": "fig1",
                    "title": "Title",
                    "caption": "Caption",
                    "plot_type": "plot",
                    "aspect_ratio": "16:9",
                    "objective": "Long objective",
                }
            ]
        }
        assets = {
            "assets": [
                {
                    "figure_id": "fig1",
                    "title": "Title",
                    "caption": "Caption",
                    "filename": "fig1.svg",
                    "latex_snippet_path": "build/plot-assets/fig1.tex",
                    "plot_type": "plot",
                    "aspect_ratio": "16:9",
                    "path": "/tmp/full/path",
                }
            ]
        }
        compact_manifest = _compact_plot_manifest_for_prompt(manifest)
        compact_assets = _compact_plot_assets_for_prompt(assets)
        self.assertNotIn("objective", compact_manifest["figures"][0])
        self.assertNotIn("path", compact_assets["assets"][0])

    def test_write_intro_related_compacts_large_prompt_inputs(self) -> None:
        testcase = self

        class IntroPromptAssertingProvider(MockProvider):
            def complete(self, request: CompletionRequest) -> str:
                testcase.assertIn("[...truncated for prompt budget...]", request.user_prompt)
                testcase.assertNotIn('"authors": [', request.user_prompt)
                return """```latex
\\section{Introduction}
Intro \\cite{alpha}.
\\section{Related Work}
Related \\cite{alpha}.
```"""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            state = load_session(root)
            Path(state.inputs.idea_path).write_text("A" * 20000, encoding="utf-8")
            Path(state.inputs.experimental_log_path).write_text("B" * 25000, encoding="utf-8")
            Path(state.inputs.template_path).write_text("C" * 18000, encoding="utf-8")
            outline_path = artifact_path(root, "outline.json")
            outline_path.write_text(
                json.dumps(
                    {
                        "plotting_plan": [],
                        "intro_related_work_plan": {
                            "introduction_strategy": {"hook_hypothesis": "Hook", "problem_gap_hypothesis": "Gap", "search_directions": []},
                            "related_work_strategy": {"overview": "Overview", "subsections": []},
                        },
                        "section_plan": [],
                    }
                ),
                encoding="utf-8",
            )
            citation_map_path = artifact_path(root, "citation_map.json")
            citation_map_path.write_text(
                json.dumps(
                    {
                        "alpha": {
                            "title": "Alpha",
                            "authors": ["A1", "A2"],
                            "year": 2024,
                            "venue": "Conf",
                            "abstract": "Z" * 1500,
                            "origin": "manual",
                            "matched_query": "alpha query",
                            "provenance": {"source": "manual_seed"},
                        }
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.outline_json = str(outline_path)
            state.artifacts.citation_map_json = str(citation_map_path)
            save_session(root, state)
            plan_narrative_and_claims(root, MockProvider())
            path = write_intro_related(root, IntroPromptAssertingProvider())
            self.assertTrue(Path(path).exists())

    def test_research_prior_work_compacts_large_prompt_inputs(self) -> None:
        testcase = self

        class PriorWorkPromptAssertingProvider(MockProvider):
            def complete(self, request: CompletionRequest) -> str:
                testcase.assertIn("[...truncated for prompt budget...]", request.user_prompt)
                return """```json
{
  "references": [],
  "research_notes": []
}
```"""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            state = load_session(root)
            Path(state.inputs.idea_path).write_text("A" * 20000, encoding="utf-8")
            Path(state.inputs.experimental_log_path).write_text("B" * 25000, encoding="utf-8")
            result = generate_prior_work_seed(root, PriorWorkPromptAssertingProvider())
            self.assertTrue(Path(result["path"]).exists())

    def test_review_current_paper_compacts_large_prompt_inputs(self) -> None:
        testcase = self

        class ReviewPromptAssertingProvider(MockProvider):
            def complete(self, request: CompletionRequest) -> str:
                testcase.assertIn("[...truncated for prompt budget...]", request.user_prompt)
                testcase.assertNotIn('"authors": [', request.user_prompt)
                return super().complete(request)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(root, provider=MockProvider(), discovery_mode="model", verify_mode="mock", refine_iterations=0)
            state = load_session(root)
            Path(state.artifacts.paper_full_tex).write_text("A" * 50000, encoding="utf-8")
            path = review_current_paper(root, ReviewPromptAssertingProvider())
            self.assertTrue(Path(path).exists())

    def test_review_current_paper_records_authenticating_review_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(root, provider=MockProvider(), discovery_mode="model", verify_mode="mock", refine_iterations=0)

            path = review_current_paper(root, MockProvider())
            payload = json.loads(Path(path).read_text(encoding="utf-8"))

            provenance = payload.get("review_provenance")
            self.assertEqual(payload["schema_version"], "paper-review/1")
            self.assertIsInstance(provenance, dict)
            self.assertEqual(provenance["schema_version"], "review-provenance/1")
            self.assertEqual(provenance["stage"], "review")
            self.assertEqual(provenance["manuscript_sha256"], payload["manuscript_sha256"])
            for key in ["prompt_trace_meta_path", "provider_identity_path", "lane_manifest_path"]:
                self.assertTrue(Path(provenance[key]).exists(), key)
            for key in ["prompt_trace_meta_sha256", "provider_identity_sha256", "lane_manifest_sha256"]:
                self.assertRegex(provenance[key], r"^[0-9a-f]{64}$")

    def test_review_cli_output_writes_named_current_review_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(root, provider=MockProvider(), discovery_mode="model", verify_mode="mock", refine_iterations=0)
            old_cwd = Path.cwd()
            stdout = io.StringIO()
            try:
                os.chdir(root)
                with contextlib.redirect_stdout(stdout):
                    code = cli_main(["review", "--provider", "mock", "--output", "review.independent.json"])
            finally:
                os.chdir(old_cwd)

            self.assertEqual(code, 0)
            path = Path(stdout.getvalue().strip())
            self.assertTrue(path.exists())
            self.assertEqual(path.name, "review.independent.json")
            state = load_session(root)
            self.assertEqual(Path(state.artifacts.latest_review_json).name, "review.independent.json")

    def test_refine_current_paper_compacts_large_prompt_inputs(self) -> None:
        testcase = self

        class RefinePromptAssertingProvider(MockProvider):
            def complete(self, request: CompletionRequest) -> str:
                if "content refinement agent" in request.system_prompt.lower():
                    testcase.assertIn("[...truncated for prompt budget...]", request.user_prompt)
                    testcase.assertNotIn('"authors": [', request.user_prompt)
                    testcase.assertNotIn('&quot;overall_score&quot;', request.user_prompt)
                    testcase.assertNotIn('&quot;axis_scores&quot;', request.user_prompt)
                    testcase.assertIn('score_redaction', request.user_prompt)
                return super().complete(request)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(root, provider=MockProvider(), discovery_mode="model", verify_mode="mock", refine_iterations=0)
            state = load_session(root)
            Path(state.artifacts.paper_full_tex).write_text("A" * 50000, encoding="utf-8")
            path = review_current_paper(root, MockProvider())
            self.assertTrue(Path(path).exists())
            result = refine_current_paper(root, RefinePromptAssertingProvider(), iterations=1)
            self.assertEqual(len(result), 1)

    def test_estimate_cost_reports_model_call_range_and_cli_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            payload = estimate_run_cost(
                root,
                discovery_mode="search-grounded",
                refine_iterations=2,
                compile_paper=True,
                runtime_mode="omx_native",
            )
            self.assertEqual(payload["estimated_model_calls"]["min"], 9)
            self.assertEqual(payload["estimated_model_calls"]["max"], 15)
            self.assertEqual(payload["estimated_external_calls"]["latex_compile"], 1)
            self.assertGreater(payload["input_size"]["chars"], 0)

            old_cwd = Path.cwd()
            stdout = io.StringIO()
            try:
                os.chdir(root)
                with contextlib.redirect_stdout(stdout):
                    code = cli_main(
                        [
                            "estimate-cost",
                            "--discovery-mode",
                            "search-grounded",
                            "--refine-iterations",
                            "2",
                            "--compile",
                            "--runtime-mode",
                            "omx_native",
                        ]
                    )
            finally:
                os.chdir(old_cwd)
            self.assertEqual(code, 0)
            cli_payload = json.loads(stdout.getvalue())
            self.assertEqual(cli_payload["runtime_mode"], "omx_native")
            self.assertEqual(cli_payload["estimated_model_calls"]["max"], 15)

    def test_doctor_report_and_cli_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = build_doctor_report(root)
            self.assertIn(report["overall_status"], {"ok", "warning"})
            codes = {check["code"] for check in report["checks"]}
            self.assertIn("omx_available", codes)
            self.assertIn("paperorchestra_mcp_health", codes)
            self.assertIn("compile_environment_ready", codes)
            self.assertIn("semantic_scholar_api_key", codes)
            self.assertIn("paperorchestra_mcp_health", report)
            self.assertIn("readiness_profiles", report)
            self.assertIn("environment_docs", report)

            old_cwd = Path.cwd()
            stdout = io.StringIO()
            try:
                os.chdir(root)
                with contextlib.redirect_stdout(stdout):
                    code = cli_main(["doctor"])
            finally:
                os.chdir(old_cwd)
            self.assertEqual(code, 0)
            cli_payload = json.loads(stdout.getvalue())
            self.assertIn("checks", cli_payload)
            self.assertIn("readiness_profiles", cli_payload)

    def test_doctor_omx_probe_requires_xz_for_control_surface(self) -> None:
        class FakeCompileReport:
            def to_dict(self) -> dict[str, object]:
                return {"ready_for_compile": False}

        def fake_which(name: str) -> str | None:
            return {"omx": "/usr/bin/omx", "codex": "/usr/bin/codex"}.get(name)

        with tempfile.TemporaryDirectory() as tmp, patch("paperorchestra.doctor.shutil.which", side_effect=fake_which), patch(
            "paperorchestra.doctor._command_version", return_value="version"
        ), patch("paperorchestra.doctor.inspect_compile_environment", return_value=FakeCompileReport()):
            report = build_doctor_report(Path(tmp))

        probe = report["omx_control_surface_probe"]
        self.assertEqual(probe["status"], "missing")
        self.assertFalse(probe["ready"])
        self.assertFalse(probe["checks"]["xz_available"])
        self.assertTrue(any("xz-utils" in step for step in probe["next_steps"]))
        omx_profile = next(profile for profile in report["readiness_profiles"] if profile["name"] == "omx_native_ready")
        self.assertFalse(omx_profile["ready"])
        self.assertTrue(any("xz-utils" in missing for missing in omx_profile["missing"]))

    def test_doctor_omx_probe_warns_on_bwrap_namespace_denial(self) -> None:
        class FakeCompileReport:
            def to_dict(self) -> dict[str, object]:
                return {"ready_for_compile": False}

        def fake_which(name: str) -> str | None:
            return {
                "omx": "/usr/bin/omx",
                "codex": "/usr/bin/codex",
                "xz": "/usr/bin/xz",
                "bwrap": "/usr/bin/bwrap",
            }.get(name)

        def fake_run(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="bwrap: No permissions to create new namespace")

        with tempfile.TemporaryDirectory() as tmp, patch("paperorchestra.doctor.shutil.which", side_effect=fake_which), patch(
            "paperorchestra.doctor._command_version", return_value="version"
        ), patch("paperorchestra.doctor.inspect_compile_environment", return_value=FakeCompileReport()), patch(
            "paperorchestra.doctor.subprocess.run", side_effect=fake_run
        ):
            report = build_doctor_report(Path(tmp))

        probe = report["omx_control_surface_probe"]
        self.assertEqual(probe["status"], "warning")
        self.assertFalse(probe["ready"])
        self.assertFalse(probe["checks"]["bwrap_namespace_usable"])
        self.assertIn("namespace", probe["detail"])
        self.assertTrue(any("actual `omx explore` may still work" in missing for missing in probe["missing"]))
        self.assertTrue(any("omx explore" in step for step in probe["next_steps"]))
        omx_profile = next(profile for profile in report["readiness_profiles"] if profile["name"] == "omx_native_ready")
        self.assertFalse(omx_profile["ready"])
        self.assertTrue(any("compatibility" in step for step in omx_profile["next_steps"]))

    def test_doctor_omx_probe_gates_full_live_profiles(self) -> None:
        class FakeCompileReport:
            def to_dict(self) -> dict[str, object]:
                return {"ready_for_compile": True}

        def fake_which(name: str) -> str | None:
            return {
                "omx": "/usr/bin/omx",
                "codex": "/usr/bin/codex",
                "xz": "/usr/bin/xz",
                "bwrap": "/usr/bin/bwrap",
            }.get(name)

        def fake_run(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="bwrap: No permissions to create new namespace")

        old_env = {key: os.environ.get(key) for key in [
            "PAPERO_MODEL_CMD",
            "SEMANTIC_SCHOLAR_API_KEY",
            "PAPERO_ALLOW_TEX_COMPILE",
            "PAPERO_STRICT_OMX_NATIVE",
            "PAPERO_STRICT_CONTENT_GATES",
        ]}
        try:
            os.environ["PAPERO_MODEL_CMD"] = '["codex"]'
            os.environ["SEMANTIC_SCHOLAR_API_KEY"] = "test"
            os.environ["PAPERO_ALLOW_TEX_COMPILE"] = "1"
            os.environ["PAPERO_STRICT_OMX_NATIVE"] = "1"
            os.environ["PAPERO_STRICT_CONTENT_GATES"] = "1"
            with tempfile.TemporaryDirectory() as tmp, patch("paperorchestra.doctor.shutil.which", side_effect=fake_which), patch(
                "paperorchestra.doctor._command_version", return_value="version"
            ), patch("paperorchestra.doctor.inspect_compile_environment", return_value=FakeCompileReport()), patch(
                "paperorchestra.doctor.subprocess.run", side_effect=fake_run
            ):
                report = build_doctor_report(Path(tmp))
        finally:
            for key, value in old_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        profiles = {profile["name"]: profile for profile in report["readiness_profiles"]}
        self.assertFalse(profiles["omx_native_ready"]["ready"])
        self.assertFalse(profiles["full_live_run_ready"]["ready"])
        self.assertFalse(profiles["claim_safe_full_run_ready"]["ready"])
        self.assertIn("OMX control surface probe did not pass.", profiles["full_live_run_ready"]["missing"])

    def test_doctor_omx_probe_allows_ready_when_prerequisites_pass(self) -> None:
        class FakeCompileReport:
            def to_dict(self) -> dict[str, object]:
                return {"ready_for_compile": False}

        def fake_which(name: str) -> str | None:
            return {
                "omx": "/usr/bin/omx",
                "codex": "/usr/bin/codex",
                "xz": "/usr/bin/xz",
            }.get(name)

        with tempfile.TemporaryDirectory() as tmp, patch("paperorchestra.doctor.shutil.which", side_effect=fake_which), patch(
            "paperorchestra.doctor._command_version", return_value="version"
        ), patch("paperorchestra.doctor.inspect_compile_environment", return_value=FakeCompileReport()):
            report = build_doctor_report(Path(tmp))

        probe = report["omx_control_surface_probe"]
        self.assertEqual(probe["status"], "ok")
        self.assertTrue(probe["ready"])
        self.assertIsNone(probe["checks"]["bwrap_namespace_usable"])
        omx_profile = next(profile for profile in report["readiness_profiles"] if profile["name"] == "omx_native_ready")
        self.assertTrue(omx_profile["ready"])

    def test_doctor_treats_falsey_compile_opt_in_as_warning(self) -> None:
        old_allow = os.environ.get("PAPERO_ALLOW_TEX_COMPILE")
        try:
            for value in ["0", "true", "yes", "on"]:
                os.environ["PAPERO_ALLOW_TEX_COMPILE"] = value
                with tempfile.TemporaryDirectory() as tmp:
                    report = build_doctor_report(Path(tmp))
                compile_opt = next(check for check in report["checks"] if check["code"] == "papero_allow_tex_compile")
                self.assertEqual(compile_opt["status"], "warning")
        finally:
            if old_allow is None:
                os.environ.pop("PAPERO_ALLOW_TEX_COMPILE", None)
            else:
                os.environ["PAPERO_ALLOW_TEX_COMPILE"] = old_allow

    def test_run_full_fidelity_writes_eval_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            reference_dir = root / "reference"
            reference_dir.mkdir()
            (reference_dir / "seed_answers.json").write_text(
                json.dumps({"baselines": ["Single Agent"], "datasets_or_benchmarks": ["PaperWritingBench"]}),
                encoding="utf-8",
            )
            (reference_dir / "results.md").write_text("Absolute win-rate margins of 50%–68% in literature review quality.", encoding="utf-8")
            (reference_dir / "methodology.md").write_text("Method excerpt", encoding="utf-8")
            (reference_dir / "task_and_dataset.md").write_text("Task excerpt", encoding="utf-8")
            (reference_dir / "template.tex").write_text("\\documentclass{article}\n", encoding="utf-8")
            reference_case = write_reference_benchmark_case(reference_dir, reference_dir / "benchmark_case.json")

            old_cwd = Path.cwd()
            stdout = io.StringIO()
            try:
                os.chdir(root)
                with contextlib.redirect_stdout(stdout):
                    code = cli_main(
                        [
                            "run",
                            "--provider",
                            "mock",
                            "--verify-mode",
                            "mock",
                            "--runtime-mode",
                            "compatibility",
                            "--discovery-mode",
                            "model",
                            "--refine-iterations",
                            "0",
                            "--full-fidelity",
                            "--reference-case",
                            str(reference_case),
                        ]
                    )
            finally:
                os.chdir(old_cwd)
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            artifacts = payload["full_fidelity_artifacts"]
            self.assertIn("reference_comparison", artifacts)
            self.assertIn("reference_case_partitioned_citation_coverage", artifacts)
            self.assertIn("citation_partition_request", artifacts)
            for path in artifacts.values():
                self.assertTrue(Path(path).exists())
            citation_partition = json.loads(Path(artifacts["citation_partition_request"]).read_text(encoding="utf-8"))
            self.assertGreater(citation_partition["reference_count"], 0)

    def test_run_full_fidelity_without_reference_case_writes_partial_partition_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)

            old_cwd = Path.cwd()
            stdout = io.StringIO()
            try:
                os.chdir(root)
                with contextlib.redirect_stdout(stdout):
                    code = cli_main(
                        [
                            "run",
                            "--provider",
                            "mock",
                            "--verify-mode",
                            "mock",
                            "--runtime-mode",
                            "compatibility",
                            "--discovery-mode",
                            "model",
                            "--refine-iterations",
                            "0",
                            "--full-fidelity",
                        ]
                    )
            finally:
                os.chdir(old_cwd)
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            artifacts = payload["full_fidelity_artifacts"]
            self.assertIn("citation_partition_request", artifacts)
            self.assertNotIn("reference_case_partitioned_citation_coverage", artifacts)
            fidelity = json.loads(Path(artifacts["fidelity_audit"]).read_text(encoding="utf-8"))
            partition = next(check for check in fidelity["checks"] if check["code"] == "citation_partition_scaffold_surface")
            self.assertIn(partition["status"], {"partial", "implemented"})


    def test_quickstart_cli_surface(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = cli_main(["quickstart", "--scenario", "testset"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["scenario"], "testset")
        self.assertTrue(any("paperorchestra init" in step for step in payload["steps"]))

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = cli_main(["quickstart", "--scenario", "environment"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["scenario"], "environment")
        self.assertTrue(any("paperorchestra environment" in step for step in payload["steps"]))

    def test_environment_inventory_and_cli_surface(self) -> None:
        inventory = build_environment_inventory()
        self.assertIn("docs", inventory)
        self.assertIn("groups", inventory)
        self.assertIn("package_context", inventory)
        self.assertIn("package_root", inventory["package_context"])
        self.assertIn("python_executable", inventory["package_context"])
        self.assertTrue(Path(inventory["docs"]["environment_guide"]).exists())
        self.assertTrue(Path(inventory["docs"]["env_example"]).exists())

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = cli_main(["environment"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertIn("readiness_profiles", payload)
        self.assertIn("package_context", payload)
        self.assertIn("package_root", payload["package_context"])
        self.assertTrue(any(profile["name"] == "compile_ready" for profile in payload["readiness_profiles"]))

    def test_environment_docs_and_example_cover_operator_vars(self) -> None:
        guide = environment_guide_path().read_text(encoding="utf-8")
        env_example = env_example_path().read_text(encoding="utf-8")
        for name in operator_environment_variable_names():
            self.assertIn(name, guide)
            self.assertIn(name, env_example)

    def test_retry_reconnect_environment_contract_is_documented(self) -> None:
        inventory = build_environment_inventory()
        specs = {spec["name"]: spec for group in inventory["groups"] for spec in group["variables"]}
        provider_retry = specs["PAPERO_PROVIDER_RETRY_ATTEMPTS"]
        self.assertIn("transport evidence", provider_retry["description"])
        self.assertIn("plain timeouts", provider_retry["description"])
        self.assertIn("grace-only", provider_retry["description"])
        self.assertTrue(any("PAPERO_PROVIDER_RETRY_SAFE=1" in note for note in provider_retry["notes"]))

        omx_retry = specs["PAPERO_OMX_RETRY_ATTEMPTS"]
        self.assertIn("read-only OMX control", omx_retry["description"])
        self.assertIn("exec/full-auto", omx_retry["description"])
        self.assertIn("never replayed", omx_retry["description"])

        guide = environment_guide_path().read_text(encoding="utf-8")
        readme = env_example_path().read_text(encoding="utf-8")
        combined = guide + "\n" + readme
        for phrase in [
            "retry-safe declaration plus reconnect/disconnect-like transport evidence",
            "plain timeouts are grace-only",
            "OMX exec/full-auto is grace-only and never replayed",
            "state read --json",
            "single retry owner",
            "forces provider/OMX retry layers off",
            "Requires BOTH PAPERO_PROVIDER_RETRY_SAFE=1 AND PAPERO_PROVIDER_RETRY_ATTEMPTS>0",
            "PAPERO_CODEX_RETRY_JITTER_SECONDS",
        ]:
            self.assertIn(phrase, combined)

    def test_stage_cli_help_surfaces_runtime_mode_for_live_runs(self) -> None:
        outline_help = subprocess.run(
            ["python3", "-m", "paperorchestra.cli", "outline", "--help"],
            cwd=Path.cwd(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        ).stdout
        write_help = subprocess.run(
            ["python3", "-m", "paperorchestra.cli", "write-sections", "--help"],
            cwd=Path.cwd(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        ).stdout
        self.assertIn("--runtime-mode", outline_help)
        self.assertIn("--runtime-mode", write_help)

    def test_demo_mock_script_documents_basic_operator_flow(self) -> None:
        script = Path(__file__).resolve().parent.parent / "scripts" / "demo-mock.sh"
        text = script.read_text(encoding="utf-8")
        self.assertIn("init", text)
        self.assertIn("examples/minimal/idea.md", text)
        self.assertIn("run --provider mock", text)
        self.assertIn("audit-fidelity", text)
        self.assertIn("status --json", text)

    def test_testset_smoke_environment_docs_use_generic_names_with_deprecated_aliases(self) -> None:
        combined = Path("README.md").read_text(encoding="utf-8") + "\n" + Path("ENVIRONMENT.md").read_text(encoding="utf-8")
        inventory = build_environment_inventory()
        operator_names = set(operator_environment_variable_names())

        self.assertIn("PAPERO_TESTSET_SMOKE_WORKDIR", combined)
        self.assertIn("PAPERO_TESTSET_SMOKE_PROVIDER_TIMEOUT_SECONDS", combined)
        self.assertIn("PAPERO_TESTSET_SMOKE_WORKDIR", operator_names)
        self.assertNotIn("PAPERO_LEGACY_SMOKE_WORKDIR", operator_names)
        self.assertTrue(any(group["category"] == "testset_smoke" for group in inventory["groups"]))

    def test_teach_cli_prepares_bundle_and_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "paper"
            source.mkdir()
            (source / "figs").mkdir()
            (source / "figs" / "overview.pdf").write_bytes(b"%PDF-1.5\n")
            (source / "sections").mkdir()
            (source / "sections" / "method.tex").write_text("\\section{Method} Evidence-rich method.", encoding="utf-8")
            paper = source / "main.tex"
            paper.write_text(
                "\\title{Demo Teach Paper}\n\\begin{abstract}Demo abstract.\\end{abstract}\n\\input{sections/method}\n",
                encoding="utf-8",
            )
            artifact_repo = root / "artifact"
            artifact_repo.mkdir()
            (artifact_repo / "README.md").write_text("Artifact README", encoding="utf-8")
            old_cwd = Path.cwd()
            stdout = io.StringIO()
            try:
                os.chdir(root)
                with contextlib.redirect_stdout(stdout):
                    code = cli_main([
                        "teach",
                        "--paper", str(paper),
                        "--artifact-repo", str(artifact_repo),
                        "--figures-dir", str(source / "figs"),
                        "--output-dir", str(root / "teach-out"),
                    ])
            finally:
                os.chdir(old_cwd)
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertTrue(Path(payload["idea"]).exists())
            self.assertTrue(Path(payload["experimental_log"]).exists())
            self.assertTrue(payload.get("session_id"))

    def test_teach_bundle_preserves_source_preamble_and_bibliography_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "paper"
            (source / "sections").mkdir(parents=True)
            (source / "sections" / "intro.tex").write_text(
                "\\section{Introduction}\n\\label{sec:intro}\nIntro.\n",
                encoding="utf-8",
            )
            (source / "sections" / "method.tex").write_text(
                "\\section{Method}\n"
                "\\label{sec:method}\n"
                "\\subsection{Adversarial Oracles}\n"
                "\\label{subsec:adv-oracles}\n"
                "\\begin{equation}\n"
                "a=b\n"
                "\\label{eq:run-token-rand}\n"
                "\\end{equation}\n"
                "\\begin{figure}\n"
                "\\caption{Oracle overview}\n"
                "\\label{fig:snm-oracles}\n"
                "\\end{figure}\n"
                "\\begin{algorithm}[t]\n"
                "\\caption{MethodX Encrypt}\n"
                "\\label{alg:method-encrypt}\n"
                "\\begin{algorithmic}[1]\n"
                "\\State do something\n"
                "\\end{algorithmic}\n"
                "\\end{algorithm}\n"
                "\\begin{theorem}Stub.\\end{theorem}\n",
                encoding="utf-8",
            )
            paper = source / "main.tex"
            paper.write_text(
                "\\documentclass[10pt,journal,compsoc]{IEEEtran}\n"
                "\\usepackage{amsmath,amssymb,amsthm}\n"
                "\\usepackage{algorithm}\n"
                "\\newtheorem{theorem}{Theorem}\n"
                "\\title{Preserve Me}\n"
                "\\author{Alice}\n"
                "\\begin{document}\n"
                "\\maketitle\n"
                "\\input{sections/intro}\n"
                "\\input{sections/method}\n"
                "\\bibliographystyle{IEEEtran}\n"
                "\\bibliography{references}\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            bundle = prepare_teach_bundle(root, paper=paper, output_dir=root / "teach-out", initialize_session=False)
            template = Path(bundle["template"]).read_text(encoding="utf-8")
            experimental_log = Path(bundle["experimental_log"]).read_text(encoding="utf-8")
            self.assertIn("\\documentclass[10pt,journal,compsoc]{IEEEtran}", template)
            self.assertIn("\\usepackage{algorithm}", template)
            self.assertIn("\\newtheorem{theorem}{Theorem}", template)
            self.assertIn("\\maketitle", template)
            self.assertIn("\\section{Introduction}", template)
            self.assertIn("\\label{sec:intro}", template)
            self.assertIn("\\section{Method}", template)
            self.assertIn("\\label{sec:method}", template)
            self.assertIn("\\subsection{Adversarial Oracles}", template)
            self.assertIn("\\label{subsec:adv-oracles}", template)
            self.assertIn("\\label{eq:run-token-rand}", template)
            self.assertIn("\\label{fig:snm-oracles}", template)
            self.assertIn("\\label{alg:method-encrypt}", template)
            self.assertIn("\\bibliographystyle{IEEEtran}", template)
            self.assertIn("\\bibliography{references}", template)
            self.assertIn("## Source manuscript abstract", experimental_log)
            self.assertIn("## Source manuscript evidence excerpt", experimental_log)

    def test_teach_bundle_inlines_local_preamble_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "paper"
            source.mkdir()
            (source / "macros.tex").write_text("\\newcommand{\\METHODX}{\\mathsf{MethodX}}\n", encoding="utf-8")
            paper = source / "main.tex"
            paper.write_text(
                "\\documentclass{article}\n"
                "\\usepackage{amsmath}\n"
                "\\input{macros}\n"
                "\\begin{document}\n"
                "\\section{Method}\n"
                "\\METHODX{} construction.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            bundle = prepare_teach_bundle(root, paper=paper, output_dir=root / "teach-out", initialize_session=False)
            template = Path(bundle["template"]).read_text(encoding="utf-8")
            self.assertIn("\\newcommand{\\METHODX}{\\mathsf{MethodX}}", template)
            self.assertNotIn("\\input{macros}", template)

    def test_restore_missing_referenced_labels_reinserts_template_blocks(self) -> None:
        template = (
            "\\documentclass{article}\n\\begin{document}\n"
            "\\section{Background}\n"
            "\\subsection{Adversarial Oracles}\n"
            "\\label{subsec:adv-oracles}\n"
            "\\begin{equation}\n"
            "a=b\n"
            "\\label{eq:run-token-rand}\n"
            "\\end{equation}\n"
            "\\begin{figure}\n"
            "\\caption{Oracle overview}\n"
            "\\label{fig:snm-oracles}\n"
            "\\end{figure}\n"
            "\\section{Method}\n"
            "See Section~\\ref{subsec:adv-oracles}, Eq.~\\eqref{eq:run-token-rand}, and Figure~\\ref{fig:snm-oracles}.\n"
            "\\end{document}\n"
        )
        generated = (
            "\\documentclass{article}\n\\begin{document}\n"
            "\\section{Background}\n"
            "Background text only.\n"
            "\\section{Method}\n"
            "See Section~\\ref{subsec:adv-oracles}, Eq.~\\eqref{eq:run-token-rand}, and Figure~\\ref{fig:snm-oracles}.\n"
            "\\end{document}\n"
        )
        repaired = _restore_missing_referenced_labels(generated, template)
        self.assertIn("\\label{subsec:adv-oracles}", repaired)
        self.assertIn("\\label{eq:run-token-rand}", repaired)
        self.assertIn("\\label{fig:snm-oracles}", repaired)

    def test_restore_missing_referenced_labels_adds_common_section_label_without_template_source(self) -> None:
        template = (
            "\\documentclass{article}\n\\begin{document}\n"
            "\\section{Implementation and Results}\n"
            "No labels in the source template.\n"
            "\\end{document}\n"
        )
        generated = (
            "\\documentclass{article}\n\\begin{document}\n"
            "\\section{Implementation and Results}\n"
            "\\begin{table}\n"
            "\\caption{Evaluation environment for Section~\\ref{sec:impl}.}\n"
            "\\end{table}\n"
            "\\end{document}\n"
        )
        repaired = _restore_missing_referenced_labels(generated, template)
        self.assertIn("\\section{Implementation and Results}\n\\label{sec:impl}", repaired)

    def test_drop_unknown_citation_keys_keeps_verified_keys_without_fabricating_bib_entries(self) -> None:
        latex = (
            "BenchHarness background~\\cite{BernsteinLangeEBACS,thomson2020UsingTlsTo} "
            "and unknown-only source note~\\cite{BernsteinLangeBenchHarness}."
        )
        citation_map = {"thomson2020UsingTlsTo": {"title": "Using TLS to Secure QUIC"}}

        cleaned, dropped = _drop_unknown_citation_keys(latex, citation_map)

        self.assertIn("\\cite{thomson2020UsingTlsTo}", cleaned)
        self.assertNotIn("BernsteinLangeEBACS", cleaned)
        self.assertNotIn("BernsteinLangeBenchHarness", cleaned)
        self.assertEqual(dropped, {"BernsteinLangeEBACS": 1, "BernsteinLangeBenchHarness": 1})

    def test_restore_missing_referenced_labels_adds_nearest_subsection_anchor_without_template_source(self) -> None:
        template = (
            "\\documentclass{article}\n\\begin{document}\n"
            "\\section{Method}\n"
            "No source subsection labels.\n"
            "\\end{document}\n"
        )
        generated = (
            "\\documentclass{article}\n\\begin{document}\n"
            "\\section{Method}\n"
            "\\subsection{Hidden-State Model}\n"
            "Sections~\\ref{subsec:deployment-scope} and~\\ref{subsec:adv-oracles} motivate the model.\n"
            "\\end{document}\n"
        )

        repaired = _restore_missing_referenced_labels(generated, template)

        self.assertIn("\\label{subsec:adv-oracles}", repaired)
        self.assertIn("\\label{subsec:deployment-scope}", repaired)
        self.assertLess(repaired.index("\\label{subsec:deployment-scope}"), repaired.index("Sections~\\ref{subsec:deployment-scope}"))
        self.assertLess(repaired.index("\\label{subsec:adv-oracles}"), repaired.index("Sections~\\ref{subsec:deployment-scope}"))

    def test_restore_missing_referenced_labels_places_figure_after_reference_in_target_section(self) -> None:
        template = (
            "\\documentclass{article}\n\\begin{document}\n"
            "\\section{Background}\n"
            "\\begin{figure}[t]\n"
            "\\caption{Oracle overview}\n"
            "\\label{fig:snm-oracles}\n"
            "\\end{figure}\n"
            "\\section{Method}\n"
            "See Figure~\\ref{fig:snm-oracles} for the oracle structure.\n"
            "\\section{Conclusion}\nDone.\n"
            "\\end{document}\n"
        )
        generated = (
            "\\documentclass{article}\n\\begin{document}\n"
            "\\section{Background}\nBackground text only.\n"
            "\\section{Method}\n"
            "See Figure~\\ref{fig:snm-oracles} for the oracle structure.\n"
            "\\section{Conclusion}\nDone.\n"
            "\\end{document}\n"
        )
        repaired = _restore_missing_referenced_labels(generated, template)
        self.assertGreater(repaired.index("\\label{fig:snm-oracles}"), repaired.index("Figure~\\ref{fig:snm-oracles}"))
        self.assertLess(repaired.index("\\label{fig:snm-oracles}"), repaired.index("\\section{Conclusion}"))

    def test_provider_identity_payload_marks_shell_backend_without_exposing_command(self) -> None:
        provider = ShellProvider(command='["codex","exec"]')
        request = CompletionRequest(system_prompt="system", user_prompt="user", seed=7, temperature=0.2, max_output_tokens=321)
        payload = _provider_identity_payload(provider, runtime_mode="omx_native", stage="outline", request=request)
        self.assertEqual(payload["provider_name"], "shell")
        self.assertEqual(payload["resolved_backend_class"], "real_shell_backend")
        self.assertEqual(payload["stage"], "outline")
        self.assertTrue(payload["provider_command_present"])
        self.assertEqual(payload["model_command_source"], "explicit")
        self.assertEqual(len(payload["provider_command_digest"]), 64)
        self.assertNotIn("codex", json.dumps(payload))
        self.assertEqual(payload["request_controls"]["seed"], 7)
        self.assertEqual(payload["request_controls"]["temperature"], 0.2)
        self.assertEqual(payload["request_controls"]["max_output_tokens"], 321)
        self.assertFalse(payload["generation_determinism"]["byte_identical_generation_claimed"])

    def test_prompt_compaction_truncates_long_text_with_marker(self) -> None:
        text = "A" * 200 + "B" * 200
        compact = _prompt_compact_text(text, head_chars=50, tail_chars=30)
        self.assertIn("[...truncated for prompt budget...]", compact)
        self.assertTrue(compact.startswith("A" * 50))
        self.assertTrue(compact.endswith("B" * 30))

    def test_compact_citation_map_for_prompt_drops_most_heavy_fields(self) -> None:
        citation_map = {
            "alpha": {
                "title": "Alpha",
                "authors": ["A1", "A2", "A3", "A4", "A5"],
                "year": 2024,
                "venue": "Conf",
                "abstract": "Z" * 1000,
                "origin": "manual",
                "matched_query": "alpha query",
                "provenance": {"source": "manual_seed", "verification": "metadata_import"},
                "paper_id": "pid",
                "url": "http://example.com",
            }
        }
        compact = _compact_citation_map_for_prompt(citation_map)
        entry = compact["alpha"]
        self.assertEqual(entry["authors"], ["A1", "A2", "A3", "A4"])
        self.assertEqual(entry["provenance"], "manual_seed")
        self.assertNotIn("paper_id", entry)
        self.assertNotIn("url", entry)
        self.assertLess(len(entry["abstract"]), 400)

    def test_compact_citation_map_for_prompt_can_drop_abstracts_and_authors(self) -> None:
        citation_map = {
            "alpha": {
                "title": "Alpha",
                "authors": ["A1", "A2"],
                "year": 2024,
                "venue": "Conf",
                "abstract": "Z" * 1000,
                "origin": "manual",
                "matched_query": "alpha query",
                "provenance": {"source": "manual_seed"},
            }
        }
        compact = _compact_citation_map_for_prompt(citation_map, include_abstract=False, include_authors=False)
        entry = compact["alpha"]
        self.assertNotIn("authors", entry)
        self.assertNotIn("abstract", entry)

    def test_compact_citation_map_for_prompt_can_drop_origin_and_query(self) -> None:
        citation_map = {
            "alpha": {
                "title": "Alpha",
                "authors": ["A1", "A2"],
                "year": 2024,
                "venue": "Conf",
                "abstract": "Z" * 1000,
                "origin": "manual",
                "matched_query": "alpha query",
                "provenance": {"source": "manual_seed"},
            }
        }
        compact = _compact_citation_map_for_prompt(
            citation_map,
            include_abstract=False,
            include_authors=False,
            include_origin=False,
            include_matched_query=False,
        )
        entry = compact["alpha"]
        self.assertNotIn("origin", entry)
        self.assertNotIn("matched_query", entry)

    def test_compact_citation_map_for_prompt_can_drop_year_venue_and_provenance(self) -> None:
        citation_map = {
            "alpha": {
                "title": "Alpha",
                "year": 2024,
                "venue": "Conf",
                "provenance": {"source": "manual_seed"},
            }
        }
        compact = _compact_citation_map_for_prompt(
            citation_map,
            include_year=False,
            include_venue=False,
            include_provenance=False,
            include_origin=False,
            include_matched_query=False,
            include_abstract=False,
            include_authors=False,
        )
        entry = compact["alpha"]
        self.assertNotIn("year", entry)
        self.assertNotIn("venue", entry)
        self.assertNotIn("provenance", entry)

    def test_write_figure_placement_review_records_after_conclusion_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            state = load_session(root)
            manuscript = artifact_path(root, "paper.full.tex")
            manuscript.write_text(
                "\\documentclass{article}\n\\begin{document}\n"
                "\\section{Method}\n"
                "Method text.\n"
                "\\section{Conclusion}\n"
                "See Figure~\\ref{fig:late}.\n"
                "\\begin{figure}\n"
                "\\caption{Late figure}\n"
                "\\label{fig:late}\n"
                "\\end{figure}\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(manuscript)
            save_session(root, state)
            path, payload = write_figure_placement_review(root)
            self.assertTrue(path.exists())
            self.assertEqual(payload["figures"][0]["label"], "fig:late")
            self.assertIn("after_conclusion", payload["figures"][0]["warning_codes"])
            self.assertEqual(load_session(root).artifacts.latest_figure_placement_review_json, str(path))


    def test_section_and_citation_critics_emit_actionable_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(
                root,
                provider=MockProvider(),
                discovery_mode="model",
                verify_mode="mock",
                refine_iterations=0,
                compile_paper=False,
            )
            section_review = build_section_review(root)
            citation_review = build_citation_support_review(root)
            self.assertGreaterEqual(len(section_review["sections"]), 1)
            self.assertIn("score", section_review["sections"][0])
            self.assertGreater(citation_review["claims_checked"], 0)
            self.assertIn("support_status", citation_review["items"][0])

    def test_citation_support_heuristic_is_metadata_only_and_preserves_decimal_sentence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            seed_path = root / "refs.bib"
            seed_path.write_text(
                "@techreport{RFC8446,\n"
                "  title = {The Transport Layer Security ({TLS}) Protocol Version 1.3},\n"
                "  author = {Eric Rescorla},\n"
                "  year = {2018},\n"
                "  url = {https://www.rfc-editor.org/rfc/rfc8446}\n"
                "}\n",
                encoding="utf-8",
            )
            import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
            paper_path = artifact_path(root, "paper.full.tex")
            paper_path.write_text(
                "\\documentclass{article}\n\\begin{document}\n"
                "\\section{Introduction}\n"
                "TLS 1.3, the Transport Layer Security protocol, uses record protection mechanisms~\\cite{RFC8446}.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            state = load_session(root)
            state.artifacts.paper_full_tex = str(paper_path)
            save_session(root, state)

            review = build_citation_support_review(root)

            self.assertEqual(review["schema_version"], "citation-support-review/2")
            self.assertFalse(review["evidence_provenance"]["semantic_scholar_required"])
            self.assertEqual(review["review_mode"], "heuristic")
            self.assertEqual(review["claims_checked"], 1)
            self.assertTrue(review["items"][0]["sentence"].startswith("TLS 1.3, the Transport Layer Security"))
            self.assertEqual(review["items"][0]["support_status"], "metadata_only")
            self.assertEqual(review["items"][0]["heuristic_support_status"], "metadata_only")

    def test_citation_support_checks_common_and_extended_cite_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            citation_map_path = artifact_path(root, "citation_map.json")
            citation_map_path.write_text(
                json.dumps(
                    {
                        "A": {"title": "Alpha Source"},
                        "B": {"title": "Beta Source"},
                        "C": {"title": "Gamma Source"},
                        "D": {"title": "Delta Source"},
                        "E": {"title": "Epsilon Source"},
                        "F": {"title": "Zeta Source"},
                        "G": {"title": "Eta Source"},
                        "H": {"title": "Theta Source"},
                        "I": {"title": "Iota Source"},
                    }
                ),
                encoding="utf-8",
            )
            paper_path = artifact_path(root, "paper.full.tex")
            paper_path.write_text(
                "\\documentclass{article}\n\\begin{document}\n"
                "\\section{Introduction}\n"
                "Alpha framing~\\cite{A}. "
                "Beta framing~\\citep{B}. "
                "Gamma framing~\\citet{C}. "
                "Delta framing~\\parencite{D}. "
                "Epsilon framing~\\textcite{E}. "
                "Zeta framing~\\autocite{F}. "
                "Eta framing~\\citeauthor{G}. "
                "Theta framing~\\Cite{H}. "
                "Iota framing~\\Cites{I}.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper_path)
            state.artifacts.citation_map_json = str(citation_map_path)
            save_session(root, state)

            review = build_citation_support_review(root)

            self.assertEqual(review["claims_checked"], 9)
            self.assertEqual([item["citation_keys"][0] for item in review["items"]], ["A", "B", "C", "D", "E", "F", "G", "H", "I"])

    def test_model_citation_support_review_overrides_title_overlap_with_unsupported(self) -> None:
        class ClaimSupportProvider(MockProvider):
            name = "claim-support-test"

            def __init__(self) -> None:
                self.request: CompletionRequest | None = None

            def complete(self, request: CompletionRequest) -> str:
                self.request = request
                return json.dumps(
                    {
                        "items": [
                            {
                                "id": "cite-001",
                                "support_status": "unsupported",
                                "risk": "high",
                                "claim_type": "comparative",
                                "evidence": [],
                                "reasoning": "The cited protocol document does not support the benchmark comparison.",
                                "suggested_fix": "Remove or narrow the benchmark comparison.",
                            }
                        ],
                        "research_notes": ["No Semantic Scholar lookup was needed."],
                    }
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            seed_path = root / "refs.bib"
            seed_path.write_text(
                "@techreport{RFC9001,\n"
                "  title = {Using {TLS} to Secure {QUIC}},\n"
                "  author = {Martin Thomson and Sean Turner},\n"
                "  year = {2021},\n"
                "  url = {https://www.rfc-editor.org/rfc/rfc9001}\n"
                "}\n",
                encoding="utf-8",
            )
            import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
            paper_path = artifact_path(root, "paper.full.tex")
            paper_path.write_text(
                "\\documentclass{article}\n\\begin{document}\n"
                "\\section{Results}\n"
                "Our pipeline is faster than prior QUIC writing baselines~\\cite{RFC9001}.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            state = load_session(root)
            state.artifacts.paper_full_tex = str(paper_path)
            save_session(root, state)
            provider = ClaimSupportProvider()

            with patch("paperorchestra.literature.search_semantic_scholar", side_effect=AssertionError("S2 called")):
                review = build_citation_support_review(root, provider=provider, evidence_mode="model")

            self.assertIsNotNone(provider.request)
            self.assertIn("semantic_scholar_required: false", provider.request.user_prompt)
            self.assertIn("Our pipeline is faster", provider.request.user_prompt)
            self.assertEqual(review["evidence_provenance"]["mode"], "model")
            self.assertFalse(review["evidence_provenance"]["semantic_scholar_required"])
            self.assertEqual(review["items"][0]["heuristic_support_status"], "metadata_only")
            self.assertEqual(review["items"][0]["support_status"], "unsupported")
            self.assertEqual(review["summary"]["unsupported"], 1)

    def test_model_citation_support_malformed_json_fails_closed_to_manual_check(self) -> None:
        class MalformedProvider(MockProvider):
            name = "claim-support-malformed"

            def complete(self, request: CompletionRequest) -> str:
                return '{"items": [}'

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            seed_path = root / "refs.bib"
            seed_path.write_text(
                "@techreport{RFC9001,\n"
                "  title = {Using {TLS} to Secure {QUIC}},\n"
                "  author = {Martin Thomson and Sean Turner},\n"
                "  year = {2021},\n"
                "  url = {https://www.rfc-editor.org/rfc/rfc9001}\n"
                "}\n",
                encoding="utf-8",
            )
            import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
            paper_path = artifact_path(root, "paper.full.tex")
            paper_path.write_text(
                "\\documentclass{article}\n\\begin{document}\n"
                "\\section{Introduction}\n"
                "QUIC can use TLS for security~\\cite{RFC9001}.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            state = load_session(root)
            state.artifacts.paper_full_tex = str(paper_path)
            save_session(root, state)

            review = build_citation_support_review(root, provider=MalformedProvider(), evidence_mode="model")

            self.assertEqual(review["items"][0]["support_status"], "needs_manual_check")
            self.assertEqual(review["items"][0]["risk"], "high")
            self.assertEqual(review["_trace"]["parse_error"], "JSONDecodeError")
            self.assertEqual(review["summary"]["needs_manual_check"], 1)

    def test_model_citation_support_accepts_llm_json_with_latex_escapes(self) -> None:
        class LatexEscapeProvider(MockProvider):
            name = "claim-support-latex-escape"

            def complete(self, request: CompletionRequest) -> str:
                return (
                    '{"items":[{"id":"cite-001","support_status":"supported","risk":"low",'
                    '"claim_type":"background","evidence":[{"citation_key":"RFC9001",'
                    '"source_title":"Using TLS to Secure QUIC",'
                    '"url":"https://www.rfc-editor.org/rfc/rfc9001",'
                    '"evidence_quote_or_summary":"The source states that QUIC uses TLS for security.",'
                    '"supports_claim":true}],'
                    '"reasoning":"The cited source supports the prose and mentions \\(QUIC\\).",'
                    '"suggested_fix":"No fix required."}],'
                    '"research_notes":["valid except for unescaped LaTeX delimiters"]}'
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            seed_path = root / "refs.bib"
            seed_path.write_text(
                "@techreport{RFC9001,\n"
                "  title = {Using {TLS} to Secure {QUIC}},\n"
                "  author = {Martin Thomson and Sean Turner},\n"
                "  year = {2021},\n"
                "  url = {https://www.rfc-editor.org/rfc/rfc9001}\n"
                "}\n",
                encoding="utf-8",
            )
            import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
            paper_path = artifact_path(root, "paper.full.tex")
            paper_path.write_text(
                "\\documentclass{article}\n\\begin{document}\n"
                "\\section{Introduction}\n"
                "QUIC can use TLS for security~\\cite{RFC9001}.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            state = load_session(root)
            state.artifacts.paper_full_tex = str(paper_path)
            save_session(root, state)

            review = build_citation_support_review(root, provider=LatexEscapeProvider(), evidence_mode="model")

            self.assertNotIn("parse_error", review["_trace"])
            self.assertEqual(review["items"][0]["support_status"], "supported")
            self.assertEqual(review["summary"]["supported"], 1)

    def test_model_citation_support_supported_requires_evidence_provenance(self) -> None:
        class EvidenceProvider(MockProvider):
            name = "claim-support-test"

            def complete(self, request: CompletionRequest) -> str:
                return json.dumps(
                    {
                        "items": [
                            {
                                "id": "cite-001",
                                "support_status": "supported",
                                "risk": "low",
                                "claim_type": "background",
                                "evidence": [
                                    {
                                        "citation_key": "RFC9001",
                                        "source_title": "Using TLS to Secure QUIC",
                                        "source_url": "https://www.rfc-editor.org/rfc/rfc9001",
                                        "quote_or_summary": "The source describes using TLS to secure QUIC.",
                                        "supports": "supports",
                                    }
                                ],
                                "reasoning": "The source directly supports the protocol background claim.",
                                "suggested_fix": "No fix required.",
                            }
                        ],
                        "research_notes": [],
                    }
                )

        class NoEvidenceProvider(MockProvider):
            name = "claim-support-test"

            def complete(self, request: CompletionRequest) -> str:
                return json.dumps(
                    {
                        "items": [
                            {
                                "id": "cite-001",
                                "support_status": "supported",
                                "risk": "low",
                                "claim_type": "background",
                                "evidence": [],
                                "reasoning": "Trust me.",
                                "suggested_fix": "No fix required.",
                            }
                        ],
                        "research_notes": [],
                    }
                )

        class BadEvidenceProvider(MockProvider):
            name = "claim-support-test"

            def complete(self, request: CompletionRequest) -> str:
                return json.dumps(
                    {
                        "items": [
                            {
                                "id": "cite-001",
                                "support_status": "supported",
                                "risk": "low",
                                "claim_type": "background",
                                "evidence": [{"supports_claim": True}],
                                "reasoning": "Malformed evidence should not pass.",
                                "suggested_fix": "No fix required.",
                            }
                        ],
                        "research_notes": [],
                    }
                )

        class WeakTitleEvidenceProvider(MockProvider):
            name = "claim-support-test"

            def complete(self, request: CompletionRequest) -> str:
                return json.dumps(
                    {
                        "items": [
                            {
                                "id": "cite-001",
                                "support_status": "supported",
                                "risk": "low",
                                "claim_type": "background",
                                "evidence": [
                                    {
                                        "citation_key": "RFC9001",
                                        "source_title": "QUIC",
                                        "evidence_quote_or_summary": "Ambiguous short title evidence.",
                                        "supports_claim": True,
                                    }
                                ],
                                "reasoning": "Weak title should not pass.",
                                "suggested_fix": "No fix required.",
                            }
                        ],
                        "research_notes": [],
                    }
                )

        class PrefixedTitleEvidenceProvider(MockProvider):
            name = "claim-support-test"

            def complete(self, request: CompletionRequest) -> str:
                return json.dumps(
                    {
                        "items": [
                            {
                                "id": "cite-001",
                                "support_status": "supported",
                                "risk": "low",
                                "claim_type": "background",
                                "evidence": [
                                    {
                                        "citation_key": "RFC9001",
                                        "source_title": "RFC 9001: Using TLS to Secure QUIC",
                                        "evidence_quote_or_summary": "RFC 9001 describes how TLS is used to secure QUIC.",
                                        "supports_claim": True,
                                    }
                                ],
                                "reasoning": "The source directly supports the protocol background claim.",
                                "suggested_fix": "No fix required.",
                            }
                        ],
                        "research_notes": [],
                    }
                )

        class CompactPrefixedTitleEvidenceProvider(MockProvider):
            name = "claim-support-test"

            def complete(self, request: CompletionRequest) -> str:
                return json.dumps(
                    {
                        "items": [
                            {
                                "id": "cite-001",
                                "support_status": "supported",
                                "risk": "low",
                                "claim_type": "background",
                                "evidence": [
                                    {
                                        "citation_key": "RFC9001",
                                        "source_title": "RFC9001: Using TLS to Secure QUIC",
                                        "evidence_quote_or_summary": "Compact RFC labels are common in generated evidence.",
                                        "supports_claim": True,
                                    }
                                ],
                                "reasoning": "The source directly supports the protocol background claim.",
                                "suggested_fix": "No fix required.",
                            }
                        ],
                        "research_notes": [],
                    }
                )

        class NearCollisionTitleEvidenceProvider(MockProvider):
            name = "claim-support-test"

            def complete(self, request: CompletionRequest) -> str:
                return json.dumps(
                    {
                        "items": [
                            {
                                "id": "cite-001",
                                "support_status": "supported",
                                "risk": "low",
                                "claim_type": "background",
                                "evidence": [
                                    {
                                        "citation_key": "RFC9001",
                                        "source_title": "Using TLS to Secure QUIC in the Wild",
                                        "evidence_quote_or_summary": "A different paper title that contains the cited title.",
                                        "supports_claim": True,
                                    }
                                ],
                                "reasoning": "Near-title collision should not pass.",
                                "suggested_fix": "No fix required.",
                            }
                        ],
                        "research_notes": [],
                    }
                )

        class SameFamilyWrongTitleEvidenceProvider(MockProvider):
            name = "claim-support-test"

            def complete(self, request: CompletionRequest) -> str:
                return json.dumps(
                    {
                        "items": [
                            {
                                "id": "cite-001",
                                "support_status": "supported",
                                "risk": "low",
                                "claim_type": "background",
                                "evidence": [
                                    {
                                        "citation_key": "RFC9001",
                                        "source_title": "RFC 9001: Something Else",
                                        "evidence_quote_or_summary": "Same RFC identifier but wrong title remainder.",
                                        "supports_claim": True,
                                    }
                                ],
                                "reasoning": "Same-family identifier alone must not validate the evidence title.",
                                "suggested_fix": "No fix required.",
                            }
                        ],
                        "research_notes": [],
                    }
                )

        class SameFamilyNonLabelPrefixEvidenceProvider(MockProvider):
            name = "claim-support-test"

            def complete(self, request: CompletionRequest) -> str:
                return json.dumps(
                    {
                        "items": [
                            {
                                "id": "cite-001",
                                "support_status": "supported",
                                "risk": "low",
                                "claim_type": "background",
                                "evidence": [
                                    {
                                        "citation_key": "RFC9001",
                                        "source_title": "See RFC 9001: Using TLS to Secure QUIC",
                                        "evidence_quote_or_summary": "The title suffix is correct but the prefix is not a source label.",
                                        "supports_claim": True,
                                    }
                                ],
                                "reasoning": "A same-family mention before the title is not provenance identity.",
                                "suggested_fix": "No fix required.",
                            }
                        ],
                        "research_notes": [],
                    }
                )

        class NistPrefixedTitleEvidenceProvider(MockProvider):
            name = "claim-support-test"

            def complete(self, request: CompletionRequest) -> str:
                return json.dumps(
                    {
                        "items": [
                            {
                                "id": "cite-001",
                                "support_status": "supported",
                                "risk": "low",
                                "claim_type": "background",
                                "evidence": [
                                    {
                                        "citation_key": "RFC9001",
                                        "source_title": "NIST SP 800-38D: Using TLS to Secure QUIC",
                                        "evidence_quote_or_summary": "Synthetic standard-document prefix regression.",
                                        "supports_claim": True,
                                    }
                                ],
                                "reasoning": "Different standard-document families must not match by title remainder.",
                                "suggested_fix": "No fix required.",
                            }
                        ],
                        "research_notes": [],
                    }
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            seed_path = root / "refs.bib"
            seed_path.write_text(
                "@techreport{RFC9001,\n"
                "  title = {Using {TLS} to Secure {QUIC}},\n"
                "  author = {Martin Thomson and Sean Turner},\n"
                "  year = {2021},\n"
                "  url = {https://www.rfc-editor.org/rfc/rfc9001}\n"
                "}\n",
                encoding="utf-8",
            )
            import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
            paper_path = artifact_path(root, "paper.full.tex")
            paper_path.write_text(
                "\\documentclass{article}\n\\begin{document}\n"
                "\\section{Introduction}\n"
                "QUIC can use TLS for security~\\cite{RFC9001}.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            state = load_session(root)
            state.artifacts.paper_full_tex = str(paper_path)
            save_session(root, state)

            supported = build_citation_support_review(root, provider=EvidenceProvider(), evidence_mode="model")
            no_evidence = build_citation_support_review(root, provider=NoEvidenceProvider(), evidence_mode="model")
            bad_evidence = build_citation_support_review(root, provider=BadEvidenceProvider(), evidence_mode="model")
            weak_title = build_citation_support_review(root, provider=WeakTitleEvidenceProvider(), evidence_mode="model")
            prefixed_title = build_citation_support_review(root, provider=PrefixedTitleEvidenceProvider(), evidence_mode="model")
            compact_prefixed_title = build_citation_support_review(
                root,
                provider=CompactPrefixedTitleEvidenceProvider(),
                evidence_mode="model",
            )
            near_collision = build_citation_support_review(root, provider=NearCollisionTitleEvidenceProvider(), evidence_mode="model")
            same_family_wrong_title = build_citation_support_review(
                root,
                provider=SameFamilyWrongTitleEvidenceProvider(),
                evidence_mode="model",
            )
            same_family_non_label_prefix = build_citation_support_review(
                root,
                provider=SameFamilyNonLabelPrefixEvidenceProvider(),
                evidence_mode="model",
            )
            nist_prefixed_title = build_citation_support_review(
                root,
                provider=NistPrefixedTitleEvidenceProvider(),
                evidence_mode="model",
            )

            self.assertEqual(supported["items"][0]["support_status"], "supported")
            self.assertEqual(supported["items"][0]["evidence"][0]["url"], "https://www.rfc-editor.org/rfc/rfc9001")
            self.assertTrue(supported["items"][0]["evidence"][0]["supports_claim"])
            self.assertEqual(no_evidence["items"][0]["support_status"], "needs_manual_check")
            self.assertEqual(bad_evidence["items"][0]["support_status"], "needs_manual_check")
            self.assertEqual(weak_title["items"][0]["support_status"], "needs_manual_check")
            self.assertEqual(prefixed_title["items"][0]["support_status"], "supported")
            self.assertEqual(compact_prefixed_title["items"][0]["support_status"], "supported")
            self.assertEqual(near_collision["items"][0]["support_status"], "needs_manual_check")
            self.assertEqual(same_family_wrong_title["items"][0]["support_status"], "needs_manual_check")
            self.assertEqual(same_family_non_label_prefix["items"][0]["support_status"], "needs_manual_check")
            self.assertEqual(nist_prefixed_title["items"][0]["support_status"], "needs_manual_check")

    def test_web_citation_support_rejects_explicit_non_search_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper_path = artifact_path(root, "paper.full.tex")
            paper_path.write_text(
                "\\documentclass{article}\n\\begin{document}\n"
                "\\section{Introduction}\n"
                "QUIC can use TLS for security~\\cite{missing}.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper_path)
            save_session(root, state)
            stdout = io.StringIO()
            stderr = io.StringIO()
            old_cwd = os.getcwd()
            try:
                os.chdir(root)
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    code = cli_main(
                        [
                            "review-citations",
                            "--evidence-mode",
                            "web",
                            "--provider",
                            "shell",
                            "--provider-command",
                            '["codex","exec","--search","--skip-git-repo-check"]',
                        ]
                    )
            finally:
                os.chdir(old_cwd)

            self.assertEqual(code, 1)
            self.assertIn("requires a Codex shell provider command containing --search", stderr.getvalue())

    def test_review_citations_cli_model_mode_writes_s2_independent_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            seed_path = root / "refs.bib"
            seed_path.write_text(
                "@techreport{RFC9001,\n"
                "  title = {Using {TLS} to Secure {QUIC}},\n"
                "  author = {Martin Thomson and Sean Turner},\n"
                "  year = {2021}\n"
                "}\n",
                encoding="utf-8",
            )
            import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
            paper_path = artifact_path(root, "paper.full.tex")
            paper_path.write_text(
                "\\documentclass{article}\n\\begin{document}\n"
                "\\section{Introduction}\n"
                "QUIC can use TLS for security~\\cite{RFC9001}.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            state = load_session(root)
            state.artifacts.paper_full_tex = str(paper_path)
            save_session(root, state)
            output_path = root / "citation_support_review.json"
            stdout = io.StringIO()
            old_cwd = os.getcwd()
            try:
                os.chdir(root)
                with patch("paperorchestra.literature.search_semantic_scholar", side_effect=AssertionError("S2 called")):
                    with contextlib.redirect_stdout(stdout):
                        code = cli_main(
                            [
                                "review-citations",
                                "--evidence-mode",
                                "model",
                                "--provider",
                                "mock",
                                "--output",
                                str(output_path),
                            ]
                        )
            finally:
                os.chdir(old_cwd)

            self.assertEqual(code, 0)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["review_mode"], "model")
            self.assertFalse(payload["evidence_provenance"]["semantic_scholar_required"])
            self.assertEqual(payload["items"][0]["support_status"], "needs_manual_check")

    def test_mcp_review_citations_model_mode_writes_claim_support_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            seed_path = root / "refs.bib"
            seed_path.write_text(
                "@techreport{RFC9001,\n"
                "  title = {Using {TLS} to Secure {QUIC}},\n"
                "  author = {Martin Thomson and Sean Turner},\n"
                "  year = {2021}\n"
                "}\n",
                encoding="utf-8",
            )
            import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
            paper_path = artifact_path(root, "paper.full.tex")
            paper_path.write_text(
                "\\documentclass{article}\n\\begin{document}\n"
                "\\section{Introduction}\n"
                "QUIC can use TLS for security~\\cite{RFC9001}.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            state = load_session(root)
            state.artifacts.paper_full_tex = str(paper_path)
            save_session(root, state)

            result = TOOL_HANDLERS["review_citations"](
                {"cwd": str(root), "evidence_mode": "model", "provider": "mock"}
            )

            self.assertFalse(result["isError"])
            path = Path(json.loads(result["content"][0]["text"])["path"])
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["review_mode"], "model")
            self.assertFalse(payload["evidence_provenance"]["semantic_scholar_required"])

    def test_mcp_schemas_expose_citation_evidence_modes(self) -> None:
        tools = {tool["name"]: tool for tool in MCP_TOOLS}
        review_props = tools["review_citations"]["inputSchema"]["properties"]
        critique_props = tools["critique"]["inputSchema"]["properties"]
        apply_props = tools["apply_operator_feedback"]["inputSchema"]["properties"]

        self.assertIn("evidence_mode", review_props)
        self.assertEqual(review_props["evidence_mode"]["default"], "heuristic")
        self.assertIn("provider", review_props)
        self.assertIn("provider_command", review_props)
        self.assertIn("citation_evidence_mode", critique_props)
        self.assertEqual(critique_props["citation_evidence_mode"]["default"], "heuristic")
        self.assertEqual(apply_props["citation_evidence_mode"]["default"], "web")
        self.assertEqual(apply_props["citation_evidence_mode"]["enum"], ["heuristic", "model", "web"])

    def test_cli_claim_safe_feedback_defaults_to_web_citation_evidence(self) -> None:
        parser = build_parser()

        qa_args = parser.parse_args(["qa-loop-step"])
        apply_args = parser.parse_args(["apply-operator-feedback", "--imported-feedback", "feedback.imported.json"])

        self.assertEqual(qa_args.citation_evidence_mode, "web")
        self.assertEqual(apply_args.citation_evidence_mode, "web")

    def test_qa_loop_plan_supervised_handoff_uses_canonical_packet_sha(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")

            _, plan = write_quality_loop_plan(root, quality_mode="claim_safe")
            plan["verdict"] = "human_needed"
            plan["repair_actions"] = [{"code": "missing_prompt_trace", "automation": "human_needed"}]
            plan_path = artifact_path(root, "qa-loop.plan.json")
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")

            _, plan = write_quality_loop_plan(root, quality_mode="claim_safe")

            entry = plan["supervised_handoff"]["operator_feedback_entry"]
            self.assertEqual(entry["packet_path"], str(packet_path))
            self.assertEqual(entry["packet_sha256"], packet["packet_sha256"])
            self.assertNotEqual(entry["packet_sha256"], __import__("hashlib").sha256(Path(packet_path).read_bytes()).hexdigest())

    def test_operator_feedback_public_surfaces_are_explicit_only(self) -> None:
        cli_parser = cli_main.__globals__["build_parser"]()
        cli_commands = set(cli_parser._subparsers._group_actions[0].choices)
        self.assertTrue(OPERATOR_PUBLIC_ENTRYPOINTS.issubset(cli_commands))
        self.assertFalse({"operator-feedback", "write-operator-feedback", "author-operator-feedback"} & cli_commands)

        mcp_names = {tool["name"] for tool in MCP_TOOLS}
        self.assertTrue({"build_operator_review_packet", "import_operator_feedback", "apply_operator_feedback"}.issubset(mcp_names))
        self.assertIn("critique", mcp_names)
        self.assertIn("suggest_revisions", mcp_names)
        self.assertIn("refine_current_paper", mcp_names)
        self.assertIn("build_operator_review_packet", TOOL_HANDLERS)
        self.assertIn("import_operator_feedback", TOOL_HANDLERS)
        self.assertIn("apply_operator_feedback", TOOL_HANDLERS)

    def test_qa_loop_bridge_exit_codes_and_progress_delta(self) -> None:
        self.assertEqual(qa_loop_exit_code("ready_for_human_finalization"), 0)
        self.assertEqual(qa_loop_exit_code("continue"), 10)
        self.assertEqual(qa_loop_exit_code("human_needed"), 20)
        self.assertEqual(qa_loop_exit_code("failed"), 30)
        self.assertEqual(qa_loop_exit_code("unknown"), 40)

        before = {"manuscript_hash": "sha256:before", "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_unsupported", "citation_support_weak"]}}}
        after = {"manuscript_hash": "sha256:after", "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_weak"]}}}
        delta = compute_progress_delta(before, after, {"unsupported": 1, "weakly_supported": 2}, {"weakly_supported": 1})
        self.assertTrue(delta["forward_progress"])
        self.assertEqual(delta["resolved_codes"], ["citation_support_unsupported"])
        self.assertEqual(delta["citation_issue_delta"], -2)

        same_before = {"manuscript_hash": "sha256:same", "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_unsupported", "citation_support_weak"]}}}
        same_after = {"manuscript_hash": "sha256:same", "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_weak"]}}}
        same_delta = compute_progress_delta(same_before, same_after, {"unsupported": 1, "weakly_supported": 2}, {"weakly_supported": 1})
        self.assertFalse(same_delta["forward_progress"])
        self.assertTrue(same_delta["same_manuscript_as_previous"])
        unknown_delta = compute_progress_delta(
            {"tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_weak"]}}},
            {"tiers": {"tier_2_claim_safety": {"status": "pass", "failing_codes": []}}},
            {"weakly_supported": 1},
            {"supported": 1},
        )
        self.assertFalse(unknown_delta["manuscript_identity_known"])
        self.assertFalse(unknown_delta["forward_progress"])

    def test_quality_loop_cross_iteration_blocks_same_manuscript_failure_drift_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = root / ".paper-orchestra"
            runtime.mkdir()
            (runtime / "qa-loop-history.jsonl").write_text(
                json.dumps(
                    {
                        "session_id": "s1",
                        "event_type": "qa_loop_step",
                        "consumes_budget": True,
                        "manuscript_hash": "sha256:same",
                        "failing_codes": ["citation_support_unsupported", "citation_support_weak"],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            cross = _build_cross_iteration(
                root,
                "s1",
                "sha256:same",
                ["citation_support_weak"],
                10,
                current_attempt_consumes_budget=True,
            )
            self.assertTrue(cross["regression"]["same_manuscript_as_previous"])
            self.assertFalse(cross["regression"]["forward_progress"])

    def test_citation_support_review_reuses_same_session_web_review(self) -> None:
        class CountingCitationProvider(MockProvider):
            def __init__(self) -> None:
                self.call_count = 0

            def complete(self, request: CompletionRequest) -> str:
                self.call_count += 1
                ids = ["cite-001"]
                return json.dumps(
                    {
                        "items": [
                            {
                                "id": item_id,
                                "support_status": "supported",
                                "risk": "low",
                                "claim_type": "background",
                                "evidence": [
                                    {
                                        "citation_key": "A",
                                        "source_title": "Synthetic Source",
                                        "url": "https://example.test/source",
                                        "evidence_quote_or_summary": "Synthetic source supports the synthetic claim.",
                                        "supports_claim": True,
                                    }
                                ],
                                "reasoning": "Synthetic cited source directly supports the claim.",
                                "suggested_fix": "",
                            }
                            for item_id in ids
                        ],
                        "research_notes": ["synthetic stable evidence"],
                    }
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\nSynthetic claim. \\cite{A}\n\\end{document}\n",
                encoding="utf-8",
            )
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(
                json.dumps({"A": {"title": "Synthetic Source", "url": "https://example.test/source", "authors": ["A. Author"], "year": 2026}}),
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)
            provider = CountingCitationProvider()

            first = write_citation_support_review(root, provider=provider, evidence_mode="web")
            first_text = first.read_text(encoding="utf-8")
            second = write_citation_support_review(root, provider=provider, evidence_mode="web")

            self.assertEqual(provider.call_count, 2)
            self.assertEqual(second.read_text(encoding="utf-8"), first_text)
            payload = json.loads(second.read_text(encoding="utf-8"))
            provenance = payload["evidence_provenance"]
            self.assertEqual(provenance["cache_scope"], "session_id")
            self.assertIn("cache_key_sha256", provenance)
            self.assertIn("retrieved_web_evidence_sha256", provenance)
            self.assertEqual(provenance["evidence_identity_source"], "pre_review_retrieved_evidence_artifact")
            retrieved_evidence_path = Path(provenance["retrieved_web_evidence_path"])
            self.assertTrue(retrieved_evidence_path.exists())

            original_cache_key = provenance["cache_key_sha256"]
            retrieved_payload = json.loads(retrieved_evidence_path.read_text(encoding="utf-8"))
            retrieved_payload["research_notes"] = ["synthetic changed retrieved evidence"]
            retrieved_evidence_path.write_text(json.dumps(retrieved_payload, indent=2), encoding="utf-8")
            changed_evidence = write_citation_support_review(root, provider=provider, evidence_mode="web")
            changed_provenance = json.loads(changed_evidence.read_text(encoding="utf-8"))["evidence_provenance"]
            self.assertEqual(provider.call_count, 3)
            self.assertNotEqual(changed_provenance["cache_key_sha256"], original_cache_key)

            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\nChanged synthetic claim. \\cite{A}\n\\end{document}\n",
                encoding="utf-8",
            )
            write_citation_support_review(root, provider=provider, evidence_mode="web")
            self.assertEqual(provider.call_count, 5)

            citation_map.write_text(
                json.dumps({"A": {"title": "Synthetic Source Changed", "url": "https://example.test/source", "authors": ["A. Author"], "year": 2026}}),
                encoding="utf-8",
            )
            write_citation_support_review(root, provider=provider, evidence_mode="web")
            self.assertEqual(provider.call_count, 7)

    def test_web_citation_evidence_retrieval_is_chunked_for_large_claim_sets(self) -> None:
        class ChunkObservingProvider(MockProvider):
            def __init__(self) -> None:
                self.retrieval_chunk_sizes: list[int] = []
                self.review_calls = 0

            def _input_items(self, request: CompletionRequest) -> list[dict[str, Any]]:
                marker = "Input:\n"
                payload = request.user_prompt.split(marker, 1)[1]
                if "\n\nA separate pre-review" in payload:
                    payload = payload.split("\n\nA separate pre-review", 1)[0]
                return json.loads(payload)["items"]

            def complete(self, request: CompletionRequest) -> str:
                items = self._input_items(request)
                if "citation-support evidence retriever" in request.system_prompt:
                    self.retrieval_chunk_sizes.append(len(items))
                    return json.dumps(
                        {
                            "items": [
                                {
                                    "id": item["id"],
                                    "evidence": [
                                        {
                                            "citation_key": item["citation_keys"][0],
                                            "source_title": f"Synthetic Source {item['citation_keys'][0]}",
                                            "url": f"https://example.test/{item['citation_keys'][0]}",
                                            "evidence_quote_or_summary": "Synthetic source directly supports the synthetic claim.",
                                            "supports_claim": True,
                                        }
                                    ],
                                }
                                for item in items
                            ],
                            "research_notes": ["chunked synthetic retrieval"],
                        }
                    )
                self.review_calls += 1
                return json.dumps(
                    {
                        "items": [
                            {
                                "id": item["id"],
                                "support_status": "supported",
                                "risk": "low",
                                "claim_type": item.get("claim_type") or "background",
                                "evidence": [
                                    {
                                        "citation_key": item["citation_keys"][0],
                                        "source_title": f"Synthetic Source {item['citation_keys'][0]}",
                                        "url": f"https://example.test/{item['citation_keys'][0]}",
                                        "evidence_quote_or_summary": "Synthetic source directly supports the synthetic claim.",
                                        "supports_claim": True,
                                    }
                                ],
                                "reasoning": "Synthetic cited source directly supports the claim.",
                                "suggested_fix": "",
                            }
                            for item in items
                        ],
                        "research_notes": ["synthetic review"],
                    }
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n"
                + "\n".join(f"Synthetic claim {i}. \\cite{{A{i}}}" for i in range(1, 10))
                + "\n\\end{document}\n",
                encoding="utf-8",
            )
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(
                json.dumps(
                    {
                        f"A{i}": {
                            "title": f"Synthetic Source A{i}",
                            "url": f"https://example.test/A{i}",
                            "authors": ["A. Author"],
                            "year": 2026,
                        }
                        for i in range(1, 10)
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)

            provider = ChunkObservingProvider()
            path = write_citation_support_review(root, provider=provider, evidence_mode="web")
            payload = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(provider.retrieval_chunk_sizes, [8, 1])
            self.assertEqual(provider.review_calls, 1)
            self.assertEqual(payload["summary"], {"supported": 9})
            retrieved_path = Path(payload["evidence_provenance"]["retrieved_web_evidence_path"])
            self.assertTrue(_retrieved_web_evidence_is_reusable(json.loads(retrieved_path.read_text(encoding="utf-8"))))

    def test_malformed_web_retrieval_is_not_cached_as_citation_review(self) -> None:
        class FlakyRetrievalProvider(MockProvider):
            def __init__(self) -> None:
                self.call_count = 0

            def complete(self, request: CompletionRequest) -> str:
                self.call_count += 1
                if "citation-support evidence retriever" in request.system_prompt:
                    if self.call_count == 1:
                        return '{"items": ['
                    return json.dumps(
                        {
                            "items": [
                                {
                                    "id": "cite-001",
                                    "evidence": [
                                        {
                                            "citation_key": "A",
                                            "source_title": "Synthetic Source",
                                            "url": "https://example.test/source",
                                            "evidence_quote_or_summary": "Synthetic source directly supports the synthetic claim.",
                                            "supports_claim": True,
                                        }
                                    ],
                                }
                            ],
                            "research_notes": ["valid retry retrieval"],
                        }
                    )
                status = "needs_manual_check" if self.call_count == 2 else "supported"
                return json.dumps(
                    {
                        "items": [
                            {
                                "id": "cite-001",
                                "support_status": status,
                                "risk": "medium" if status == "needs_manual_check" else "low",
                                "claim_type": "background",
                                "evidence": [
                                    {
                                        "citation_key": "A",
                                        "source_title": "Synthetic Source",
                                        "url": "https://example.test/source",
                                        "evidence_quote_or_summary": "Synthetic source directly supports the synthetic claim.",
                                        "supports_claim": status == "supported",
                                    }
                                ],
                                "reasoning": "Synthetic review.",
                                "suggested_fix": "",
                            }
                        ],
                        "research_notes": ["synthetic review"],
                    }
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\nSynthetic claim. \\cite{A}\n\\end{document}\n", encoding="utf-8")
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(
                json.dumps({"A": {"title": "Synthetic Source", "url": "https://example.test/source", "authors": ["A. Author"], "year": 2026}}),
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)
            provider = FlakyRetrievalProvider()

            first = write_citation_support_review(root, provider=provider, evidence_mode="web")
            first_payload = json.loads(first.read_text(encoding="utf-8"))
            self.assertEqual(provider.call_count, 2)
            self.assertNotIn("cache_key_sha256", first_payload["evidence_provenance"])

            second = write_citation_support_review(root, provider=provider, evidence_mode="web")
            second_payload = json.loads(second.read_text(encoding="utf-8"))
            self.assertEqual(provider.call_count, 4)
            self.assertEqual(second_payload["summary"], {"supported": 1})
            self.assertIn("cache_key_sha256", second_payload["evidence_provenance"])

    def test_retrieved_web_evidence_reusability_allows_some_metadata_only_items(self) -> None:
        self.assertTrue(
            _retrieved_web_evidence_is_reusable(
                {
                    "items": [
                        {"id": "cite-001", "evidence": [{"citation_key": "A"}]},
                        {"id": "cite-002", "evidence": []},
                    ],
                    "trace": {"schema_version": "citation-support-retrieval-trace/1"},
                }
            )
        )
        self.assertFalse(
            _retrieved_web_evidence_is_reusable(
                {
                    "items": [
                        {"id": "cite-001", "evidence": []},
                        {"id": "cite-002", "evidence": []},
                    ],
                    "trace": {"schema_version": "citation-support-retrieval-trace/1"},
                }
            )
        )
        self.assertFalse(
            _retrieved_web_evidence_is_reusable(
                {
                    "items": [{"id": "cite-001", "evidence": [{"citation_key": "A"}]}],
                    "trace": {
                        "schema_version": "citation-support-retrieval-trace/1",
                        "chunk_traces": [{"parse_error": "JSONDecodeError"}],
                    },
                }
            )
        )

    def test_citation_support_cache_key_includes_shell_provider_command_digest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\nSynthetic claim. \\cite{A}\n\\end{document}\n", encoding="utf-8")
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(json.dumps({"A": {"title": "Synthetic Source"}}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)

            provider_a = ShellProvider(command="codex --model gpt-a")
            provider_b = ShellProvider(command="codex --model gpt-b")
            key_a = _citation_support_cache_key(state, provider_a, "web", retrieved_web_evidence_sha256="sha256:evidence")
            key_b = _citation_support_cache_key(state, provider_b, "web", retrieved_web_evidence_sha256="sha256:evidence")

            self.assertNotEqual(key_a, key_b)

    def test_final_citation_review_must_match_quality_eval_gate_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review_a = root / "citation-a.json"
            review_b = root / "citation-b.json"
            review_a.write_text(json.dumps({"summary": {"supported": 1}}), encoding="utf-8")
            review_b.write_text(json.dumps({"summary": {"unsupported": 1}}), encoding="utf-8")
            quality_eval = root / "quality-eval.json"
            quality_eval.write_text(
                json.dumps({"source_artifacts": {"citation_review_sha256": hashlib.sha256(review_b.read_bytes()).hexdigest()}}),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                ensure_final_citation_review_bound_to_quality_eval(quality_eval, review_a)
            result = ensure_final_citation_review_bound_to_quality_eval(quality_eval, review_b)
            self.assertEqual(result["status"], "pass")

    def test_qa_loop_brief_contains_omx_handoff_and_no_success_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nBody.\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)

            brief = build_qa_loop_brief(root, quality_mode="claim_safe")

            self.assertIn("omx ralph --prd", brief)
            for verdict in ["continue", "human_needed", "ready_for_human_finalization", "failed"]:
                self.assertIn(verdict, brief)
            self.assertIn("There is no terminal state named `success`", brief)
            self.assertIn("paperorchestra qa-loop-step --quality-mode claim_safe", brief)
            self.assertIn("[OMX_TMUX_INJECT]", brief)
            self.assertIn("PAPERO_MODEL_CMD is required", brief)
            self.assertIn("## Exit code contract", brief)

    def test_qa_loop_brief_prioritizes_executable_actions_over_human_needed_sidecars(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nBody.\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            quality_eval_path = root / "quality-eval.synthetic.json"
            quality_eval_path.write_text(
                json.dumps(
                    {
                        "session_id": state.session_id,
                        "mode": "claim_safe",
                        "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_weak"]}},
                    }
                ),
                encoding="utf-8",
            )
            plan_path = root / "qa-loop.plan.synthetic.json"
            plan_path.write_text(
                json.dumps(
                    {
                        "verdict": "continue",
                        "repair_actions": [
                            {"code": "fidelity_runtime_parity_missing", "automation": "human_needed", "reason": "Sidecar human issue."},
                            {"code": "citation_support_critic_failed", "automation": "semi_auto", "reason": "Executable citation repair."},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            brief = build_qa_loop_brief(root, quality_eval_path=quality_eval_path, plan_path=plan_path)

            executable_section = brief.split("## Executable repair actions", 1)[1].split("## Human-needed", 1)[0]
            self.assertIn("citation_support_critic_failed", executable_section)
            self.assertNotIn("fidelity_runtime_parity_missing", executable_section)
            self.assertIn("do not stop only because separate human-needed actions are also listed", brief)

    def test_next_ralph_instruction_uses_supported_executable_action(self) -> None:
        instruction = _next_ralph_instruction(
            "continue",
            [
                {"code": "fidelity_runtime_parity_missing", "automation": "human_needed", "ralph_instruction": "Ask a human."},
                {
                    "code": "citation_support_critic_failed",
                    "automation": "semi_auto",
                    "ralph_instruction": "Repair cited claims.",
                    "suggested_commands": ["paperorchestra repair-citation-claims"],
                },
            ],
        )

        self.assertIn("executable action citation_support_critic_failed", instruction)
        self.assertIn("Repair cited claims", instruction)
        self.assertNotIn("Ask a human", instruction)

    def test_repair_citation_claims_softens_sentence_and_rejects_unknown_citation(self) -> None:
        class RepairProvider(MockProvider):
            def __init__(self, latex: str):
                self.latex = latex
                self.prompt = ""

            def complete(self, request: CompletionRequest) -> str:
                self.prompt = request.user_prompt
                return "```latex\n" + self.latex + "\n```"

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            seed_path = root / "refs.bib"
            seed_path.write_text(
                "@techreport{RFC9001,\n"
                "  title = {Using {TLS} to Secure {QUIC}},\n"
                "  author = {Martin Thomson and Sean Turner},\n"
                "  year = {2021},\n"
                "  url = {https://www.rfc-editor.org/rfc/rfc9001}\n"
                "}\n",
                encoding="utf-8",
            )
            import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
            paper = artifact_path(root, "paper.full.tex")
            original = (
                "\\documentclass{article}\n\\begin{document}\n"
                "\\section{Intro}\n"
                "QUIC is always faster than every transport~\\cite{RFC9001}.\n"
                "\\bibliographystyle{plain}\n\\bibliography{references}\n"
                "\\end{document}\n"
            )
            paper.write_text(original, encoding="utf-8")
            state = load_session(root)
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            review_path = artifact_path(root, "citation_support_review.json")
            review_path.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "id": "cite-001",
                                "sentence": "QUIC is always faster than every transport~\\cite{RFC9001}.",
                                "citation_keys": ["RFC9001"],
                                "support_status": "unsupported",
                                "risk": "high",
                                "suggested_fix": "Soften the claim to a source-supported protocol statement.",
                            }
                        ],
                        "summary": {"unsupported": 1},
                    }
                ),
                encoding="utf-8",
            )
            repaired_latex = original.replace(
                "QUIC is always faster than every transport~\\cite{RFC9001}.",
                "RFC 9001 describes how TLS is used to secure QUIC~\\cite{RFC9001}.",
            )
            provider = RepairProvider(repaired_latex)

            result = repair_citation_claims(root, provider, citation_review_path=review_path)

            self.assertTrue(result["accepted"])
            self.assertFalse(result["committed"])
            self.assertIn("citation_support_issues.json", provider.prompt)
            self.assertNotIn("overall_score", provider.prompt)
            self.assertIn("QUIC is always faster", paper.read_text(encoding="utf-8"))
            self.assertIn("TLS is used to secure QUIC", Path(result["candidate_path"]).read_text(encoding="utf-8"))

            bad_provider = RepairProvider(repaired_latex.replace("\\cite{RFC9001}", "\\cite{FakeNew}"))
            paper.write_text(original, encoding="utf-8")
            bad_result = repair_citation_claims(root, bad_provider, citation_review_path=review_path)
            self.assertFalse(bad_result["accepted"])
            self.assertEqual(bad_result["reason"], "unknown_citation_keys")
            self.assertIn("QUIC is always faster", paper.read_text(encoding="utf-8"))

    def test_ralph_start_dry_run_cli_does_not_launch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nBody.\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            stdout = io.StringIO()
            old_cwd = os.getcwd()
            try:
                os.chdir(root)
                with patch("paperorchestra.cli.launch_omx_ralph", side_effect=AssertionError("should not launch")):
                    with contextlib.redirect_stdout(stdout):
                        code = cli_main(["ralph-start", "--dry-run", "--max-iterations", "5", "--require-live-verification"])
            finally:
                os.chdir(old_cwd)
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["launch"]["status"], "dry_run")
            self.assertIn("omx ralph --prd", payload["suggested_command"])
            self.assertIn("--max-iterations 5", payload["argv"][3])
            self.assertEqual(payload["schema_version"], "paperorchestra-ralph-handoff/1")
            self.assertEqual(payload["hook_contract"]["marker"], "[OMX_TMUX_INJECT]")
            self.assertEqual(payload["hook_contract"]["continuation_exit_code"], 10)
            self.assertTrue(payload["execution_contract"]["require_live_verification"])
            self.assertIn("PAPERO_MODEL_CMD", payload["execution_contract"]["step_command"])
            self.assertTrue(Path(payload["handoff_path"]).exists())
            self.assertTrue(Path(payload["canonical_prd_path"]).exists())
            self.assertTrue(Path(payload["canonical_test_spec_path"]).exists())
            self.assertTrue(Path(payload["prd_path"]).exists())
            prd = json.loads(Path(payload["prd_path"]).read_text(encoding="utf-8"))
            self.assertEqual(prd["project"], "PaperOrchestra Ralph QA Loop")

    def test_ralph_start_launch_calls_omx_ralph_explicitly(self) -> None:
        class FakeProc:
            pid = 4242

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nBody.\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            stdout = io.StringIO()
            old_cwd = os.getcwd()
            try:
                os.chdir(root)
                with patch("paperorchestra.cli.launch_omx_ralph", return_value=FakeProc()) as launcher:
                    with contextlib.redirect_stdout(stdout):
                        code = cli_main(["ralph-start", "--launch"])
            finally:
                os.chdir(old_cwd)
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["launch"], {"pid": 4242, "status": "started"})
            argv = launcher.call_args.args[0]
            self.assertEqual(argv[:3], ["omx", "ralph", "--prd"])
            self.assertIn("PaperOrchestra Ralph Brief", argv[3])

    def test_qa_loop_planning_surfaces_do_not_consume_execution_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            seed_path = root / "refs.bib"
            seed_path.write_text(
                "@techreport{RFC9001,\n"
                "  title = {Using {TLS} to Secure {QUIC}},\n"
                "  author = {Martin Thomson and Sean Turner},\n"
                "  year = {2021},\n"
                "  url = {https://www.rfc-editor.org/rfc/rfc9001}\n"
                "}\n",
                encoding="utf-8",
            )
            import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\n"
                "QUIC uses TLS~\\cite{RFC9001}.\n"
                "\\bibliographystyle{plain}\n\\bibliography{references}\n\\end{document}\n",
                encoding="utf-8",
            )
            state = load_session(root)
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            record_current_validation_report(root, name="validation.current.json")
            write_figure_placement_review(root)

            for _ in range(5):
                write_quality_loop_plan(root, quality_mode="claim_safe", max_iterations=5)
                build_qa_loop_brief(root, quality_mode="claim_safe", max_iterations=5)
                build_ralph_start_payload(root, quality_mode="claim_safe", max_iterations=5)

            history_path = root / ".paper-orchestra" / "qa-loop-history.jsonl"
            history = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines()]
            self.assertGreaterEqual(len(history), 5)
            self.assertTrue(all(entry["event_type"] == "qa_loop_plan" for entry in history))
            self.assertTrue(all(entry["consumes_budget"] is False for entry in history))

            _, quality_eval = write_quality_eval(root, quality_mode="claim_safe", max_iterations=5)
            self.assertEqual(quality_eval["cross_iteration"]["budget"]["attempts_used"], 0)
            self.assertEqual(quality_eval["cross_iteration"]["budget"]["remaining"], 5)
            _, plan = write_quality_loop_plan(root, quality_mode="claim_safe", max_iterations=5)
            self.assertNotEqual(plan["verdict"], "failed")

    def test_quality_loop_budget_is_session_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            history_path = root / ".paper-orchestra" / "qa-loop-history.jsonl"
            history_path.parent.mkdir(parents=True, exist_ok=True)
            history_path.write_text(
                "\n".join(
                    json.dumps(
                        {
                            "session_id": "po-other",
                            "event_type": "qa_loop_step",
                            "consumes_budget": True,
                            "manuscript_hash": "sha256:other",
                            "failing_codes": ["citation_support_weak"],
                        }
                    )
                    for _ in range(7)
                )
                + "\n",
                encoding="utf-8",
            )
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\nBody.\n\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)

            _, quality_eval = write_quality_eval(root, quality_mode="claim_safe", max_iterations=5)

            budget = quality_eval["cross_iteration"]["budget"]
            self.assertEqual(quality_eval["session_id"], state.session_id)
            self.assertEqual(budget["attempts_used"], 0)
            self.assertEqual(budget["remaining"], 5)
            self.assertEqual(quality_eval["cross_iteration"]["iteration_index"], 1)

    def test_quality_loop_plan_stops_after_budgeted_no_progress_with_supported_repairs(self) -> None:
        quality_eval = {
            "tiers": {
                "tier_2_claim_safety": {
                    "status": "fail",
                    "failing_codes": ["citation_support_weak"],
                }
            },
            "cross_iteration": {
                "budget": {
                    "remaining": 3,
                    "current_attempt_consumes_budget": True,
                },
                "regression": {
                    "forward_progress": False,
                    "oscillation": {"detected": False, "flapping_codes": []},
                    "tier_3_axis_drops": [],
                },
            },
        }
        actions = [{"code": "citation_support_critic_failed", "automation": "semi_auto"}]

        verdict, rationale = _plan_verdict(quality_eval, actions, accept_mixed_provenance=False)

        self.assertEqual(verdict, "human_needed")
        self.assertIn("no forward progress", rationale)

        quality_eval["cross_iteration"]["budget"]["current_attempt_consumes_budget"] = False
        verdict, _ = _plan_verdict(quality_eval, actions, accept_mixed_provenance=False)
        self.assertEqual(verdict, "continue")

    def test_section_process_residue_is_non_reviewable_failure(self) -> None:
        quality_eval = {
            "tiers": {
                "tier_0_preconditions": {"status": "pass"},
                "tier_1_structural": {"status": "pass"},
                "tier_2_claim_safety": {"status": "pass"},
                "tier_3_scholarly_quality": {
                    "status": "fail",
                    "checks": {
                        "section_quality_critic": {
                            "status": "fail",
                            "path": "section_review.json",
                            "failing_codes": ["section_process_residue_detected"],
                        }
                    },
                    "failing_codes": ["section_process_residue_detected"],
                },
            },
            "cross_iteration": {
                "budget": {"remaining": 3, "current_attempt_consumes_budget": False},
                "regression": {"forward_progress": True, "oscillation": {"detected": False}, "tier_3_axis_drops": []},
            },
        }
        actions = _quality_eval_actions(quality_eval)

        verdict, rationale = _plan_verdict(quality_eval, actions, accept_mixed_provenance=False)

        self.assertEqual(verdict, "failed")
        self.assertIn("non-reviewable", rationale)

    def test_mixed_provenance_boolean_without_acceptance_artifact_is_not_ready(self) -> None:
        quality_eval = {
            "provenance_trust": {
                "level": "mixed",
                "mixed_acceptance": {"status": "missing", "failing_codes": ["mixed_provenance_acceptance_missing"]},
            },
            "tiers": {
                "tier_0_preconditions": {"status": "pass"},
                "tier_1_structural": {"status": "pass"},
                "tier_2_claim_safety": {"status": "pass"},
                "tier_3_scholarly_quality": {"status": "pass"},
            },
            "cross_iteration": {
                "budget": {"remaining": 3, "current_attempt_consumes_budget": False},
                "regression": {"forward_progress": True, "oscillation": {"detected": False}, "tier_3_axis_drops": []},
            },
        }

        verdict, _ = _plan_verdict(quality_eval, [], accept_mixed_provenance=True)

        self.assertEqual(verdict, "human_needed")

    def test_qa_loop_step_is_the_budget_consuming_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            seed_path = root / "refs.bib"
            seed_path.write_text(
                "@techreport{RFC9001,\n"
                "  title = {Using {TLS} to Secure {QUIC}},\n"
                "  author = {Martin Thomson and Sean Turner},\n"
                "  year = {2021},\n"
                "  url = {https://www.rfc-editor.org/rfc/rfc9001}\n"
                "}\n",
                encoding="utf-8",
            )
            import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\n"
                "QUIC uses TLS~\\cite{RFC9001}.\n"
                "\\bibliographystyle{plain}\n\\bibliography{references}\n\\end{document}\n",
                encoding="utf-8",
            )
            state = load_session(root)
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            record_current_validation_report(root, name="validation.current.json")
            write_figure_placement_review(root)

            before_plan = {
                "verdict": "continue",
                "repair_actions": [{"code": "citation_support_review_missing", "automation": "automatic"}],
            }
            after_plan = {"verdict": "human_needed", "repair_actions": []}
            with patch("paperorchestra.ralph_bridge.write_quality_loop_plan", side_effect=[(root / "before-p.json", before_plan), (root / "after-p.json", after_plan)]):
                result = run_qa_loop_step(root, MockProvider(), max_iterations=5, citation_evidence_mode="heuristic")

            self.assertTrue(result.payload["actions_attempted"])
            history_path = root / ".paper-orchestra" / "qa-loop-history.jsonl"
            history = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines()]
            budgeted = [entry for entry in history if entry.get("consumes_budget")]
            self.assertEqual(len(budgeted), 1)
            self.assertEqual(budgeted[0]["event_type"], "qa_loop_step")
            self.assertEqual(budgeted[0]["execution_path"], str(result.path))
            _, quality_eval = write_quality_eval(root, quality_mode="claim_safe", max_iterations=5)
            self.assertEqual(quality_eval["cross_iteration"]["budget"]["attempts_used"], 1)
            self.assertEqual(quality_eval["cross_iteration"]["budget"]["remaining"], 4)

    def test_qa_loop_step_runs_missing_citation_review_handler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            seed_path = root / "refs.bib"
            seed_path.write_text(
                "@techreport{RFC9001,\n"
                "  title = {Using {TLS} to Secure {QUIC}},\n"
                "  author = {Martin Thomson and Sean Turner},\n"
                "  year = {2021},\n"
                "  url = {https://www.rfc-editor.org/rfc/rfc9001}\n"
                "}\n",
                encoding="utf-8",
            )
            import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\n"
                "QUIC uses TLS~\\cite{RFC9001}.\n"
                "\\bibliographystyle{plain}\n\\bibliography{references}\n\\end{document}\n",
                encoding="utf-8",
            )
            state = load_session(root)
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            record_current_validation_report(root, name="validation.current.json")
            write_figure_placement_review(root)

            before_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_review_missing"]}},
            }
            after_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "tiers": {"tier_2_claim_safety": {"status": "pass", "failing_codes": []}},
            }
            before_plan = {
                "verdict": "continue",
                "repair_actions": [{"code": "citation_support_review_missing", "automation": "automatic"}],
            }
            after_plan = {"verdict": "human_needed", "repair_actions": []}
            with patch(
                "paperorchestra.ralph_bridge.write_quality_eval",
                side_effect=[(root / "before-q.json", before_eval), (root / "after-q.json", after_eval)],
            ):
                with patch(
                    "paperorchestra.ralph_bridge.write_quality_loop_plan",
                    side_effect=[(root / "before-p.json", before_plan), (root / "after-p.json", after_plan)],
                ):
                    result = run_qa_loop_step(root, MockProvider(), citation_evidence_mode="heuristic")

            self.assertTrue(result.path.exists())
            self.assertIn(result.exit_code, {10, 20, 30})
            handlers = [item.get("handler") for item in result.payload.get("actions_attempted", [])]
            self.assertIn("review_citations", handlers)
            citation_review_path = Path(load_session(root).artifacts.paper_full_tex).resolve().parent / "citation_support_review.json"
            self.assertTrue(citation_review_path.exists())

    def test_qa_loop_step_runs_source_obligations_handler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            before_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["source_obligations_missing"]}},
            }
            after_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "tiers": {"tier_2_claim_safety": {"status": "pass", "failing_codes": []}},
            }
            before_plan = {
                "verdict": "continue",
                "repair_actions": [{"code": "source_obligations_missing", "automation": "automatic"}],
            }
            after_plan = {"verdict": "human_needed", "repair_actions": []}
            with patch("paperorchestra.ralph_bridge.write_quality_eval", side_effect=[(root / "before-q.json", before_eval), (root / "after-q.json", after_eval)]):
                with patch("paperorchestra.ralph_bridge.write_quality_loop_plan", side_effect=[(root / "before-p.json", before_plan), (root / "after-p.json", after_plan)]):
                    result = run_qa_loop_step(root, MockProvider(), citation_evidence_mode="heuristic")

            handlers = [item.get("handler") for item in result.payload.get("actions_attempted", [])]
            self.assertIn("build_source_obligations", handlers)
            self.assertTrue(Path(load_session(root).artifacts.source_obligations_json).exists())

    def test_qa_loop_step_runs_tier0_precondition_refresh_handlers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            before_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "tiers": {
                    "tier_0_preconditions": {
                        "status": "fail",
                        "failing_codes": [
                            "narrative_plan_stale",
                            "validation_report_missing",
                            "figure_placement_review_missing",
                        ],
                    }
                },
            }
            after_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "tiers": {"tier_0_preconditions": {"status": "pass", "failing_codes": []}},
            }
            before_plan = {
                "verdict": "continue",
                "repair_actions": [
                    {"code": "narrative_plan_stale", "automation": "automatic"},
                    {"code": "validation_report_missing", "automation": "automatic"},
                    {"code": "figure_placement_review_missing", "automation": "automatic"},
                ],
            }
            after_plan = {"verdict": "human_needed", "repair_actions": []}
            with patch("paperorchestra.ralph_bridge.write_quality_eval", side_effect=[(root / "before-q.json", before_eval), (root / "after-q.json", after_eval)]):
                with patch("paperorchestra.ralph_bridge.write_quality_loop_plan", side_effect=[(root / "before-p.json", before_plan), (root / "after-p.json", after_plan)]):
                    result = run_qa_loop_step(root, MockProvider(), citation_evidence_mode="heuristic")

            attempted = result.payload.get("actions_attempted", [])
            handlers = [item.get("handler") for item in attempted]
            self.assertIn("plan_narrative", handlers)
            self.assertIn("validate_current", handlers)
            self.assertIn("review_figure_placement", handlers)
            planning_actions = [item for item in attempted if item.get("handler") == "plan_narrative"]
            validation_actions = [item for item in attempted if item.get("handler") == "validate_current"]
            figure_actions = [item for item in attempted if item.get("handler") == "review_figure_placement"]
            self.assertTrue(Path(planning_actions[0]["paths"]["narrative_plan"]).exists())
            self.assertTrue(Path(validation_actions[0]["path"]).exists())
            self.assertTrue(Path(figure_actions[0]["path"]).exists())
            state = load_session(root)
            self.assertIsNotNone(state.artifacts.narrative_plan_json)
            self.assertIsNotNone(state.artifacts.latest_validation_json)
            self.assertIsNotNone(state.artifacts.latest_figure_placement_review_json)

    def test_qa_loop_step_runs_new_review_authentication_refresh_handler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            before_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "tiers": {"tier_3_scholarly_quality": {"status": "warn", "failing_codes": ["review_provenance_missing"]}},
            }
            after_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "tiers": {"tier_3_scholarly_quality": {"status": "pass", "failing_codes": []}},
            }
            before_plan = {
                "verdict": "continue",
                "repair_actions": [{"code": "review_provenance_missing", "automation": "automatic"}],
            }
            after_plan = {"verdict": "human_needed", "repair_actions": []}
            with patch("paperorchestra.ralph_bridge.write_quality_eval", side_effect=[(root / "before-q.json", before_eval), (root / "after-q.json", after_eval)]):
                with patch("paperorchestra.ralph_bridge.write_quality_loop_plan", side_effect=[(root / "before-p.json", before_plan), (root / "after-p.json", after_plan)]):
                    with patch("paperorchestra.ralph_bridge.review_current_paper", return_value=root / "review.json"):
                        result = run_qa_loop_step(root, MockProvider(), citation_evidence_mode="heuristic")

            handlers = [item.get("handler") for item in result.payload.get("actions_attempted", [])]
            self.assertIn("review", handlers)

    def test_qa_loop_step_stops_on_unsupported_executable_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quality_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["compile_not_clean"]}},
            }
            plan = {
                "verdict": "continue",
                "repair_actions": [
                    {
                        "code": "unknown_citation_keys",
                        "automation": "automatic",
                        "reason": "No bridge handler exists for this synthetic action.",
                    }
                ],
            }
            with patch("paperorchestra.ralph_bridge.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                with patch("paperorchestra.ralph_bridge.write_quality_loop_plan", return_value=(root / "plan.json", plan)):
                    with patch("paperorchestra.ralph_bridge._citation_summary", return_value={}):
                        result = run_qa_loop_step(root, MockProvider())

            self.assertEqual(result.exit_code, 20)
            self.assertEqual(result.payload["verdict"], "human_needed")
            self.assertEqual(result.payload["reason"], "no_supported_executable_handlers")
            self.assertEqual(result.payload["actions_skipped"][0]["code"], "unknown_citation_keys")

    def test_qa_loop_step_noops_on_terminal_human_needed_even_with_executable_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quality_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "tiers": {"tier_1_structural": {"status": "fail", "failing_codes": ["missing_prompt_trace"]}},
            }
            plan = {
                "verdict": "human_needed",
                "repair_actions": [
                    {"code": "missing_prompt_trace", "automation": "human_needed"},
                    {"code": "citation_support_review_missing", "automation": "automatic"},
                ],
            }
            with patch("paperorchestra.ralph_bridge.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                with patch("paperorchestra.ralph_bridge.write_quality_loop_plan", return_value=(root / "plan.json", plan)):
                    with patch("paperorchestra.ralph_bridge._citation_summary", return_value={}):
                        with patch("paperorchestra.ralph_bridge.write_citation_support_review") as review_citations:
                            result = run_qa_loop_step(root, MockProvider())

            self.assertEqual(result.exit_code, 20)
            self.assertEqual(result.payload["verdict"], "human_needed")
            self.assertTrue(result.payload["terminal_noop"])
            self.assertEqual(result.payload["actions_attempted"], [])
            review_citations.assert_not_called()

    def test_operator_review_packet_requires_terminal_human_needed_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)

            with self.assertRaises(ContractError):
                build_operator_review_packet(root, review_scope="tex_only")

            self._write_terminal_human_needed_plan(root, verdict="continue")
            with self.assertRaises(ContractError):
                build_operator_review_packet(root, review_scope="tex_only")

            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            self.assertTrue(packet_path.exists())
            self.assertEqual(packet["review_scope"], "tex_only")
            self.assertIn("qa_loop_plan", {artifact["role"] for artifact in packet["artifacts"]})

            with self.assertRaises(ContractError):
                build_operator_review_packet(root, require_pdf=True)

    def test_operator_review_packet_rejects_stale_human_needed_execution_without_current_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)

            self._write_terminal_human_needed_plan(root, verdict="continue")
            base_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            execution_path = root / ".paper-orchestra" / "qa-loop-execution.iter-01.json"
            execution_path.write_text(
                json.dumps(
                    {
                        "schema_version": "qa-loop-execution/1",
                        "verdict": "human_needed",
                        "manuscript_sha256_before": base_sha,
                        "candidate_approval": {
                            "status": "human_needed_candidate_ready",
                            "base_manuscript_sha256": base_sha,
                            "reason": "semi_auto candidate requires supervised approval",
                        },
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ContractError):
                build_operator_review_packet(root, review_scope="tex_only")

            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            self.assertTrue(packet_path.exists())
            self.assertIn("qa_loop_execution", {artifact["role"] for artifact in packet["artifacts"]})
            issue = {
                "source_artifact_role": "qa_loop_execution",
                "source_item_key": "candidate_approval",
                "target_section": "Whole manuscript",
                "severity": "major",
                "rationale": "The latest QA-loop execution requires supervised approval.",
                "suggested_action": "Review and apply the candidate only if it preserves claim safety.",
                "authority_class": "author_feedback",
                "owner_category": "author",
            }
            issue["id"] = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role=issue["source_artifact_role"],
                source_item_key=issue["source_item_key"],
                target_section=issue["target_section"],
                rationale=issue["rationale"],
                suggested_action=issue["suggested_action"],
            )
            issue["source"] = "codex_operator"
            issue["not_independent_human_review"] = True
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback/1",
                        "source": "codex_operator",
                        "not_independent_human_review": True,
                        "intent": "approve_existing_candidate",
                        "packet_sha256": packet["packet_sha256"],
                        "manuscript_sha256": packet["manuscript_sha256"],
                        "issues": [issue],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, imported = import_operator_feedback(
                root,
                packet_path=packet_path,
                feedback_path=feedback_path,
            )
            self.assertTrue(imported_path.exists())
            self.assertEqual(imported["packet_sha256"], packet["packet_sha256"])

    def test_operator_review_packet_accepts_hash_bound_candidate_approval_with_continue_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="continue")
            base_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            candidate = artifact_path(root, "paper.citation-repair.candidate.tex")
            candidate.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft with a narrowed claim.\n\\end{document}\n",
                encoding="utf-8",
            )
            candidate_sha = "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest()
            execution_path = root / ".paper-orchestra" / "qa-loop-execution.iter-01.json"
            execution_payload = {
                "schema_version": "qa-loop-execution/1",
                "verdict": "human_needed",
                "candidate_approval": {
                    "status": "human_needed_candidate_ready",
                    "candidate_path": str(candidate),
                    "candidate_sha256": candidate_sha,
                    "base_manuscript_sha256": base_sha,
                    "source_execution_path": str(execution_path),
                    "source_execution_sha256": "pending_until_execution_write",
                    "created_at": "2026-05-06T00:00:00Z",
                    "reason": "Semi-automatic citation repair made progress and needs supervised approval.",
                },
                "candidate_progress": {
                    "forward_progress": True,
                    "before_failing_codes": ["citation_support_manual_check", "citation_support_weak"],
                    "after_failing_codes": ["citation_support_weak"],
                    "resolved_codes": ["citation_support_manual_check"],
                    "new_codes": [],
                },
                "candidate_state": {"verification": {"validate_current": {"ok": True}}},
            }
            execution_payload["candidate_approval"]["source_execution_sha256"] = self._execution_source_sha(execution_payload)
            execution_path.write_text(json.dumps(execution_payload), encoding="utf-8")
            stale_operator_execution = artifact_path(root, "operator_feedback.execution.json")
            stale_operator_execution.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback-execution/1",
                        "verdict": "human_needed",
                        "promotion_status": "rolled_back",
                        "manuscript_sha256_before": "sha256:" + hashlib.sha256(b"stale manuscript").hexdigest(),
                    }
                ),
                encoding="utf-8",
            )

            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            roles = {artifact["role"] for artifact in packet["artifacts"]}
            self.assertIn("qa_loop_plan", roles)
            self.assertIn("qa_loop_execution", roles)
            self.assertNotIn("operator_feedback_execution", roles)
            qa_plan_record = next(artifact for artifact in packet["artifacts"] if artifact["role"] == "qa_loop_plan")
            self.assertEqual(json.loads(Path(qa_plan_record["path"]).read_text(encoding="utf-8"))["verdict"], "continue")

            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="qa_loop_execution",
                source_item_key="candidate_approval",
                target_section="Whole manuscript",
                rationale="Approve the hash-bound candidate because it resolves a manual-check citation issue.",
                suggested_action="Promote the candidate only after preserving the remaining weak citation warning.",
            )
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback/1",
                        "source": "codex_operator",
                        "not_independent_human_review": True,
                        "intent": "approve_existing_candidate",
                        "packet_sha256": packet["packet_sha256"],
                        "manuscript_sha256": packet["manuscript_sha256"],
                        "issues": [
                            {
                                "id": issue_id,
                                "source_artifact_role": "qa_loop_execution",
                                "source_item_key": "candidate_approval",
                                "target_section": "Whole manuscript",
                                "severity": "major",
                                "rationale": "Approve the hash-bound candidate because it resolves a manual-check citation issue.",
                                "suggested_action": "Promote the candidate only after preserving the remaining weak citation warning.",
                                "authority_class": "author_feedback",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, imported = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            self.assertTrue(imported_path.exists())
            self.assertEqual(imported["intent"], "approve_existing_candidate")

            artifact_path(root, "qa-loop.plan.json").write_text(
                json.dumps(
                    {
                        "schema_version": "qa-loop-plan/2",
                        "session_id": state.session_id,
                        "verdict": "failed",
                        "quality_eval_summary": {"manuscript_hash": base_sha},
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ContractError, "operator review stop requires current qa-loop.plan.json verdict=continue or human_needed"):
                import_operator_feedback(
                    root,
                    packet_path=packet_path,
                    feedback_path=feedback_path,
                    output_path=root / "stale-candidate-context.json",
                )

    def test_operator_review_packet_accepts_hash_bound_rejected_candidate_stop_with_continue_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="continue")
            base_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            execution_path = root / ".paper-orchestra" / "qa-loop-execution.iter-01.json"
            execution_path.write_text(
                json.dumps(
                    {
                        "schema_version": "qa-loop-execution/1",
                        "verdict": "human_needed",
                        "actions_attempted": [
                            {"code": "citation_support_critic_failed", "handler": "repair_citation_claims"}
                        ],
                        "candidate_handoff": {
                            "status": "human_needed_candidate_rejected_by_citation_support",
                            "reason": "candidate still has non-reviewable citation-support failures",
                        },
                        "candidate_rollback": {
                            "reason": "citation_support_approval_failed",
                            "failing_codes": ["citation_support_weak"],
                        },
                        "progress": {
                            "before_manuscript_hash": base_sha,
                            "after_manuscript_hash": base_sha,
                            "same_manuscript_as_previous": True,
                            "forward_progress": False,
                            "before_failing_codes": ["citation_support_weak"],
                            "after_failing_codes": ["citation_support_weak"],
                        },
                        "restored_current_state": {
                            "qa_loop_plan_verdict": "continue",
                            "progress": {
                                "before_manuscript_hash": base_sha,
                                "after_manuscript_hash": base_sha,
                                "forward_progress": False,
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")

            roles = {artifact["role"] for artifact in packet["artifacts"]}
            self.assertIn("qa_loop_plan", roles)
            self.assertIn("qa_loop_execution", roles)
            qa_plan_record = next(artifact for artifact in packet["artifacts"] if artifact["role"] == "qa_loop_plan")
            self.assertEqual(json.loads(Path(qa_plan_record["path"]).read_text(encoding="utf-8"))["verdict"], "continue")
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="qa_loop_execution",
                source_item_key="candidate_handoff",
                target_section="Whole manuscript",
                rationale="The latest QA-loop execution exhausted the bounded candidate repair lane.",
                suggested_action="Generate a new operator candidate grounded in the packet artifacts.",
            )
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback/1",
                        "source": "codex_operator",
                        "not_independent_human_review": True,
                        "intent": "generate_new_operator_candidate",
                        "packet_sha256": packet["packet_sha256"],
                        "manuscript_sha256": packet["manuscript_sha256"],
                        "issues": [
                            {
                                "id": issue_id,
                                "source_artifact_role": "qa_loop_execution",
                                "source_item_key": "candidate_handoff",
                                "target_section": "Whole manuscript",
                                "severity": "major",
                                "rationale": "The latest QA-loop execution exhausted the bounded candidate repair lane.",
                                "suggested_action": "Generate a new operator candidate grounded in the packet artifacts.",
                                "authority_class": "author_feedback",
                                "owner_category": "author",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            imported_path, imported = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            self.assertTrue(imported_path.exists())
            self.assertEqual(imported["intent"], "generate_new_operator_candidate")

    def test_operator_review_packet_rejects_stale_rejected_candidate_stop_with_continue_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="continue")
            stale_sha = "sha256:" + hashlib.sha256(b"stale manuscript").hexdigest()
            execution_path = root / ".paper-orchestra" / "qa-loop-execution.iter-01.json"
            execution_path.write_text(
                json.dumps(
                    {
                        "schema_version": "qa-loop-execution/1",
                        "verdict": "human_needed",
                        "candidate_handoff": {"status": "human_needed_candidate_rejected_by_citation_support"},
                        "progress": {
                            "before_manuscript_hash": stale_sha,
                            "after_manuscript_hash": stale_sha,
                            "forward_progress": False,
                        },
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ContractError):
                build_operator_review_packet(root, review_scope="tex_only")

    def test_operator_review_packet_rejects_operator_execution_only_reopen_with_continue_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="continue")
            base_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            operator_execution_path = artifact_path(root, "operator_feedback.execution.json")
            operator_execution_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback-execution/1",
                        "verdict": "human_needed",
                        "manuscript_sha256_before": base_sha,
                        "promotion_status": "rolled_back",
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ContractError):
                build_operator_review_packet(root, review_scope="tex_only")

    def test_current_human_needed_plan_ignores_stale_supplemental_executions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            old_paper = artifact_path(root, "old-paper.full.tex")
            old_paper.write_text("\\documentclass{article}\n\\begin{document}\nOld.\n\\end{document}\n", encoding="utf-8")
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\nCurrent.\n\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            old_sha = "sha256:" + hashlib.sha256(old_paper.read_bytes()).hexdigest()
            current_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            self.assertNotEqual(old_sha, current_sha)
            qa_execution_path = root / ".paper-orchestra" / "qa-loop-execution.iter-01.json"
            qa_execution_path.write_text(
                json.dumps(
                    {
                        "schema_version": "qa-loop-execution/1",
                        "verdict": "human_needed",
                        "manuscript_sha256_before": old_sha,
                    }
                ),
                encoding="utf-8",
            )
            operator_execution_path = artifact_path(root, "operator_feedback.execution.json")
            operator_execution_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback-execution/1",
                        "verdict": "human_needed",
                        "manuscript_sha256_before": old_sha,
                        "promotion_status": "rolled_back",
                    }
                ),
                encoding="utf-8",
            )

            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")

            self.assertTrue(packet_path.exists())
            roles = {artifact["role"] for artifact in packet["artifacts"]}
            self.assertIn("qa_loop_plan", roles)
            self.assertNotIn("qa_loop_execution", roles)
            self.assertNotIn("operator_feedback_execution", roles)
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="qa_loop_plan",
                source_item_key="verdict",
                target_section="Whole manuscript",
                rationale="The current plan is human-needed even though old execution artifacts exist.",
                suggested_action="Continue supervised feedback from the current plan only.",
            )
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback/1",
                        "source": "codex_operator",
                        "not_independent_human_review": True,
                        "intent": "generate_new_operator_candidate",
                        "packet_sha256": packet["packet_sha256"],
                        "manuscript_sha256": packet["manuscript_sha256"],
                        "issues": [
                            {
                                "id": issue_id,
                                "source_artifact_role": "qa_loop_plan",
                                "source_item_key": "verdict",
                                "target_section": "Whole manuscript",
                                "severity": "major",
                                "rationale": "The current plan is human-needed even though old execution artifacts exist.",
                                "suggested_action": "Continue supervised feedback from the current plan only.",
                                "authority_class": "author_feedback",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, imported = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            self.assertTrue(imported_path.exists())
            self.assertEqual(imported["intent"], "generate_new_operator_candidate")

    def test_operator_review_packet_omits_stale_review_artifacts_for_current_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            old_sha = "sha256:" + hashlib.sha256(b"old manuscript").hexdigest()
            artifact_path(root, "section_review.json").write_text(
                json.dumps({"schema_version": "section-review/1", "manuscript_sha256": old_sha, "sections": []}),
                encoding="utf-8",
            )
            artifact_path(root, "citation_support_review.json").write_text(
                json.dumps({"schema_version": "citation-support-review/1", "manuscript_sha256": old_sha, "items": []}),
                encoding="utf-8",
            )
            artifact_path(root, "quality-eval.json").write_text(
                json.dumps({"schema_version": "quality-eval/1", "manuscript_hash": old_sha, "tiers": {}}),
                encoding="utf-8",
            )

            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")

            self.assertTrue(packet_path.exists())
            roles = {artifact["role"] for artifact in packet["artifacts"]}
            self.assertIn("qa_loop_plan", roles)
            self.assertNotIn("section_review", roles)
            self.assertNotIn("citation_support_review", roles)
            self.assertNotIn("quality_eval", roles)

    def test_operator_review_packet_uses_current_fallback_when_state_pointer_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n"
                "\\begin{document}\n"
                "\\section{Intro}\n"
                "Draft.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            current_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            stale_section = artifact_path(root, "stale-section-review.json")
            stale_section.write_text(
                json.dumps(
                    {
                        "schema_version": "section-review/1",
                        "manuscript_sha256": "sha256:" + hashlib.sha256(b"old manuscript").hexdigest(),
                        "sections": [],
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.latest_section_review_json = str(stale_section)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            current_section = artifact_path(root, "section_review.json")
            current_section.write_text(
                json.dumps(
                    {
                        "schema_version": "section-review/1",
                        "manuscript_sha256": current_sha,
                        "sections": [{"title": "Intro", "score": 55}],
                    }
                ),
                encoding="utf-8",
            )

            _packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")

            by_role = {artifact["role"]: artifact for artifact in packet["artifacts"]}
            self.assertIn("section_review", by_role)
            self.assertEqual(Path(by_role["section_review"]["original_path"]).resolve(), current_section.resolve())

    def test_operator_review_payload_includes_concrete_claim_safety_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            artifact_path(root, "citation_support_review.json").write_text(
                json.dumps(
                    {
                        "schema_version": "citation-support-review/1",
                        "items": [
                            {
                                "id": "cite-001",
                                "support_status": "supported",
                                "sentence": "Supported sentence.",
                                "citation_keys": ["GoodKey"],
                            },
                            {
                                "id": "cite-002",
                                "support_status": "unsupported",
                                "claim_type": "numeric",
                                "risk": "high",
                                "sentence": "Exact bound unsupported by the provided citation.",
                                "citation_keys": ["WeakKey"],
                                "suggested_fix": "Remove the exact bound or cite the exact lemma.",
                                "model_reasoning": "The citation does not establish the numeric denominator.",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            artifact_path(root, "quality-eval.json").write_text(
                json.dumps(
                    {
                        "schema_version": "quality-eval/1",
                        "tiers": {
                            "tier_2_claim_safety": {
                                "status": "fail",
                                "checks": {
                                    "high_risk_claim_sweep": {
                                        "status": "fail",
                                        "items": [
                                            {
                                                "line": 12,
                                                "sentence": "High-risk uncited security claim.",
                                                "reason": "high-risk claim lacks citation",
                                            }
                                        ],
                                    }
                                },
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue = {
                "source_artifact_role": "citation_support_review",
                "source_item_key": "non_supported_items",
                "target_section": "Whole manuscript",
                "severity": "critical",
                "rationale": "Citation support failed.",
                "suggested_action": "Fix the concrete unsupported claims.",
                "authority_class": "author_feedback",
            }
            issue["id"] = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role=issue["source_artifact_role"],
                source_item_key=issue["source_item_key"],
                target_section=issue["target_section"],
                rationale=issue["rationale"],
                suggested_action=issue["suggested_action"],
            )
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback/1",
                        "source": "codex_operator",
                        "not_independent_human_review": True,
                        "intent": "generate_new_operator_candidate",
                        "packet_sha256": packet["packet_sha256"],
                        "manuscript_sha256": packet["manuscript_sha256"],
                        "issues": [issue],
                    }
                ),
                encoding="utf-8",
            )
            _, imported = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)

            review_payload = _operator_review_payload(imported)

            context = review_payload["issue_context"]
            self.assertEqual(context["problematic_citation_items"][0]["id"], "cite-002")
            self.assertIn("Exact bound unsupported", context["problematic_citation_items"][0]["sentence"])
            self.assertEqual(context["high_risk_uncited_claims"][0]["line"], 12)
            self.assertIn("High-risk uncited security claim", context["high_risk_uncited_claims"][0]["sentence"])
            self.assertIn("primary repair targets", context["writer_instruction"])

    def test_operator_feedback_cli_trio_smoke_runs_explicit_supervised_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_cwd = Path.cwd()
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n"
                "\\section{Intro}\nDraft.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            try:
                os.chdir(root)
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(cli_main(["plan-narrative", "--provider", "mock"]), 0)
                self._write_terminal_human_needed_plan(root)
                packet_stdout = io.StringIO()
                with contextlib.redirect_stdout(packet_stdout):
                    self.assertEqual(cli_main(["build-operator-review-packet", "--review-scope", "tex_only"]), 0)
                packet_payload = json.loads(packet_stdout.getvalue())
                packet = packet_payload["packet"]
                packet_path = packet_payload["path"]
                issue_id = derive_operator_issue_id(
                    packet["packet_sha256"],
                    source_artifact_role="paper_full_tex",
                    source_item_key="Intro:p1",
                    target_section="Intro",
                    rationale="The opening is too thin to be worth external review.",
                    suggested_action="Add a concrete contribution paragraph without inventing new evidence.",
                )
                feedback_path = root / "operator-feedback.json"
                feedback_path.write_text(
                    json.dumps(
                        {
                            "schema_version": "operator-feedback/1",
                            "source": "codex_operator",
                            "not_independent_human_review": True,
                            "intent": "generate_new_operator_candidate",
                            "packet_sha256": packet["packet_sha256"],
                            "manuscript_sha256": packet["manuscript_sha256"],
                            "issues": [
                                {
                                    "id": issue_id,
                                    "source_artifact_role": "paper_full_tex",
                                    "source_item_key": "Intro:p1",
                                    "target_section": "Intro",
                                    "severity": "major",
                                    "rationale": "The opening is too thin to be worth external review.",
                                    "suggested_action": "Add a concrete contribution paragraph without inventing new evidence.",
                                    "authority_class": "prose_rewrite",
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                import_stdout = io.StringIO()
                with contextlib.redirect_stdout(import_stdout):
                    self.assertEqual(
                        cli_main(["import-operator-feedback", "--packet", packet_path, "--feedback", str(feedback_path)]),
                        0,
                    )
                imported_payload = json.loads(import_stdout.getvalue())
                imported_path = imported_payload["path"]
                self.assertEqual(imported_payload["imported_feedback"]["translated_actions"][0]["source_issue_id"], issue_id)

                apply_stdout = io.StringIO()
                with contextlib.redirect_stdout(apply_stdout):
                    apply_code = cli_main(
                        [
                            "apply-operator-feedback",
                            "--imported-feedback",
                            imported_path,
                            "--provider",
                            "mock",
                            "--quality-mode",
                            "draft",
                            "--citation-evidence-mode",
                            "heuristic",
                        ]
                    )
                self.assertEqual(apply_code, 0)
                execution_payload = json.loads(apply_stdout.getvalue())["execution"]
                self.assertEqual(execution_payload["event_type"], "operator_feedback_cycle")
                self.assertTrue(execution_payload["not_independent_human_review"])
                self.assertIn(execution_payload["verdict"], {"human_needed", "continue", "ready_for_human_finalization", "failed"})
                self.assertTrue(Path(execution_payload["incorporation_report"]).exists())
            finally:
                os.chdir(old_cwd)

    def test_import_operator_feedback_requires_machine_readable_intent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(packet["packet_sha256"], source_artifact_role="paper_full_tex", source_item_key="Intro:p1", target_section="Intro", rationale="Needs direction.", suggested_action="Add direction.")
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{"id": issue_id, "source_artifact_role": "paper_full_tex", "source_item_key": "Intro:p1", "target_section": "Intro", "severity": "major", "rationale": "Needs direction.", "suggested_action": "Add direction.", "authority_class": "prose_rewrite"}]}), encoding="utf-8")
            with self.assertRaises(ContractError):
                import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)

    def test_operator_feedback_packet_import_is_hash_bound_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)

            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="paper_full_tex",
                source_item_key="Intro:p1",
                target_section="Intro",
                rationale="The opening does not state the research contribution.",
                suggested_action="Rewrite the introduction around the concrete contribution and evidence boundary.",
            )
            feedback = {
                "schema_version": "operator-feedback/1",
                "source": "codex_operator",
                "not_independent_human_review": True,
                "intent": "generate_new_operator_candidate",
                "packet_sha256": packet["packet_sha256"],
                "manuscript_sha256": packet["manuscript_sha256"],
                "issues": [
                    {
                        "id": issue_id,
                        "source_artifact_role": "paper_full_tex",
                        "source_item_key": "Intro:p1",
                        "target_section": "Intro",
                        "severity": "major",
                        "rationale": "The opening does not state the research contribution.",
                        "suggested_action": "Rewrite the introduction around the concrete contribution and evidence boundary.",
                        "authority_class": "prose_rewrite",
                    }
                ],
            }
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps(feedback), encoding="utf-8")

            imported_path, imported = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            self.assertEqual(imported["issues"][0]["id"], issue_id)
            self.assertEqual(imported["translated_actions"][0]["source_issue_id"], issue_id)
            self.assertTrue(imported["not_independent_human_review"])

            repeat_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="paper_full_tex",
                source_item_key="Intro:p1",
                target_section="Intro",
                rationale="The opening does not state the research contribution.",
                suggested_action="Rewrite the introduction around the concrete contribution and evidence boundary.",
            )
            self.assertEqual(repeat_id, issue_id)

            paper.write_text(paper.read_text(encoding="utf-8") + "% changed\n", encoding="utf-8")
            with self.assertRaises(ContractError):
                import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path, output_path=root / "stale-current.json")

            frozen_paper = Path(next(artifact["path"] for artifact in packet["artifacts"] if artifact["role"] == "paper_full_tex"))
            frozen_paper.write_text(frozen_paper.read_text(encoding="utf-8") + "% tampered\n", encoding="utf-8")
            with self.assertRaises(ContractError):
                import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path, output_path=root / "stale.json")
            self.assertTrue(imported_path.exists())

    def test_operator_feedback_cycle_is_supervised_and_does_not_consume_automatic_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            review = review_path(root, "review.latest.json")
            review.write_text(
                json.dumps(
                    {
                        "overall_score": 50,
                        "axis_scores": {},
                        "summary": {"weaknesses": ["thin"], "top_improvements": ["improve"]},
                        "questions": [],
                        "penalties": [],
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.latest_review_json = str(review)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)

            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="paper_full_tex",
                source_item_key="Intro:p1",
                target_section="Intro",
                rationale="The introduction is too thin.",
                suggested_action="Add a sharper contribution paragraph.",
            )
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback/1",
                        "source": "codex_operator",
                        "not_independent_human_review": True,
                        "intent": "generate_new_operator_candidate",
                        "packet_sha256": packet["packet_sha256"],
                        "manuscript_sha256": packet["manuscript_sha256"],
                        "issues": [
                            {
                                "id": issue_id,
                                "source_artifact_role": "paper_full_tex",
                                "source_item_key": "Intro:p1",
                                "target_section": "Intro",
                                "severity": "major",
                                "rationale": "The introduction is too thin.",
                                "suggested_action": "Add a sharper contribution paragraph.",
                                "authority_class": "prose_rewrite",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)

            def fake_refine(cwd, provider, **kwargs):
                target = Path(load_session(cwd).artifacts.paper_full_tex)
                target.write_text(target.read_text(encoding="utf-8") + "\nA sharper contribution paragraph.\n", encoding="utf-8")
                return [{"iteration": 1, "accepted": True, "reason": "test"}]

            quality_eval = {"session_id": state.session_id, "mode": "claim_safe", "manuscript_hash": "sha256:after", "tiers": {}}
            with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=fake_refine):
                with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                    with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                        with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                            with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                                with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "human_needed"})):
                                    execution_path, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)

            self.assertTrue(execution_path.exists())
            self.assertEqual(execution["event_type"], "operator_feedback_cycle")
            self.assertEqual(execution["supervised_iteration_index"], 1)
            self.assertTrue(execution["not_independent_human_review"])
            incorporation = json.loads(Path(execution["incorporation_report"]).read_text(encoding="utf-8"))
            self.assertIn(incorporation["issues"][0]["status"], {"reflected", "partially_reflected"})

            history_path = root / ".paper-orchestra" / "qa-loop-history.jsonl"
            history = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(history[-1]["event_type"], "operator_feedback_cycle")
            self.assertFalse(history[-1]["consumes_budget"])
            self.assertEqual(history[-1]["supervised_max_iterations"], 1)


    def test_operator_feedback_explicit_rejection_is_human_needed_not_execution_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="paper_full_tex",
                source_item_key="Intro:p1",
                target_section="Intro",
                rationale="Reject the current candidate because it should not be promoted.",
                suggested_action="Keep the current manuscript and request human follow-up.",
            )
            feedback_path = root / "operator-feedback-reject.json"
            feedback_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback/1",
                        "source": "codex_operator",
                        "not_independent_human_review": True,
                        "intent": "reject_candidate_with_reason",
                        "packet_sha256": packet["packet_sha256"],
                        "manuscript_sha256": packet["manuscript_sha256"],
                        "issues": [
                            {
                                "id": issue_id,
                                "source_artifact_role": "paper_full_tex",
                                "source_item_key": "Intro:p1",
                                "target_section": "Intro",
                                "severity": "major",
                                "rationale": "Reject the current candidate because it should not be promoted.",
                                "suggested_action": "Keep the current manuscript and request human follow-up.",
                                "authority_class": "author_feedback",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            quality_eval = {"session_id": state.session_id, "mode": "claim_safe", "manuscript_hash": "sha256:same", "tiers": {}}
            with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=AssertionError("reject must not rewrite")):
                with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                    with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                        with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                            with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                                with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "human_needed"})):
                                    execution_path, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)

            self.assertTrue(execution_path.exists())
            self.assertEqual(execution["verdict"], "human_needed")
            self.assertEqual(execution["promotion_status"], "rolled_back")
            self.assertEqual(execution["promotion_reason"], "operator_rejected_candidate")
            self.assertEqual(execution["candidate_rollback"]["reason"], "operator_rejected_candidate")
            self.assertEqual(execution["supervised_iteration_index"], 0)
            self.assertEqual(execution["attempts"], [])

    def test_operator_feedback_catastrophic_regression_threshold_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
            review = review_path(root, "review.latest.json")
            review.write_text(json.dumps({"overall_score": 70, "axis_scores": {"organization_and_writing": {"score": 70}}, "summary": {"weaknesses": [], "top_improvements": []}, "questions": [], "penalties": []}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.latest_review_json = str(review)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(packet["packet_sha256"], source_artifact_role="paper_full_tex", source_item_key="Intro:p1", target_section="Intro", rationale="The contribution paragraph is missing.", suggested_action="Add contribution language.")
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "intent": "generate_new_operator_candidate", "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{"id": issue_id, "source_artifact_role": "paper_full_tex", "source_item_key": "Intro:p1", "target_section": "Intro", "severity": "major", "rationale": "The contribution paragraph is missing.", "suggested_action": "Add contribution language.", "authority_class": "prose_rewrite"}]}), encoding="utf-8")
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)

            def run_with_scores(overall_after: float, axis_after: float):
                paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
                candidate = artifact_path(root, f"candidate-{overall_after}-{axis_after}.tex")
                candidate.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft. Contribution language.\n\\end{document}\n", encoding="utf-8")
                def fake_refine(cwd, provider, **kwargs):
                    return [{"iteration": 1, "candidate_only": True, "candidate_path": str(candidate), "candidate_sha256": "x", "score_before": 70.0, "score_after": overall_after, "axis_scores_before": {"organization_and_writing": 70.0}, "axis_scores_after": {"organization_and_writing": axis_after}}]
                quality_eval = {"session_id": state.session_id, "mode": "claim_safe", "tiers": {"tier_0_preconditions": {"status": "pass"}, "tier_1_structural": {"status": "pass"}, "tier_2_claim_safety": {"status": "pass"}}}
                with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=fake_refine):
                    with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                        with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                            with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                                with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                                    with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "continue"})):
                                        return apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)
            _, at_boundary = run_with_scores(62.0, 55.0)
            self.assertEqual(at_boundary["promotion_status"], "promoted")
            _, beyond = run_with_scores(61.9, 55.0)
            self.assertEqual(beyond["promotion_status"], "rolled_back")
            self.assertIn("reviewer_catastrophic_regression", beyond["attempts"][-1]["gate_reasons"])

    def test_operator_feedback_preserves_each_generated_candidate_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
            review = review_path(root, "review.latest.json")
            review.write_text(json.dumps({"overall_score": 70, "axis_scores": {}, "summary": {"weaknesses": [], "top_improvements": []}, "questions": [], "penalties": []}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.latest_review_json = str(review)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            artifact_path(root, "quality-eval.json").write_text(json.dumps({"schema_version": "quality-eval/1", "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["existing_claim_issue"]}}}), encoding="utf-8")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(packet["packet_sha256"], source_artifact_role="paper_full_tex", source_item_key="Intro:p1", target_section="Intro", rationale="The contribution paragraph is missing.", suggested_action="Add contribution language.")
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "intent": "generate_new_operator_candidate", "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{"id": issue_id, "source_artifact_role": "paper_full_tex", "source_item_key": "Intro:p1", "target_section": "Intro", "severity": "major", "rationale": "The contribution paragraph is missing.", "suggested_action": "Add contribution language.", "authority_class": "prose_rewrite"}]}), encoding="utf-8")
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            shared_candidate = artifact_path(root, "shared-candidate.tex")
            call_count = {"value": 0}

            def fake_refine(cwd, provider, **kwargs):
                call_count["value"] += 1
                shared_candidate.write_text(
                    f"\\documentclass{{article}}\n\\begin{{document}}\n\\section{{Intro}}\nDraft. Contribution language attempt {call_count['value']}.\\end{{document}}\n",
                    encoding="utf-8",
                )
                return [{"iteration": 1, "candidate_path": str(shared_candidate), "candidate_sha256": "sha256:" + hashlib.sha256(shared_candidate.read_bytes()).hexdigest(), "score_before": 70, "score_after": 70, "axis_scores_before": {}, "axis_scores_after": {}}]

            quality_eval = {"session_id": state.session_id, "mode": "claim_safe", "tiers": {"tier_0_preconditions": {"status": "pass"}, "tier_1_structural": {"status": "pass"}, "tier_2_claim_safety": {"status": "fail", "failing_codes": ["existing_claim_issue"]}}}
            with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=fake_refine):
                with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                    with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                        with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                            with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                                with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "continue"})):
                                    _, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path, max_supervised_iterations=2)

            self.assertEqual(execution["promotion_status"], "rolled_back")
            candidate_paths = [Path(attempt["candidate_path"]) for attempt in execution["attempts"]]
            self.assertEqual(len(candidate_paths), 2)
            self.assertNotEqual(candidate_paths[0], candidate_paths[1])
            self.assertIn("attempt 1", candidate_paths[0].read_text(encoding="utf-8"))
            self.assertIn("attempt 2", candidate_paths[1].read_text(encoding="utf-8"))

    def test_operator_feedback_promotes_operator_execution_candidate_with_human_reviewable_new_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
            review = review_path(root, "review.latest.json")
            review.write_text(json.dumps({"overall_score": 70, "axis_scores": {}, "summary": {"weaknesses": [], "top_improvements": []}, "questions": [], "penalties": []}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.latest_review_json = str(review)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            artifact_path(root, "quality-eval.json").write_text(json.dumps({"schema_version": "quality-eval/1", "manuscript_hash": "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest(), "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_unsupported"]}}}), encoding="utf-8")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(packet["packet_sha256"], source_artifact_role="paper_full_tex", source_item_key="Intro:p1", target_section="Intro", rationale="Unsupported claim remains.", suggested_action="Soften unsupported claim.")
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "intent": "generate_new_operator_candidate", "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{"id": issue_id, "source_artifact_role": "paper_full_tex", "source_item_key": "Intro:p1", "target_section": "Intro", "severity": "major", "rationale": "Unsupported claim remains.", "suggested_action": "Soften unsupported claim.", "authority_class": "prose_rewrite"}]}), encoding="utf-8")
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            candidate = artifact_path(root, "candidate-manual-check.tex")
            candidate.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft. Softened claim needing manual check.\n\\end{document}\n", encoding="utf-8")

            def fake_refine(cwd, provider, **kwargs):
                return [{"iteration": 1, "candidate_path": str(candidate), "candidate_sha256": "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest(), "score_before": 70, "score_after": 70, "axis_scores_before": {}, "axis_scores_after": {}}]

            manual_check_eval = {"session_id": state.session_id, "mode": "claim_safe", "tiers": {"tier_0_preconditions": {"status": "pass"}, "tier_1_structural": {"status": "pass"}, "tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_manual_check"]}}}
            with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=fake_refine):
                with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                    with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                        with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                            with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", manual_check_eval)):
                                with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "human_needed"})):
                                    _, first_execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)
            self.assertEqual(first_execution["promotion_status"], "rolled_back")
            self.assertEqual(first_execution["candidate_approval"]["status"], "human_needed_candidate_ready")
            self.assertEqual(first_execution["candidate_progress"]["new_codes"], ["citation_support_manual_check"])

            packet_path2, packet2 = build_operator_review_packet(root, review_scope="tex_only")
            roles = {artifact["role"] for artifact in packet2["artifacts"]}
            self.assertIn("operator_feedback_execution", roles)
            approve_issue_id = derive_operator_issue_id(packet2["packet_sha256"], source_artifact_role="operator_feedback_execution", source_item_key="candidate_approval", target_section="Whole manuscript", rationale="Manual-check candidate is approved by the operator.", suggested_action="Promote the human-reviewed candidate.")
            approve_feedback = root / "operator-feedback-approve.json"
            approve_feedback.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "intent": "approve_existing_candidate", "packet_sha256": packet2["packet_sha256"], "manuscript_sha256": packet2["manuscript_sha256"], "issues": [{"id": approve_issue_id, "source_artifact_role": "operator_feedback_execution", "source_item_key": "candidate_approval", "target_section": "Whole manuscript", "severity": "major", "rationale": "Manual-check candidate is approved by the operator.", "suggested_action": "Promote the human-reviewed candidate.", "authority_class": "author_feedback"}]}), encoding="utf-8")
            approve_imported, _ = import_operator_feedback(root, packet_path=packet_path2, feedback_path=approve_feedback, output_path=root / "operator-feedback-approve.imported.json")
            with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                    with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                        with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", manual_check_eval)):
                            with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "human_needed"})):
                                _, approved = apply_operator_feedback(root, MockProvider(), imported_feedback_path=approve_imported)
            self.assertEqual(approved["promotion_status"], "promoted")
            self.assertIn("Softened claim needing manual check", paper.read_text(encoding="utf-8"))

    def test_operator_review_packet_freezes_mutable_artifact_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\nDraft.\n\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            mutable_plan = artifact_path(root, "qa-loop.plan.json")
            original_plan_text = mutable_plan.read_text(encoding="utf-8")

            packet_path, packet = build_operator_review_packet(
                root,
                output_path=root / "operator-feedback" / "operator-review-packet.cycle-1.json",
                review_scope="tex_only",
            )

            packet_snapshot_dir = packet_path.with_suffix(".artifacts").resolve()
            qa_plan_record = next(artifact for artifact in packet["artifacts"] if artifact["role"] == "qa_loop_plan")
            frozen_plan = Path(qa_plan_record["path"]).resolve()
            self.assertEqual(packet_snapshot_dir, frozen_plan.parent)
            self.assertEqual(qa_plan_record["original_path"], str(mutable_plan.resolve()))
            self.assertEqual(frozen_plan.read_text(encoding="utf-8"), original_plan_text)

            mutable_plan.write_text(json.dumps({"verdict": "failed"}), encoding="utf-8")
            self.assertEqual(frozen_plan.read_text(encoding="utf-8"), original_plan_text)

            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="qa_loop_plan",
                source_item_key="verdict",
                target_section="Whole manuscript",
                rationale="The frozen plan remains human-needed.",
                suggested_action="Continue supervised feedback.",
            )
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback/1",
                        "source": "codex_operator",
                        "not_independent_human_review": True,
                        "intent": "generate_new_operator_candidate",
                        "packet_sha256": packet["packet_sha256"],
                        "manuscript_sha256": packet["manuscript_sha256"],
                        "issues": [
                            {
                                "id": issue_id,
                                "source_artifact_role": "qa_loop_plan",
                                "source_item_key": "verdict",
                                "target_section": "Whole manuscript",
                                "severity": "major",
                                "rationale": "The frozen plan remains human-needed.",
                                "suggested_action": "Continue supervised feedback.",
                                "authority_class": "author_feedback",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            mutable_plan.write_text(original_plan_text, encoding="utf-8")
            imported_path, imported = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            self.assertTrue(imported_path.exists())
            self.assertEqual(imported["packet_sha256"], packet["packet_sha256"])

    def test_build_operator_review_packet_includes_operator_execution_after_current_human_needed_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            base_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            operator_execution_path = artifact_path(root, "operator_feedback.execution.json")
            operator_execution_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback-execution/1",
                        "verdict": "human_needed",
                        "manuscript_sha256_before": base_sha,
                        "promotion_status": "rolled_back",
                        "candidate_approval": {
                            "status": "human_needed_candidate_ready",
                            "base_manuscript_sha256": base_sha,
                        },
                        "attempts": [],
                    }
                ),
                encoding="utf-8",
            )

            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")

            roles = {artifact["role"] for artifact in packet["artifacts"]}
            self.assertIn("operator_feedback_execution", roles)
            self.assertIn("qa_loop_plan", roles)
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="operator_feedback_execution",
                source_item_key="verdict",
                target_section="Whole manuscript",
                rationale="Operator feedback remains at a human-needed gate.",
                suggested_action="Continue supervised operator review.",
            )
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback/1",
                        "source": "codex_operator",
                        "not_independent_human_review": True,
                        "intent": "generate_new_operator_candidate",
                        "packet_sha256": packet["packet_sha256"],
                        "manuscript_sha256": packet["manuscript_sha256"],
                        "issues": [
                            {
                                "id": issue_id,
                                "source_artifact_role": "operator_feedback_execution",
                                "source_item_key": "verdict",
                                "target_section": "Whole manuscript",
                                "severity": "major",
                                "rationale": "Operator feedback remains at a human-needed gate.",
                                "suggested_action": "Continue supervised operator review.",
                                "authority_class": "author_feedback",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, imported = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            self.assertTrue(imported_path.exists())
            self.assertEqual(imported["intent"], "generate_new_operator_candidate")

    def test_operator_feedback_approval_uses_issue_source_when_candidate_sources_compete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nBase draft.\n\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            artifact_path(root, "quality-eval.json").write_text(
                json.dumps(
                    {
                        "schema_version": "quality-eval/1",
                        "manuscript_hash": "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest(),
                        "tiers": {
                            "tier_2_claim_safety": {
                                "status": "fail",
                                "failing_codes": ["citation_support_unsupported"],
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            base_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            wrong_candidate = artifact_path(root, "wrong-qa-candidate.tex")
            wrong_candidate.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nWrong QA candidate.\n\\end{document}\n", encoding="utf-8")
            right_candidate = artifact_path(root, "right-operator-candidate.tex")
            right_candidate.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nRight operator candidate.\n\\end{document}\n", encoding="utf-8")
            qa_execution_path = root / ".paper-orchestra" / "qa-loop-execution.iter-01.json"
            qa_execution_payload = {
                "schema_version": "qa-loop-execution/1",
                "verdict": "human_needed",
                "candidate_approval": {
                    "status": "human_needed_candidate_ready",
                    "candidate_path": str(wrong_candidate),
                    "candidate_sha256": "sha256:" + hashlib.sha256(wrong_candidate.read_bytes()).hexdigest(),
                    "base_manuscript_sha256": base_sha,
                    "source_execution_path": str(qa_execution_path),
                    "source_execution_sha256": "pending_until_execution_write",
                    "created_at": "2026-05-03T00:00:00Z",
                },
                "candidate_progress": {
                    "forward_progress": True,
                    "before_failing_codes": ["citation_support_unsupported"],
                    "after_failing_codes": [],
                },
                "candidate_state": {"verification": {"validate_current": {"ok": True}}},
            }
            qa_execution_payload["candidate_approval"]["source_execution_sha256"] = self._execution_source_sha(qa_execution_payload)
            qa_execution_path.write_text(json.dumps(qa_execution_payload), encoding="utf-8")
            operator_execution_path = artifact_path(root, "operator_feedback.execution.json")
            operator_execution_payload = {
                "schema_version": "operator-feedback-execution/1",
                "verdict": "human_needed",
                "promotion_status": "rolled_back",
                "candidate_approval": {
                    "status": "human_needed_candidate_ready",
                    "candidate_path": str(right_candidate),
                    "candidate_sha256": "sha256:" + hashlib.sha256(right_candidate.read_bytes()).hexdigest(),
                    "base_manuscript_sha256": base_sha,
                    "source_execution_path": str(operator_execution_path),
                    "source_execution_sha256": "pending_until_execution_write",
                    "created_at": "2026-05-03T00:00:01Z",
                },
                "candidate_progress": {
                    "forward_progress": True,
                    "before_failing_codes": ["citation_support_unsupported"],
                    "after_failing_codes": ["citation_support_manual_check"],
                },
                "candidate_state": {"verification": {"validate_current": {"ok": True}}},
            }
            operator_execution_payload["candidate_approval"]["source_execution_sha256"] = self._execution_source_sha(operator_execution_payload)
            operator_execution_path.write_text(json.dumps(operator_execution_payload), encoding="utf-8")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            roles = {artifact["role"] for artifact in packet["artifacts"]}
            self.assertIn("qa_loop_execution", roles)
            self.assertIn("operator_feedback_execution", roles)
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="operator_feedback_execution",
                source_item_key="candidate_approval",
                target_section="Whole manuscript",
                rationale="Approve the operator-generated candidate, not the stale QA-loop candidate.",
                suggested_action="Promote the operator-feedback candidate.",
            )
            feedback_path = root / "operator-feedback-approve.json"
            feedback_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback/1",
                        "source": "codex_operator",
                        "not_independent_human_review": True,
                        "intent": "approve_existing_candidate",
                        "packet_sha256": packet["packet_sha256"],
                        "manuscript_sha256": packet["manuscript_sha256"],
                        "issues": [
                            {
                                "id": issue_id,
                                "source_artifact_role": "operator_feedback_execution",
                                "source_item_key": "candidate_approval",
                                "target_section": "Whole manuscript",
                                "severity": "major",
                                "rationale": "Approve the operator-generated candidate, not the stale QA-loop candidate.",
                                "suggested_action": "Promote the operator-feedback candidate.",
                                "authority_class": "author_feedback",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            manual_check_eval = {
                "session_id": state.session_id,
                "mode": "claim_safe",
                "tiers": {
                    "tier_0_preconditions": {"status": "pass"},
                    "tier_1_structural": {"status": "pass"},
                    "tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_manual_check"]},
                },
            }
            with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                    with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                        with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", manual_check_eval)):
                            with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "human_needed"})):
                                _, approved = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)
            self.assertEqual(approved["promotion_status"], "promoted")
            self.assertIn("Right operator candidate", paper.read_text(encoding="utf-8"))
            self.assertNotIn("Wrong QA candidate", paper.read_text(encoding="utf-8"))

    def test_operator_feedback_approval_accepts_nested_operator_candidate_source_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nBase draft.\n\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            base_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            candidate = artifact_path(root, "nested-operator-candidate.tex")
            candidate.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nNested operator candidate.\n\\end{document}\n",
                encoding="utf-8",
            )
            candidate_sha = "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest()
            embedded_source_path = root / ".paper-orchestra" / "qa-loop-execution.iter-02.json"
            source_execution_payload = {
                "schema_version": "qa-loop-execution/1",
                "verdict": "human_needed",
                "candidate_approval": {
                    "status": "human_needed_candidate_ready",
                    "candidate_path": str(candidate),
                    "candidate_sha256": candidate_sha,
                    "base_manuscript_sha256": base_sha,
                    "source_execution_path": str(embedded_source_path),
                    "source_execution_sha256": "pending_until_execution_write",
                    "created_at": "2026-05-04T00:00:00Z",
                },
                "candidate_progress": {
                    "forward_progress": True,
                    "before_failing_codes": ["citation_support_insufficient_evidence"],
                    "after_failing_codes": [],
                },
                "candidate_state": {"verification": {"validate_current": {"ok": True}}},
            }
            source_execution_payload["candidate_approval"]["source_execution_sha256"] = self._execution_source_sha(source_execution_payload)
            operator_execution_path = artifact_path(root, "operator_feedback.execution.json")
            operator_execution_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback-execution/1",
                        "verdict": "human_needed",
                        "promotion_status": "rolled_back",
                        "candidate_branch": "approve_existing_candidate",
                        "candidate_result": {
                            "candidate_path": str(candidate),
                            "candidate_sha256": candidate_sha,
                            "candidate_approval": source_execution_payload["candidate_approval"],
                            "candidate_progress": source_execution_payload["candidate_progress"],
                            "candidate_state": source_execution_payload["candidate_state"],
                            "source_execution": source_execution_payload,
                            "executor_source_role": "qa_loop_execution",
                            "executor_failure_category": "none",
                        },
                    }
                ),
                encoding="utf-8",
            )
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            operator_record = next(artifact for artifact in packet["artifacts"] if artifact["role"] == "operator_feedback_execution")
            self.assertNotEqual(str(embedded_source_path.resolve()), str(Path(operator_record["path"]).resolve()))
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="operator_feedback_execution",
                source_item_key="candidate_result.candidate_approval",
                target_section="Whole manuscript",
                rationale="The nested operator candidate is approved by the operator.",
                suggested_action="Promote the nested operator candidate.",
            )
            feedback_path = root / "operator-feedback-approve.json"
            feedback_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback/1",
                        "source": "codex_operator",
                        "not_independent_human_review": True,
                        "intent": "approve_existing_candidate",
                        "packet_sha256": packet["packet_sha256"],
                        "manuscript_sha256": packet["manuscript_sha256"],
                        "issues": [
                            {
                                "id": issue_id,
                                "source_artifact_role": "operator_feedback_execution",
                                "source_item_key": "candidate_result.candidate_approval",
                                "target_section": "Whole manuscript",
                                "severity": "major",
                                "rationale": "The nested operator candidate is approved by the operator.",
                                "suggested_action": "Promote the nested operator candidate.",
                                "authority_class": "author_feedback",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            quality_eval = {
                "session_id": state.session_id,
                "mode": "claim_safe",
                "tiers": {
                    "tier_0_preconditions": {"status": "pass"},
                    "tier_1_structural": {"status": "pass"},
                    "tier_2_claim_safety": {"status": "pass"},
                },
            }
            with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                    with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                        with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                            with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "continue"})):
                                _, approved = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)

            self.assertEqual(approved["promotion_status"], "promoted")
            self.assertEqual(approved["candidate_result"]["executor_source_role"], "operator_feedback_execution")
            self.assertIn("Nested operator candidate", paper.read_text(encoding="utf-8"))

    def test_operator_feedback_refreshes_figure_review_for_candidate_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
            review = review_path(root, "review.latest.json")
            review.write_text(json.dumps({"overall_score": 70, "axis_scores": {}, "summary": {"weaknesses": [], "top_improvements": []}, "questions": [], "penalties": []}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.latest_review_json = str(review)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            artifact_path(root, "quality-eval.json").write_text(json.dumps({"schema_version": "quality-eval/1", "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["existing_claim_issue"]}}}), encoding="utf-8")
            # Simulate the live-smoke path: a figure-placement review exists for
            # the pre-feedback manuscript. Candidate staging changes the
            # manuscript hash, so operator verification must refresh this review
            # before quality-eval runs; otherwise Tier 0 reports
            # figure_placement_review_stale and rejects a valid candidate.
            stale_figure_path, stale_figure_payload = write_figure_placement_review(root)
            self.assertEqual(stale_figure_payload["manuscript_sha256"], hashlib.sha256(paper.read_bytes()).hexdigest())
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(packet["packet_sha256"], source_artifact_role="paper_full_tex", source_item_key="Intro:p1", target_section="Intro", rationale="The contribution paragraph is missing.", suggested_action="Add contribution language.")
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "intent": "generate_new_operator_candidate", "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{"id": issue_id, "source_artifact_role": "paper_full_tex", "source_item_key": "Intro:p1", "target_section": "Intro", "severity": "major", "rationale": "The contribution paragraph is missing.", "suggested_action": "Add contribution language.", "authority_class": "prose_rewrite"}]}), encoding="utf-8")
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            candidate = artifact_path(root, "candidate-with-figure-refresh.tex")
            candidate.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft. Contribution language.\n\\end{document}\n", encoding="utf-8")

            def fake_refine(cwd, provider, **kwargs):
                return [{"iteration": 1, "candidate_path": str(candidate), "candidate_sha256": "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest(), "score_before": 70, "score_after": 70, "axis_scores_before": {}, "axis_scores_after": {}}]

            quality_eval = {"session_id": state.session_id, "mode": "claim_safe", "tiers": {"tier_0_preconditions": {"status": "pass"}, "tier_1_structural": {"status": "pass"}, "tier_2_claim_safety": {"status": "pass"}}}
            with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=fake_refine):
                with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                    with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                        with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                            with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                                with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "continue"})):
                                    _, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)

            self.assertEqual(execution["promotion_status"], "promoted")
            attempt = execution["attempts"][0]
            self.assertNotIn("tier0_failed", attempt["gate_reasons"])
            figure_block = attempt["verification"]["figure_placement_review"]
            self.assertEqual(Path(figure_block["path"]).resolve(), stale_figure_path.resolve())
            self.assertNotEqual(stale_figure_payload["manuscript_sha256"], hashlib.sha256(candidate.read_bytes()).hexdigest())
            self.assertEqual(figure_block["manuscript_sha256"], hashlib.sha256(candidate.read_bytes()).hexdigest())

    def test_operator_feedback_promotes_existing_candidate_with_continue_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            artifact_path(root, "quality-eval.json").write_text(
                json.dumps(
                    {
                        "schema_version": "quality-eval/1",
                        "session_id": state.session_id,
                        "mode": "claim_safe",
                        "tiers": {
                            "tier_0_preconditions": {"status": "pass"},
                            "tier_1_structural": {"status": "pass"},
                            "tier_2_claim_safety": {
                                "status": "fail",
                                "failing_codes": ["citation_support_manual_check", "citation_support_weak"],
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            candidate = artifact_path(root, "paper.candidate.tex")
            candidate.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft. Candidate improvement.\n\\end{document}\n", encoding="utf-8")
            candidate_sha = "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest()
            base_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            execution_path = root / ".paper-orchestra" / "qa-loop-execution.iter-01.json"
            execution_payload = {"schema_version": "qa-loop-execution/1", "verdict": "human_needed", "candidate_approval": {"status": "human_needed_candidate_ready", "candidate_path": str(candidate), "candidate_sha256": candidate_sha, "base_manuscript_sha256": base_sha, "source_execution_path": str(execution_path), "source_execution_sha256": "pending_until_execution_write", "created_at": "2026-04-27T00:00:00Z"}, "candidate_progress": {"forward_progress": True, "before_failing_codes": ["citation_support_critic_failed"], "after_failing_codes": []}, "candidate_state": {"verification": {"validate_current": {"ok": True}}}}
            execution_payload["candidate_approval"]["source_execution_sha256"] = self._execution_source_sha(execution_payload)
            execution_path.write_text(json.dumps(execution_payload), encoding="utf-8")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(packet["packet_sha256"], source_artifact_role="qa_loop_execution", source_item_key="candidate_approval", target_section="Whole manuscript", rationale="Candidate is ready for supervised approval.", suggested_action="Approve the ready candidate.")
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "intent": "approve_existing_candidate", "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{"id": issue_id, "source_artifact_role": "qa_loop_execution", "source_item_key": "candidate_approval", "target_section": "Whole manuscript", "severity": "major", "rationale": "Candidate is ready for supervised approval.", "suggested_action": "Approve the ready candidate.", "authority_class": "author_feedback"}]}), encoding="utf-8")
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            quality_eval = {"session_id": state.session_id, "mode": "claim_safe", "tiers": {"tier_0_preconditions": {"status": "pass"}, "tier_1_structural": {"status": "pass"}, "tier_2_claim_safety": {"status": "pass"}}}
            with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                    with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                        with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                            with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "continue"})):
                                _, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)
            self.assertEqual(execution["promotion_status"], "promoted")
            self.assertEqual(execution["post_promotion_qa_verdict"], "continue")
            self.assertIn("Candidate improvement", paper.read_text(encoding="utf-8"))

    def test_operator_feedback_promotes_existing_candidate_with_reduced_citation_issue_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            candidate = artifact_path(root, "paper.candidate.tex")
            candidate.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft. Candidate reduces citation issue count.\n\\end{document}\n", encoding="utf-8")
            candidate_sha = "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest()
            base_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            execution_path = root / ".paper-orchestra" / "qa-loop-execution.iter-01.json"
            execution_payload = {
                "schema_version": "qa-loop-execution/1",
                "verdict": "human_needed",
                "candidate_approval": {
                    "status": "human_needed_candidate_ready",
                    "candidate_path": str(candidate),
                    "candidate_sha256": candidate_sha,
                    "base_manuscript_sha256": base_sha,
                    "source_execution_path": str(execution_path),
                    "source_execution_sha256": "pending_until_execution_write",
                    "created_at": "2026-04-27T00:00:00Z",
                },
                "candidate_progress": {
                    "forward_progress": True,
                    "before_failing_codes": ["citation_support_manual_check", "citation_support_weak"],
                    "after_failing_codes": ["citation_support_manual_check", "citation_support_weak"],
                    "before_citation_issue_count": 22,
                    "after_citation_issue_count": 20,
                    "citation_issue_delta": -2,
                },
                "candidate_state": {"verification": {"validate_current": {"ok": True}}},
            }
            execution_payload["candidate_approval"]["source_execution_sha256"] = self._execution_source_sha(execution_payload)
            execution_path.write_text(json.dumps(execution_payload), encoding="utf-8")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(packet["packet_sha256"], source_artifact_role="qa_loop_execution", source_item_key="candidate_approval", target_section="Whole manuscript", rationale="Candidate reduces citation issue count.", suggested_action="Approve the ready candidate.")
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "intent": "approve_existing_candidate", "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{"id": issue_id, "source_artifact_role": "qa_loop_execution", "source_item_key": "candidate_approval", "target_section": "Whole manuscript", "severity": "major", "rationale": "Candidate reduces citation issue count.", "suggested_action": "Approve the ready candidate.", "authority_class": "author_feedback"}]}), encoding="utf-8")
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            quality_eval = {"session_id": state.session_id, "mode": "claim_safe", "tiers": {"tier_0_preconditions": {"status": "pass"}, "tier_1_structural": {"status": "pass"}, "tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_manual_check"]}}}
            with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                    with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                        with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                            with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "continue"})):
                                _, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)
            self.assertEqual(execution["promotion_status"], "promoted")
            self.assertNotIn("active_blocker_progress_missing", execution["attempts"][0]["gate_reasons"])
            self.assertIn("Candidate reduces citation issue count", paper.read_text(encoding="utf-8"))

    def test_operator_feedback_rejects_existing_candidate_without_resolved_active_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            original = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n"
            paper.write_text(original, encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            candidate = artifact_path(root, "paper.candidate.tex")
            candidate.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft. Same blocker candidate.\n\\end{document}\n", encoding="utf-8")
            candidate_sha = "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest()
            base_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            execution_path = root / ".paper-orchestra" / "qa-loop-execution.iter-01.json"
            execution_payload = {
                "schema_version": "qa-loop-execution/1",
                "verdict": "human_needed",
                "candidate_approval": {
                    "status": "human_needed_candidate_ready",
                    "candidate_path": str(candidate),
                    "candidate_sha256": candidate_sha,
                    "base_manuscript_sha256": base_sha,
                    "source_execution_path": str(execution_path),
                    "source_execution_sha256": "pending_until_execution_write",
                    "created_at": "2026-04-27T00:00:00Z",
                },
                "candidate_progress": {
                    "forward_progress": True,
                    "before_failing_codes": ["citation_support_critic_failed"],
                    "after_failing_codes": ["citation_support_critic_failed"],
                },
                "candidate_state": {"verification": {"validate_current": {"ok": True}}},
            }
            execution_payload["candidate_approval"]["source_execution_sha256"] = self._execution_source_sha(execution_payload)
            execution_path.write_text(json.dumps(execution_payload), encoding="utf-8")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(packet["packet_sha256"], source_artifact_role="qa_loop_execution", source_item_key="candidate_approval", target_section="Whole manuscript", rationale="Candidate does not resolve the blocker.", suggested_action="Reject same-blocker candidate.")
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "intent": "approve_existing_candidate", "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{"id": issue_id, "source_artifact_role": "qa_loop_execution", "source_item_key": "candidate_approval", "target_section": "Whole manuscript", "severity": "major", "rationale": "Candidate does not resolve the blocker.", "suggested_action": "Reject same-blocker candidate.", "authority_class": "author_feedback"}]}), encoding="utf-8")
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)

            _, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)

            self.assertEqual(execution["promotion_status"], "rolled_back")
            self.assertIn("resolved active blockers", execution["error"])
            self.assertEqual(paper.read_text(encoding="utf-8"), original)

    def test_operator_feedback_approval_requires_full_candidate_binding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            candidate = artifact_path(root, "paper.candidate.tex")
            candidate.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nBound candidate.\\end{document}\n", encoding="utf-8")
            execution_path = root / ".paper-orchestra" / "qa-loop-execution.iter-01.json"
            execution_payload = {
                "schema_version": "qa-loop-execution/1",
                "verdict": "human_needed",
                "candidate_approval": {
                    "status": "human_needed_candidate_ready",
                    "candidate_path": str(candidate),
                    "candidate_sha256": "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest(),
                    "base_manuscript_sha256": "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest(),
                    "source_execution_path": str(execution_path),
                    # Missing source_execution_sha256 and created_at must fail closed.
                },
                "candidate_progress": {"forward_progress": True, "before_failing_codes": ["citation_support_weak"], "after_failing_codes": []},
                "candidate_state": {"verification": {"validate_current": {"ok": True}}},
            }
            execution_path.write_text(json.dumps(execution_payload), encoding="utf-8")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(packet["packet_sha256"], source_artifact_role="qa_loop_execution", source_item_key="candidate_approval", target_section="Whole manuscript", rationale="Candidate is missing binding evidence.", suggested_action="Approve only if binding is complete.")
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "intent": "approve_existing_candidate", "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{"id": issue_id, "source_artifact_role": "qa_loop_execution", "source_item_key": "candidate_approval", "target_section": "Whole manuscript", "severity": "major", "rationale": "Candidate is missing binding evidence.", "suggested_action": "Approve only if binding is complete.", "authority_class": "author_feedback"}]}), encoding="utf-8")
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            _, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)
            self.assertEqual(execution["promotion_status"], "rolled_back")
            self.assertIn("missing candidate_approval", execution["error"])
            self.assertEqual(hashlib.sha256(paper.read_bytes()).hexdigest(), hashlib.sha256("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n".encode("utf-8")).hexdigest())

    def test_operator_feedback_rejects_noop_existing_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            original = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n"
            paper.write_text(original, encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            candidate = artifact_path(root, "paper.candidate.tex")
            candidate.write_text(original, encoding="utf-8")
            execution_path = root / ".paper-orchestra" / "qa-loop-execution.iter-01.json"
            execution_payload = {
                "schema_version": "qa-loop-execution/1",
                "verdict": "human_needed",
                "candidate_approval": {
                    "status": "human_needed_candidate_ready",
                    "candidate_path": str(candidate),
                    "candidate_sha256": "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest(),
                    "base_manuscript_sha256": "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest(),
                    "source_execution_path": str(execution_path),
                    "source_execution_sha256": "pending_until_execution_write",
                    "created_at": "2026-04-27T00:00:00Z",
                },
                "candidate_progress": {"forward_progress": True, "before_failing_codes": ["citation_support_weak"], "after_failing_codes": []},
                "candidate_state": {"verification": {"validate_current": {"ok": True}}},
            }
            execution_payload["candidate_approval"]["source_execution_sha256"] = self._execution_source_sha(execution_payload)
            execution_path.write_text(json.dumps(execution_payload), encoding="utf-8")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(packet["packet_sha256"], source_artifact_role="qa_loop_execution", source_item_key="candidate_approval", target_section="Whole manuscript", rationale="No-op candidate should not be promoted.", suggested_action="Reject the no-op candidate.")
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "intent": "approve_existing_candidate", "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{"id": issue_id, "source_artifact_role": "qa_loop_execution", "source_item_key": "candidate_approval", "target_section": "Whole manuscript", "severity": "major", "rationale": "No-op candidate should not be promoted.", "suggested_action": "Reject the no-op candidate.", "authority_class": "author_feedback"}]}), encoding="utf-8")
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            quality_eval = {"session_id": state.session_id, "mode": "claim_safe", "tiers": {"tier_0_preconditions": {"status": "pass"}, "tier_1_structural": {"status": "pass"}, "tier_2_claim_safety": {"status": "pass", "failing_codes": []}}}
            with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                    with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                        with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                            with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "continue"})):
                                _, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)
            self.assertEqual(execution["promotion_status"], "rolled_back")
            self.assertIn("no_textual_change", execution["attempts"][-1]["gate_reasons"])
            self.assertIn("executor_returned_identical_content", execution["attempts"][-1]["gate_reasons"])
            self.assertNotIn("executor_crashed", execution["attempts"][-1]["gate_reasons"])
            self.assertEqual(execution["attempts"][-1]["executor_failure_category"], "none")
            self.assertEqual(execution["attempts"][-1]["executor_environment"], "preexisting_candidate")
            self.assertEqual(paper.read_text(encoding="utf-8"), original)

    def test_import_operator_feedback_accepts_action_kind_intent_and_rejects_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(packet["packet_sha256"], source_artifact_role="paper_full_tex", source_item_key="Intro:p1", target_section="Intro", rationale="Needs direction.", suggested_action="Add direction.")
            base_issue = {"id": issue_id, "source_artifact_role": "paper_full_tex", "source_item_key": "Intro:p1", "target_section": "Intro", "severity": "major", "rationale": "Needs direction.", "suggested_action": "Add direction.", "authority_class": "prose_rewrite"}
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{**base_issue, "action_kind": "generate_new_operator_candidate"}]}), encoding="utf-8")
            _, imported = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            self.assertEqual(imported["intent"], "generate_new_operator_candidate")
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "intent": "approve_existing_candidate", "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{**base_issue, "action_kind": "generate_new_operator_candidate"}]}), encoding="utf-8")
            with self.assertRaises(ContractError):
                import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path, output_path=root / "conflict.json")

    def test_operator_feedback_blocks_only_new_tier2_claim_safety_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
            review = review_path(root, "review.latest.json")
            review.write_text(json.dumps({"overall_score": 70, "axis_scores": {}, "summary": {"weaknesses": [], "top_improvements": []}, "questions": [], "penalties": []}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.latest_review_json = str(review)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            base_eval_path = artifact_path(root, "quality-eval.json")
            base_eval_path.write_text(json.dumps({"schema_version": "quality-eval/1", "session_id": state.session_id, "mode": "claim_safe", "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["existing_claim_issue"]}}}), encoding="utf-8")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(packet["packet_sha256"], source_artifact_role="paper_full_tex", source_item_key="Intro:p1", target_section="Intro", rationale="The contribution paragraph is missing.", suggested_action="Add contribution language.")
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "intent": "generate_new_operator_candidate", "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{"id": issue_id, "source_artifact_role": "paper_full_tex", "source_item_key": "Intro:p1", "target_section": "Intro", "severity": "major", "rationale": "The contribution paragraph is missing.", "suggested_action": "Add contribution language.", "authority_class": "prose_rewrite"}]}), encoding="utf-8")
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            candidate = artifact_path(root, "candidate-tier2.tex")
            candidate.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft. Contribution language.\n\\end{document}\n", encoding="utf-8")

            def fake_refine(cwd, provider, **kwargs):
                return [{"iteration": 1, "candidate_path": str(candidate), "candidate_sha256": "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest(), "score_before": 70, "score_after": 70, "axis_scores_before": {}, "axis_scores_after": {}}]

            def run_with_codes(codes):
                paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
                quality_eval = {"session_id": state.session_id, "mode": "claim_safe", "tiers": {"tier_0_preconditions": {"status": "pass"}, "tier_1_structural": {"status": "pass"}, "tier_2_claim_safety": {"status": "fail" if codes else "pass", "failing_codes": codes}}}
                with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=fake_refine):
                    with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                        with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                            with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                                with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                                    with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "continue"})):
                                        return apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)[1]

            existing_only = run_with_codes(["existing_claim_issue"])
            self.assertEqual(existing_only["promotion_status"], "rolled_back")
            self.assertIn("active_blocker_progress_missing", existing_only["attempts"][-1]["gate_reasons"])
            self.assertEqual(existing_only["attempts"][-1]["resolved_active_failures"], [])
            resolved = run_with_codes([])
            self.assertEqual(resolved["promotion_status"], "promoted")
            self.assertEqual(resolved["attempts"][-1]["resolved_active_failures"], ["existing_claim_issue"])
            with_new = run_with_codes(["existing_claim_issue", "new_claim_issue"])
            self.assertEqual(with_new["promotion_status"], "rolled_back")
            self.assertIn("tier2_claim_safety_new_failures", with_new["attempts"][-1]["gate_reasons"])
            self.assertIn("active_blocker_progress_missing", with_new["attempts"][-1]["gate_reasons"])
            self.assertEqual(with_new["attempts"][-1]["new_tier2_failures"], ["new_claim_issue"])

    def test_operator_feedback_rollback_records_restored_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)

            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="paper_full_tex",
                source_item_key="Intro:p1",
                target_section="Intro",
                rationale="The introduction remains unchanged after operator review.",
                suggested_action="Add a concrete contribution paragraph.",
            )
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback/1",
                        "source": "codex_operator",
                        "not_independent_human_review": True,
                        "intent": "generate_new_operator_candidate",
                        "packet_sha256": packet["packet_sha256"],
                        "manuscript_sha256": packet["manuscript_sha256"],
                        "issues": [
                            {
                                "id": issue_id,
                                "source_artifact_role": "paper_full_tex",
                                "source_item_key": "Intro:p1",
                                "target_section": "Intro",
                                "severity": "major",
                                "rationale": "The introduction remains unchanged after operator review.",
                                "suggested_action": "Add a concrete contribution paragraph.",
                                "authority_class": "prose_rewrite",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)

            def fake_refine(cwd, provider, **kwargs):
                return [{"iteration": 1, "accepted": True, "reason": "no textual change"}]

            candidate_eval = {"session_id": state.session_id, "mode": "claim_safe", "manuscript_hash": "sha256:candidate", "tiers": {}}
            restored_eval = {"session_id": state.session_id, "mode": "claim_safe", "manuscript_hash": "sha256:restored", "tiers": {}}
            with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=fake_refine):
                with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                    with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                        with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                            with patch(
                                "paperorchestra.operator_feedback.write_quality_eval",
                                side_effect=[(root / "candidate-quality.json", candidate_eval), (root / "restored-quality.json", restored_eval)],
                            ):
                                with patch(
                                    "paperorchestra.operator_feedback.write_quality_loop_plan",
                                    side_effect=[(root / "candidate-plan.json", {"verdict": "failed"}), (root / "restored-plan.json", {"verdict": "human_needed"})],
                                ):
                                    execution_path, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)

            self.assertTrue(execution_path.exists())
            self.assertEqual(execution["verdict"], "human_needed")
            self.assertEqual(execution["verification"]["qa_loop_plan"]["path"], str(root / "restored-plan.json"))
            self.assertEqual(execution["candidate_rollback"]["restored_verification"]["qa_loop_plan"]["verdict"], "human_needed")
            self.assertIn("executor_returned_identical_content", execution["attempts"][-1]["gate_reasons"])
            self.assertEqual(execution["attempts"][-1]["executor_environment"], "in_process")
            self.assertEqual(execution["attempts"][-1]["executor_failure_category"], "none")
            incorporation = json.loads(Path(execution["incorporation_report"]).read_text(encoding="utf-8"))
            self.assertIn(incorporation["issues"][0]["status"], {"not_reflected", "needs_author_decision"})
            history_path = root / ".paper-orchestra" / "qa-loop-history.jsonl"
            history = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(history[-1]["plan_path"], str(root / "restored-plan.json"))
            self.assertFalse(history[-1]["consumes_budget"])

    def test_operator_feedback_exception_rollback_records_restored_verification_and_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)

            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="paper_full_tex",
                source_item_key="Intro:p1",
                target_section="Intro",
                rationale="The supervised writer crashes after making a candidate change.",
                suggested_action="Attempt a safe introduction rewrite.",
            )
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback/1",
                        "source": "codex_operator",
                        "not_independent_human_review": True,
                        "intent": "generate_new_operator_candidate",
                        "packet_sha256": packet["packet_sha256"],
                        "manuscript_sha256": packet["manuscript_sha256"],
                        "issues": [
                            {
                                "id": issue_id,
                                "source_artifact_role": "paper_full_tex",
                                "source_item_key": "Intro:p1",
                                "target_section": "Intro",
                                "severity": "major",
                                "rationale": "The supervised writer crashes after making a candidate change.",
                                "suggested_action": "Attempt a safe introduction rewrite.",
                                "authority_class": "prose_rewrite",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)

            def crashing_refine(cwd, provider, **kwargs):
                target = Path(load_session(cwd).artifacts.paper_full_tex)
                target.write_text(target.read_text(encoding="utf-8") + "\nBAD CANDIDATE\n", encoding="utf-8")
                raise RuntimeError("boom")

            restored_eval = {"session_id": state.session_id, "mode": "claim_safe", "manuscript_hash": "sha256:restored", "tiers": {}}
            with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=crashing_refine):
                with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                    with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                        with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                            with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "restored-quality.json", restored_eval)):
                                with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "restored-plan.json", {"verdict": "human_needed"})):
                                    execution_path, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)

            self.assertTrue(execution_path.exists())
            self.assertEqual(execution["verdict"], "execution_error")
            self.assertEqual(execution["attempts"][-1]["executor_failure_category"], "unexpected_exception")
            self.assertTrue(execution["attempts"][-1]["executor_trace_artifact"])
            self.assertTrue(Path(execution["attempts"][-1]["executor_trace_artifact"]).exists())
            self.assertIn("executor_crashed", execution["attempts"][-1]["gate_reasons"])
            self.assertNotIn("BAD CANDIDATE", paper.read_text(encoding="utf-8"))
            restored = execution["candidate_rollback"]["restored_verification"]
            self.assertEqual(restored["qa_loop_plan"]["path"], str(root / "restored-plan.json"))
            self.assertEqual(restored["qa_loop_plan"]["verdict"], "human_needed")
            history_path = root / ".paper-orchestra" / "qa-loop-history.jsonl"
            history = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(history[-1]["event_type"], "operator_feedback_cycle")
            self.assertEqual(history[-1]["verdict"], "execution_error")
            self.assertEqual(history[-1]["plan_path"], str(root / "restored-plan.json"))
            self.assertFalse(history[-1]["consumes_budget"])

    def test_qa_loop_step_cli_passes_citation_provider_settings(self) -> None:
        class Result:
            path = Path("execution.json")
            payload = {"verdict": "continue"}
            exit_code = 10

        stdout = io.StringIO()
        with patch("paperorchestra.cli.run_qa_loop_step", return_value=Result()) as runner:
            with contextlib.redirect_stdout(stdout):
                code = cli_main(
                    [
                        "qa-loop-step",
                        "--citation-evidence-mode",
                        "model",
                        "--provider",
                        "shell",
                        "--provider-command",
                        '["codex","exec"]',
                    ]
                )

        self.assertEqual(code, 10)
        self.assertEqual(runner.call_args.kwargs["citation_provider_name"], "shell")
        self.assertEqual(runner.call_args.kwargs["citation_provider_command"], '["codex","exec"]')

    def test_qa_loop_step_model_evidence_defaults_to_shell_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            quality_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_review_missing"]}},
            }
            plan = {
                "verdict": "continue",
                "repair_actions": [{"code": "citation_support_review_missing", "automation": "automatic"}],
            }
            with patch("paperorchestra.ralph_bridge.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                with patch("paperorchestra.ralph_bridge.write_quality_loop_plan", return_value=(root / "plan.json", plan)):
                    with patch("paperorchestra.ralph_bridge._citation_summary", return_value={}):
                        with patch("paperorchestra.ralph_bridge.get_citation_support_provider", return_value=None) as provider_factory:
                            with patch("paperorchestra.ralph_bridge.write_citation_support_review", return_value=root / "citation.json"):
                                run_qa_loop_step(root, MockProvider(), citation_evidence_mode="model")

            self.assertEqual(provider_factory.call_args.args[0], "shell")

    def test_repair_citation_claims_restores_validation_pointer_on_compile_reject(self) -> None:
        class RepairProvider(MockProvider):
            def __init__(self, latex: str):
                self.latex = latex

            def complete(self, request: CompletionRequest) -> str:
                return "```latex\n" + self.latex + "\n```"

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            seed_path = root / "refs.bib"
            seed_path.write_text(
                "@techreport{RFC9001,\n"
                "  title = {Using {TLS} to Secure {QUIC}},\n"
                "  author = {Martin Thomson and Sean Turner},\n"
                "  year = {2021},\n"
                "  url = {https://www.rfc-editor.org/rfc/rfc9001}\n"
                "}\n",
                encoding="utf-8",
            )
            import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
            paper = artifact_path(root, "paper.full.tex")
            original = (
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\n"
                "QUIC uses TLS~\\cite{RFC9001}.\n"
                "\\bibliographystyle{plain}\n\\bibliography{references}\n\\end{document}\n"
            )
            paper.write_text(original, encoding="utf-8")
            state = load_session(root)
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            previous_validation, _ = record_current_validation_report(root, name="validation.previous.json")
            review_path = artifact_path(root, "citation_support_review.json")
            review_path.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "id": "cite-001",
                                "sentence": "QUIC uses TLS~\\cite{RFC9001}.",
                                "citation_keys": ["RFC9001"],
                                "support_status": "weakly_supported",
                                "risk": "medium",
                                "suggested_fix": "Soften.",
                            }
                        ],
                        "summary": {"weakly_supported": 1},
                    }
                ),
                encoding="utf-8",
            )
            provider = RepairProvider(original)

            with patch("paperorchestra.ralph_bridge_repair.compile_current_paper", side_effect=RuntimeError("compile down")):
                result = repair_citation_claims(root, provider, citation_review_path=review_path, require_compile=True)

            self.assertFalse(result["accepted"])
            self.assertEqual(result["reason"], "compile_failed")
            self.assertEqual(paper.read_text(encoding="utf-8"), original)
            restored_state = load_session(root)
            self.assertEqual(restored_state.artifacts.latest_validation_json, str(previous_validation))
            self.assertIsNone(restored_state.artifacts.latest_compile_report_json)
            self.assertIsNone(restored_state.artifacts.compiled_pdf)

    def test_qa_loop_step_rolls_back_candidate_on_verification_exception(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            original = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nOriginal.\\end{document}\n"
            candidate = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nCandidate.\\end{document}\n"
            paper.write_text(original, encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            quality_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_weak"]}},
            }
            plan = {
                "verdict": "continue",
                "repair_actions": [{"code": "citation_support_critic_failed", "automation": "semi_auto"}],
            }
            repair_result = {"accepted": True, "candidate_path": str(root / "candidate.tex")}
            Path(repair_result["candidate_path"]).write_text(candidate, encoding="utf-8")
            with patch("paperorchestra.ralph_bridge.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                with patch("paperorchestra.ralph_bridge.write_quality_loop_plan", return_value=(root / "plan.json", plan)):
                    with patch("paperorchestra.ralph_bridge._citation_summary", return_value={}):
                        with patch("paperorchestra.ralph_bridge.repair_citation_claims", return_value=repair_result):
                            with patch("paperorchestra.ralph_bridge.write_citation_support_review", side_effect=RuntimeError("critic down")):
                                result = run_qa_loop_step(root, MockProvider(), citation_evidence_mode="heuristic")

            self.assertEqual(result.exit_code, 40)
            self.assertEqual(result.payload["verdict"], "execution_error")
            self.assertEqual(paper.read_text(encoding="utf-8"), original)

    def test_qa_loop_step_exposes_forward_progress_candidate_with_human_reviewable_residuals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            original = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nOriginal.\\end{document}\n"
            candidate = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nCandidate.\\end{document}\n"
            paper.write_text(original, encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            before_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "manuscript_hash": "sha256:original",
                "tiers": {
                    "tier_2_claim_safety": {
                        "status": "fail",
                        "failing_codes": [
                            "citation_support_insufficient_evidence",
                            "citation_support_weak",
                        ],
                    }
                },
            }
            candidate_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "manuscript_hash": "sha256:candidate",
                "tiers": {
                    "tier_2_claim_safety": {
                        "status": "fail",
                        "failing_codes": ["citation_support_weak"],
                    }
                },
            }
            restored_eval = before_eval
            before_plan = {
                "verdict": "continue",
                "repair_actions": [{"code": "citation_support_critic_failed", "automation": "semi_auto"}],
            }
            candidate_plan = {
                "verdict": "continue",
                "repair_actions": [{"code": "citation_support_critic_failed", "automation": "semi_auto"}],
            }
            restored_plan = before_plan
            repair_result = {"accepted": True, "candidate_path": str(root / "candidate.tex")}
            Path(repair_result["candidate_path"]).write_text(candidate, encoding="utf-8")
            artifact_dir = artifact_path(root, "paper.full.tex").parent
            citation_review_path = artifact_dir / "citation_support_review.json"
            citation_trace_path = artifact_dir / "citation_support_review.trace.json"
            citation_review_path.write_text(json.dumps({"summary": {"insufficient_evidence": 1, "weakly_supported": 1}}), encoding="utf-8")
            original_trace = {"manuscript_sha256": "original-hash"}
            citation_trace_path.write_text(json.dumps(original_trace), encoding="utf-8")

            def overwrite_citation_review(*args, **kwargs):
                citation_review_path.write_text(json.dumps({"summary": {"weakly_supported": 1}}), encoding="utf-8")
                citation_trace_path.write_text(json.dumps({"manuscript_sha256": "candidate-hash"}), encoding="utf-8")
                return citation_review_path

            with patch(
                "paperorchestra.ralph_bridge.write_quality_eval",
                side_effect=[
                    (root / "before-q.json", before_eval),
                    (root / "candidate-q.json", candidate_eval),
                    (root / "restored-q.json", restored_eval),
                ],
            ):
                with patch(
                    "paperorchestra.ralph_bridge.write_quality_loop_plan",
                    side_effect=[
                        (root / "before-p.json", before_plan),
                        (root / "candidate-p.json", candidate_plan),
                        (root / "restored-p.json", restored_plan),
                    ],
                ):
                    with patch(
                        "paperorchestra.ralph_bridge._citation_summary",
                        side_effect=[
                            {"insufficient_evidence": 1, "weakly_supported": 1},
                            {"weakly_supported": 1},
                            {"insufficient_evidence": 1, "weakly_supported": 1},
                        ],
                    ):
                        with patch("paperorchestra.ralph_bridge.repair_citation_claims", return_value=repair_result):
                            with patch("paperorchestra.ralph_bridge.write_citation_support_review", side_effect=overwrite_citation_review):
                                result = run_qa_loop_step(root, MockProvider(), citation_evidence_mode="heuristic")

            self.assertEqual(result.exit_code, 20)
            self.assertEqual(result.payload["verdict"], "human_needed")
            self.assertEqual(result.payload["candidate_approval"]["status"], "human_needed_candidate_ready")
            approved_candidate_path = Path(result.payload["candidate_approval"]["candidate_path"])
            self.assertNotEqual(approved_candidate_path.resolve(), Path(repair_result["candidate_path"]).resolve())
            self.assertEqual(
                result.payload["candidate_approval"]["candidate_sha256"],
                "sha256:" + hashlib.sha256(approved_candidate_path.read_bytes()).hexdigest(),
            )
            Path(repair_result["candidate_path"]).write_text("mutated volatile candidate", encoding="utf-8")
            self.assertEqual(approved_candidate_path.read_text(encoding="utf-8"), candidate)
            self.assertEqual(
                result.payload["candidate_handoff"]["status"],
                "human_needed_candidate_ready_with_residual_citation_support",
            )
            self.assertEqual(result.payload["candidate_handoff"]["residual_citation_failures"], ["citation_support_weak"])
            self.assertEqual(result.payload["candidate_progress"]["resolved_codes"], ["citation_support_insufficient_evidence"])
            self.assertTrue(result.payload["candidate_progress"]["forward_progress"])
            self.assertEqual(result.payload["candidate_state"]["after"]["failing_codes"], ["citation_support_weak"])
            self.assertEqual(result.payload["after"]["failing_codes"], ["citation_support_insufficient_evidence", "citation_support_weak"])
            self.assertEqual(paper.read_text(encoding="utf-8"), original)

    def test_qa_loop_step_keeps_approved_semi_auto_candidate_uncommitted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            original = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nOriginal.\\end{document}\n"
            candidate = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nCandidate.\\end{document}\n"
            paper.write_text(original, encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            before_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "manuscript_hash": "sha256:original",
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_weak"]}},
            }
            after_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "manuscript_hash": "sha256:candidate",
                "tiers": {"tier_2_claim_safety": {"status": "pass", "failing_codes": []}},
            }
            restored_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "manuscript_hash": "sha256:original",
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_weak"]}},
            }
            before_plan = {
                "verdict": "continue",
                "repair_actions": [{"code": "citation_support_critic_failed", "automation": "semi_auto"}],
            }
            after_plan = {"verdict": "ready_for_human_finalization", "repair_actions": []}
            restored_plan = {"verdict": "human_needed", "repair_actions": [{"code": "citation_support_critic_failed", "automation": "semi_auto"}]}
            repair_result = {"accepted": True, "candidate_path": str(root / "candidate.tex")}
            Path(repair_result["candidate_path"]).write_text(candidate, encoding="utf-8")
            artifact_dir = artifact_path(root, "paper.full.tex").parent
            citation_review_path = artifact_dir / "citation_support_review.json"
            citation_trace_path = artifact_dir / "citation_support_review.trace.json"
            citation_review_path.write_text(json.dumps({"summary": {"weakly_supported": 1}}), encoding="utf-8")
            original_trace = {"manuscript_sha256": "original-hash"}
            citation_trace_path.write_text(json.dumps(original_trace), encoding="utf-8")

            def overwrite_citation_review(*args, **kwargs):
                citation_review_path.write_text(json.dumps({"summary": {"supported": 1}}), encoding="utf-8")
                citation_trace_path.write_text(json.dumps({"manuscript_sha256": "candidate-hash"}), encoding="utf-8")
                return citation_review_path

            with patch(
                "paperorchestra.ralph_bridge.write_quality_eval",
                side_effect=[
                    (root / "before-q.json", before_eval),
                    (root / "candidate-q.json", after_eval),
                    (root / "restored-q.json", restored_eval),
                ],
            ):
                with patch(
                    "paperorchestra.ralph_bridge.write_quality_loop_plan",
                    side_effect=[
                        (root / "before-p.json", before_plan),
                        (root / "candidate-p.json", after_plan),
                        (root / "restored-p.json", restored_plan),
                    ],
                ):
                    with patch(
                        "paperorchestra.ralph_bridge._citation_summary",
                        side_effect=[{"weakly_supported": 1}, {"supported": 1}, {"weakly_supported": 1}],
                    ):
                        with patch("paperorchestra.ralph_bridge.repair_citation_claims", return_value=repair_result):
                            with patch("paperorchestra.ralph_bridge.write_citation_support_review", side_effect=overwrite_citation_review):
                                result = run_qa_loop_step(root, MockProvider(), citation_evidence_mode="heuristic")

            self.assertEqual(result.exit_code, 20)
            self.assertEqual(result.payload["verdict"], "human_needed")
            self.assertEqual(result.payload["candidate_approval"]["status"], "human_needed_candidate_ready")
            self.assertEqual(result.payload["candidate_progress"]["resolved_codes"], ["citation_support_weak"])
            self.assertTrue(result.payload["candidate_progress"]["forward_progress"])
            self.assertEqual(result.payload["candidate_state"]["qa_loop_plan_verdict"], "ready_for_human_finalization")
            self.assertEqual(result.payload["candidate_state"]["after"]["failing_codes"], [])
            self.assertEqual(result.payload["candidate_state"]["progress"]["resolved_codes"], ["citation_support_weak"])
            self.assertEqual(result.payload["restored_current_state"]["after"]["failing_codes"], ["citation_support_weak"])
            self.assertEqual(result.payload["after"]["failing_codes"], ["citation_support_weak"])
            self.assertFalse(result.payload["progress"]["forward_progress"])
            self.assertEqual(result.payload["progress"], result.payload["restored_current_state"]["progress"])
            self.assertEqual(result.payload["verification"]["quality_eval"]["path"], str(root / "restored-q.json"))
            self.assertEqual(result.payload["verification"]["qa_loop_plan"]["path"], str(root / "restored-p.json"))
            self.assertEqual(result.payload["restored_current_verification"]["quality_eval"]["path"], str(root / "restored-q.json"))
            self.assertEqual(json.loads(citation_trace_path.read_text(encoding="utf-8")), original_trace)
            self.assertTrue(result.payload["restored_current_verification"]["citation_support_trace_restored"]["restored"])
            self.assertEqual(paper.read_text(encoding="utf-8"), original)

    def test_qa_loop_step_refreshes_figure_review_for_uncommitted_citation_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            original = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nOriginal.\\end{document}\n"
            candidate = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nCandidate.\\end{document}\n"
            paper.write_text(original, encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            stale_figure_path, stale_figure_payload = write_figure_placement_review(root)
            self.assertEqual(stale_figure_payload["manuscript_sha256"], hashlib.sha256(original.encode("utf-8")).hexdigest())
            before_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "manuscript_hash": "sha256:original",
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_weak"]}},
            }
            after_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "manuscript_hash": "sha256:candidate",
                "tiers": {"tier_2_claim_safety": {"status": "pass", "failing_codes": []}},
            }
            restored_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "manuscript_hash": "sha256:original",
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_weak"]}},
            }
            before_plan = {
                "verdict": "continue",
                "repair_actions": [{"code": "citation_support_critic_failed", "automation": "semi_auto"}],
            }
            after_plan = {"verdict": "ready_for_human_finalization", "repair_actions": []}
            restored_plan = {"verdict": "human_needed", "repair_actions": [{"code": "citation_support_critic_failed", "automation": "semi_auto"}]}
            repair_result = {"accepted": True, "candidate_path": str(root / "candidate.tex")}
            Path(repair_result["candidate_path"]).write_text(candidate, encoding="utf-8")
            artifact_dir = artifact_path(root, "paper.full.tex").parent
            citation_review_path = artifact_dir / "citation_support_review.json"
            citation_review_path.write_text(json.dumps({"summary": {"weakly_supported": 1}}), encoding="utf-8")
            candidate_hash = hashlib.sha256(candidate.encode("utf-8")).hexdigest()

            def overwrite_citation_review(*args, **kwargs):
                citation_review_path.write_text(json.dumps({"summary": {"supported": 1}}), encoding="utf-8")
                return citation_review_path

            with patch(
                "paperorchestra.ralph_bridge.write_quality_eval",
                side_effect=[
                    (root / "before-q.json", before_eval),
                    (root / "candidate-q.json", after_eval),
                    (root / "restored-q.json", restored_eval),
                ],
            ):
                with patch(
                    "paperorchestra.ralph_bridge.write_quality_loop_plan",
                    side_effect=[
                        (root / "before-p.json", before_plan),
                        (root / "candidate-p.json", after_plan),
                        (root / "restored-p.json", restored_plan),
                    ],
                ):
                    with patch(
                        "paperorchestra.ralph_bridge._citation_summary",
                        side_effect=[{"weakly_supported": 1}, {"supported": 1}, {"weakly_supported": 1}],
                    ):
                        with patch("paperorchestra.ralph_bridge.repair_citation_claims", return_value=repair_result):
                            with patch("paperorchestra.ralph_bridge.write_citation_support_review", side_effect=overwrite_citation_review):
                                result = run_qa_loop_step(root, MockProvider(), citation_evidence_mode="heuristic")

            self.assertEqual(result.exit_code, 20)
            candidate_figure = result.payload["candidate_state"]["verification"]["figure_placement_review"]
            self.assertEqual(Path(candidate_figure["path"]).resolve(), stale_figure_path.resolve())
            self.assertEqual(candidate_figure["manuscript_sha256"], candidate_hash)
            self.assertEqual(
                result.payload["candidate_progress"]["after_failing_codes"],
                [],
            )
            self.assertEqual(paper.read_text(encoding="utf-8"), original)
            restored_figure = result.payload["restored_current_verification"]["figure_placement_review"]
            self.assertEqual(restored_figure["manuscript_sha256"], hashlib.sha256(original.encode("utf-8")).hexdigest())

    def test_section_review_scores_are_not_flat_when_section_shapes_differ(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(root, provider=MockProvider(), discovery_mode="model", verify_mode="mock", refine_iterations=0, compile_paper=False)
            state = load_session(root)
            Path(state.artifacts.paper_full_tex).write_text(
                "\\documentclass{article}\n"
                "\\begin{document}\n"
                "\\section{Introduction}\n"
                "This introduction surveys prior art in detail and cites foundational work~\\cite{paper1}. "
                "It also cites the implementation baseline~\\cite{paper2} while explaining the staged pipeline."
                "\n"
                "\\section{Conclusion}\n"
                "We outperform the baseline.\n"
                "\\section{Experiments}\n"
                "Accuracy improves from 91.2 to 94.8 while latency drops by 12%.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            review = build_section_review(root)
            scores = {item["section_title"]: item["score"] for item in review["sections"]}
            self.assertGreater(len(set(scores.values())), 1)

    def test_section_review_declares_scores_advisory_and_penalizes_process_residue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(root, provider=MockProvider(), discovery_mode="model", verify_mode="mock", refine_iterations=0, compile_paper=False)
            state = load_session(root)
            Path(state.artifacts.paper_full_tex).write_text(
                "\\documentclass{article}\n"
                "\\begin{document}\n"
                "\\section{Discussion}\n"
                "This supplied source material should not appear as manuscript process prose. "
                "The technical boundary is stated as an authorial limitation.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )

            review = build_section_review(root)

            self.assertTrue(review["score_use"]["advisory"])
            self.assertFalse(review["score_use"]["load_bearing"])
            discussion = review["sections"][0]
            self.assertIn("supplied_source", discussion["process_residue_markers"])
            self.assertLess(discussion["score"], 70)

            write_section_review(root)
            check = _section_quality_check(root, load_session(root), quality_mode="claim_safe")
            self.assertFalse(check["load_bearing"])
            self.assertIn("Tier 3 after upstream Tier 0-2 pass", check["load_bearing_context"])
            self.assertIn("section_process_residue_detected", check["failing_codes"])

    def test_section_review_penalizes_uncited_claim_like_conclusion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(root, provider=MockProvider(), discovery_mode="model", verify_mode="mock", refine_iterations=0, compile_paper=False)
            state = load_session(root)
            Path(state.artifacts.paper_full_tex).write_text(
                "\\documentclass{article}\n"
                "\\begin{document}\n"
                "\\section{Conclusion}\n"
                "Our results outperform the baseline and establish a new state-of-the-art result.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            review = build_section_review(root)
            conclusion = review["sections"][0]
            self.assertEqual(conclusion["citation_count"], 0)
            self.assertTrue(conclusion["claim_like"])
            self.assertIn("Add verified citations", " ".join(conclusion["required_fixes"]))
            self.assertLess(conclusion["score"], 85)

    def test_section_and_citation_critic_cli_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(root, provider=MockProvider(), discovery_mode="model", verify_mode="mock", refine_iterations=0)
            old_cwd = Path.cwd()
            try:
                os.chdir(root)
                self.assertEqual(cli_main(["review-sections", "--output", str(root / "section_review.json")]), 0)
                self.assertEqual(cli_main(["review-citations", "--output", str(root / "citation_review.json")]), 0)
            finally:
                os.chdir(old_cwd)
            self.assertTrue((root / "section_review.json").exists())
            self.assertTrue((root / "citation_review.json").exists())

    def test_suggest_revisions_maps_review_items_to_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sections").mkdir()
            main = root / "main.tex"
            main.write_text("\\input{sections/04_security_analysis}\n\\input{sections/05_implementation_results}\n", encoding="utf-8")
            (root / "sections" / "04_security_analysis.tex").write_text("\\section{Security Analysis}", encoding="utf-8")
            (root / "sections" / "05_implementation_results.tex").write_text("\\section{Implementation and Results}", encoding="utf-8")
            review = root / "review.json"
            review.write_text(json.dumps({
                "overall_score": 58,
                "summary": {"weaknesses": ["The integrity proof needs a concrete tamper-detection bound."], "top_improvements": ["Clarify evaluation scope."]},
                "questions": []
            }), encoding="utf-8")
            section_review = root / "section_review.json"
            section_review.write_text(json.dumps({"sections": [{"section_title": "Security Analysis", "required_fixes": ["Add theorem resources."]}]}), encoding="utf-8")
            citation_review = root / "citation_review.json"
            citation_review.write_text(json.dumps({"items": [{"id": "cite-001", "sentence": "Baseline-X is faster \\cite{gcm}.", "support_status": "weakly_supported", "risk": "medium", "suggested_fix": "Narrow the comparative claim."}]}), encoding="utf-8")
            suggestions = build_revision_suggestions(main, review, section_review_json=section_review, citation_review_json=citation_review)
            self.assertEqual(suggestions["action_count"], 4)
            self.assertEqual(suggestions["actions"][0]["target_area"], "security_analysis")
            self.assertEqual(suggestions["actions"][0]["priority"], "P0")
            self.assertEqual(suggestions["actions"][0]["action_type"], "formalize_security_argument")
            self.assertEqual(suggestions["actions"][1]["target_area"], "implementation_results")
            self.assertTrue(any(action["review_trace"]["source"].startswith("section_review") for action in suggestions["actions"]))
            self.assertTrue(any(action["review_trace"]["source"] == "citation_support_review" for action in suggestions["actions"]))
            self.assertIn("security_analysis", suggestions["actions_by_target"])
            self.assertIn("word_count", suggestions["section_diagnostics"]["security_analysis"])
            self.assertIn("suggested_patch_hunk", suggestions["actions"][0])
            self.assertIn("anchor", suggestions["actions"][0]["suggested_patch_hunk"])
            self.assertIn("@@", suggestions["actions"][0]["suggested_patch_hunk"]["hunk_template"])


    def test_critique_cli_runs_full_critic_stack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(root, provider=MockProvider(), discovery_mode="model", verify_mode="mock", refine_iterations=0)
            source = root / "source.tex"
            source.write_text("\\input{sections/04_security_analysis}\n", encoding="utf-8")
            (root / "sections").mkdir()
            (root / "sections" / "04_security_analysis.tex").write_text("\\section{Security Analysis}", encoding="utf-8")
            old_cwd = Path.cwd()
            stdout = io.StringIO()
            try:
                os.chdir(root)
                with contextlib.redirect_stdout(stdout):
                    code = cli_main(["critique", "--provider", "mock", "--source-paper", str(source), "--output-dir", str(root / "critique")])
            finally:
                os.chdir(old_cwd)
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            for key in ["review", "section_review", "citation_support_review", "revision_suggestions"]:
                self.assertTrue(Path(payload[key]).exists())
            suggestions = json.loads(Path(payload["revision_suggestions"]).read_text(encoding="utf-8"))
            self.assertGreater(suggestions["action_count"], 0)

    def test_cleanup_tmp_cli_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tmp_dir = root / ".paper-orchestra" / "tmp"
            tmp_dir.mkdir(parents=True)
            (tmp_dir / "omx-exec-cli.json").write_text("{}", encoding="utf-8")
            old_cwd = Path.cwd()
            stdout = io.StringIO()
            try:
                os.chdir(root)
                with contextlib.redirect_stdout(stdout):
                    code = cli_main(["cleanup-tmp"])
            finally:
                os.chdir(old_cwd)
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["removed_count"], 1)
            self.assertFalse((tmp_dir / "omx-exec-cli.json").exists())


class ReproducibilityAndParityTests(unittest.TestCase):
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

    def test_run_pipeline_records_prompt_traces_watermark_and_reproducibility(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            outputs = run_pipeline(root, provider=MockProvider(), discovery_mode="model", verify_mode="mock", refine_iterations=0, compile_paper=False)
            state = load_session(root)
            self.assertTrue(Path(state.artifacts.latest_prompt_trace_dir).exists())
            prompt_files = list(Path(state.artifacts.latest_prompt_trace_dir).glob('*.md'))
            self.assertTrue(any(path.name.endswith('.system.md') for path in prompt_files))
            self.assertTrue(any(path.name.endswith('.user.md') for path in prompt_files))
            self.assertTrue(Path(state.artifacts.latest_lane_summary_json).exists())
            self.assertTrue(Path(state.artifacts.latest_reproducibility_json).exists())
            repro = json.loads(Path(state.artifacts.latest_reproducibility_json).read_text(encoding='utf-8'))
            self.assertEqual(outputs['reproducibility_report'], state.artifacts.latest_reproducibility_json)
            self.assertEqual(repro['verdict'], 'BLOCK')
            self.assertIn('latest_provider_identity_json', repro['source_artifacts'])
            self.assertIn('latest_figure_placement_review_json', repro['source_artifacts'])
            self.assertIsNotNone(repro['source_artifacts']['latest_figure_placement_review_json'])
            self.assertIn('figure_placement_review', outputs)
            self.assertFalse(repro['generation_determinism']['byte_identical_generation_claimed'])
            self.assertTrue(repro['generation_determinism']['auditability_claimed'])
            paper_text = Path(state.artifacts.paper_full_tex).read_text(encoding='utf-8')
            self.assertIn('DO NOT DISTRIBUTE AS A FACTUAL DRAFT.', paper_text)

    def test_audit_reproducibility_cli_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(root, provider=MockProvider(), discovery_mode="model", verify_mode="mock", refine_iterations=0, compile_paper=False)
            old_cwd = Path.cwd()
            stdout = io.StringIO()
            try:
                os.chdir(root)
                with contextlib.redirect_stdout(stdout):
                    code = cli_main(["audit-reproducibility"])
            finally:
                os.chdir(old_cwd)
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertTrue(Path(payload['path']).exists())
            self.assertIn(payload['report']['verdict'], {'OK', 'WARN', 'BLOCK'})

    def test_audit_reproducibility_cli_can_require_live_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            seed_path = root / "refs.bib"
            seed_path.write_text(
                "@article{RFC9001,\n"
                "  title = {Using TLS to Secure QUIC},\n"
                "  author = {Martin Thomson and Sean Turner},\n"
                "  year = {2021}\n"
                "}\n",
                encoding="utf-8",
            )
            import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
            state = load_session(root)
            paper_path = Path(state.artifacts.paper_full_tex or artifact_path(root, "paper.full.tex"))
            paper_path.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\nSee prior work~\\cite{RFC9001}.\n\\end{document}\n",
                encoding="utf-8",
            )
            prompt_dir = artifact_path(root, "prompts/dummy.system.md").parent
            (prompt_dir / "outline.system.md").write_text("system", encoding="utf-8")
            (prompt_dir / "outline.user.md").write_text("user", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper_path)
            state.artifacts.latest_prompt_trace_dir = str(prompt_dir)
            state.latest_provider_name = "shell"
            state.latest_runtime_mode = "compatibility"
            save_session(root, state)

            old_cwd = Path.cwd()
            stdout = io.StringIO()
            try:
                os.chdir(root)
                with contextlib.redirect_stdout(stdout):
                    code = cli_main(["audit-reproducibility", "--require-live-verification"])
            finally:
                os.chdir(old_cwd)
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["report"]["verdict"], "BLOCK")
            self.assertTrue(payload["report"]["require_live_verification"])

    def test_doctor_report_includes_versions_and_reproducibility(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(root, provider=MockProvider(), discovery_mode="model", verify_mode="mock", refine_iterations=0, compile_paper=False)
            report = build_doctor_report(root)
            codes = {check['code'] for check in report['checks']}
            self.assertIn('omx_version', codes)
            self.assertIn('codex_version', codes)
            self.assertIn('papero_allow_tex_compile', codes)
            self.assertIn('current_session_reproducibility', codes)
            self.assertIn('disk_usage', report)

    def test_background_job_logs_include_stage_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            job = start_run_job(root, provider='mock', discovery_mode='model', verify_mode='mock', refine_iterations=0, compile_paper=False, runtime_mode='compatibility')
            for _ in range(100):
                status = get_job_status(root, job['job_id'])
                if status['status'] in {'succeeded', 'failed', 'cancelled'}:
                    break
                time.sleep(0.05)
            tail = tail_job_log(root, job['job_id'], lines=200)
            self.assertIn('"stage": "outline"', tail['tail'])
            self.assertIn('"stage": "pipeline"', tail['tail'])

    def test_mcp_and_docs_surface_include_reproducibility_and_parity_commands(self) -> None:
        tool_names = {tool['name'] for tool in MCP_TOOLS}
        self.assertIn('audit_reproducibility', tool_names)
        self.assertIn('audit_reproducibility', TOOL_HANDLERS)
        readme = Path('README.md').read_text(encoding='utf-8')
        skill = Path('skills/paperorchestra/SKILL.md').read_text(encoding='utf-8')
        self.assertIn('audit-reproducibility', readme)
        self.assertIn('ENVIRONMENT.md', readme)
        self.assertIn('paperorchestra environment', readme)
        self.assertNotIn('111 tests passing', readme)
        self.assertIn('teach', skill)
        self.assertIn('research_prior_work_seed', skill)
        self.assertIn('import_prior_work', skill)
        self.assertIn('critique', skill)
        self.assertIn('paperorchestra environment', skill)


class RalphCandidateWriteAtomicityTests(unittest.TestCase):
    def _init_session(self, root: Path) -> None:
        files = {
            "idea.md": "## Problem Statement\nDemo\n",
            "experimental_log.md": "# Experimental Log\n\n## 1. Experimental Setup\n* **Datasets:** DemoSet\n",
            "template.tex": "\\documentclass{article}\\begin{document}\\section{Intro}\\end{document}\n",
            "guidelines.md": "Target venue: DemoConf\n",
        }
        for name, content in files.items():
            (root / name).write_text(content, encoding="utf-8")
        (root / "figures").mkdir()
        create_session(
            root,
            InputBundle(
                idea_path=str(root / "idea.md"),
                experimental_log_path=str(root / "experimental_log.md"),
                template_path=str(root / "template.tex"),
                guidelines_path=str(root / "guidelines.md"),
                figures_dir=str(root / "figures"),
            ),
        )

    def test_pending_candidate_write_recovers_original_manuscript(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session(root)
            paper_path = root / "paper.full.tex"
            original = "\\documentclass{article}\\begin{document}original\\end{document}\n"
            candidate = "\\documentclass{article}\\begin{document}candidate\\end{document}\n"
            paper_path.write_text(original, encoding="utf-8")

            marker_path = guarded_replace_manuscript_text(
                root,
                paper_path,
                candidate,
                reason="unit_test_candidate",
                original_text=original,
            )

            self.assertEqual(paper_path.read_text(encoding="utf-8"), candidate)
            self.assertTrue(marker_path.exists())
            self.assertEqual(marker_path.name, MANUSCRIPT_CANDIDATE_WRITE_MARKER_FILENAME)
            recovery = recover_pending_manuscript_write(root)
            self.assertEqual(recovery["status"], "restored_original")
            self.assertEqual(paper_path.read_text(encoding="utf-8"), original)
            self.assertFalse(marker_path.exists())

    def test_failed_candidate_replace_leaves_original_and_recoverable_marker(self) -> None:
        from paperorchestra import ralph_bridge_state

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session(root)
            paper_path = root / "paper.full.tex"
            original = "\\documentclass{article}\\begin{document}original\\end{document}\n"
            candidate = "\\documentclass{article}\\begin{document}candidate\\end{document}\n"
            paper_path.write_text(original, encoding="utf-8")
            real_replace = ralph_bridge_state.os.replace
            calls = {"count": 0}

            def flaky_replace(src: str | Path, dst: str | Path) -> None:
                calls["count"] += 1
                if calls["count"] == 3:
                    raise RuntimeError("simulated destination replace crash")
                real_replace(src, dst)

            with patch("paperorchestra.ralph_bridge_state.os.replace", side_effect=flaky_replace):
                with self.assertRaisesRegex(RuntimeError, "simulated destination replace crash"):
                    guarded_replace_manuscript_text(
                        root,
                        paper_path,
                        candidate,
                        reason="unit_test_candidate",
                        original_text=original,
                    )

            marker_path = artifact_path(root, MANUSCRIPT_CANDIDATE_WRITE_MARKER_FILENAME)
            self.assertEqual(paper_path.read_text(encoding="utf-8"), original)
            self.assertTrue(marker_path.exists())
            recovery = recover_pending_manuscript_write(root)
            self.assertEqual(recovery["status"], "already_original")
            self.assertFalse(marker_path.exists())

    def test_ralph_active_manuscript_paths_do_not_use_truncating_write_text(self) -> None:
        for path in (Path("paperorchestra/ralph_bridge.py"), Path("paperorchestra/ralph_bridge_repair.py")):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("paper_path.write_text", source)


class DomainRegistrySemanticsTests(unittest.TestCase):
    def test_unknown_domain_env_fails_closed(self) -> None:
        with patch.dict(os.environ, {"PAPERO_DOMAIN": "not-a-real-domain"}):
            with self.assertRaisesRegex(ValueError, "Unknown PaperOrchestra domain profile"):
                get_domain()

    def test_register_domain_selects_external_profile_and_rejects_duplicates(self) -> None:
        name = f"unit_test_domain_{os.getpid()}_{int(time.time() * 1000)}"
        profile = replace(GENERIC, name=name)

        registered = register_domain(profile)

        self.assertIs(registered, profile)
        self.assertIn(name, available_domains())
        self.assertIs(get_domain(name.replace("_", "-")), profile)
        with patch.dict(os.environ, {"PAPERO_DOMAIN": name}):
            self.assertIs(get_domain(), profile)
            self.assertIs(detect_domain_for_text("text that should not auto-select another domain"), profile)
        with self.assertRaisesRegex(ValueError, "already registered"):
            register_domain(profile)

        replacement = replace(GENERIC, name=name, method_scope_tail=" Replacement domain profile.")
        self.assertIs(register_domain(replacement, replace=True), replacement)
        self.assertIs(get_domain(name), replacement)

    def test_domain_docs_and_environment_inventory_explain_plugin_lifecycle(self) -> None:
        inventory = build_environment_inventory()
        names = {
            variable["name"]
            for group in inventory["groups"]
            for variable in group.get("variables", [])
        }
        self.assertIn("PAPERO_DOMAIN", names)
        readme = Path("README.md").read_text(encoding="utf-8")
        environment = Path("ENVIRONMENT.md").read_text(encoding="utf-8")
        self.assertIn("register_domain", readme)
        self.assertIn("PAPERO_DOMAIN", readme)
        self.assertIn("register_domain", environment)
        self.assertIn("PAPERO_DOMAIN", environment)



if __name__ == "__main__":
    unittest.main()
