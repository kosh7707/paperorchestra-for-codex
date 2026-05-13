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
from paperorchestra.citation_integrity import build_rendered_reference_audit
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
            self.assertIn("--dangerously-bypass-approvals-and-sandbox", args)
            self.assertNotIn("--full-auto", args)
            self.assertEqual(args[-1], "-")
            self.assertNotIn(large_prompt, args)
            self.assertEqual(kwargs.get("input_text"), large_prompt)

            omx_exec_json_completion(large_prompt, {"type": "object", "properties": {}, "additionalProperties": False}, cwd=tmp)
            args, kwargs = calls[-1]
            self.assertIn("--dangerously-bypass-approvals-and-sandbox", args)
            self.assertNotIn("--full-auto", args)
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
            "ERROR: Selected model is at capacity. Please try a different model.",
            "The requested model gpt-5.5 is at capacity right now.",
            "ERROR: You've hit your usage limit. Visit settings or try again at 10:17 AM.",
            "429 rate limited by upstream provider",
            "Too many requests; retry later.",
            "quota exceeded for this billing window",
        ]
        negatives = [
            "model rejected request",
            "LaTeX compile failed",
            "Please try a different model.",
        ]
        for text in positives:
            self.assertTrue(is_retryable_transport_text(text), text)
        for text in negatives:
            self.assertFalse(is_retryable_transport_text(text), text)

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

    def test_quality_eval_rejects_process_residue_title_without_broad_word_ban(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n"
                "\\title{Artifact-Governed Drafting with Promotion-Time Validation}\n"
                "\\begin{document}\n"
                "\\maketitle\n"
                "\\section{Introduction}\n"
                "This paper studies a concrete technical system.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)

            _, quality_eval = write_quality_eval(root, quality_mode="claim_safe")

            self.assertIn("prompt_meta_leakage", quality_eval["non_reviewable"]["failing_codes"])
            markers = quality_eval["non_reviewable"]["checks"]["prompt_meta_leakage"]["markers"]
            self.assertTrue(any("artifact_governed_drafting" in marker for marker in markers))
            self.assertTrue(any("promotion_time_validation" in marker for marker in markers))

        benign = "Artifact validation is a normal term in reproducibility papers."
        self.assertFalse(_leakage_markers_in_text(benign, source="unit"))

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

    def test_import_prior_work_require_complete_metadata_filters_rendered_reference_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            seed_path = root / "prior_work.json"
            seed_path.write_text(
                json.dumps(
                    {
                        "references": [
                            {
                                "title": "Complete Metadata Reference",
                                "authors": ["Alice Example"],
                                "year": 2020,
                                "venue": "Example Venue",
                                "source": "codex_web_seed",
                            },
                            {
                                "title": "Organization Metadata Reference",
                                "organization": "Example Standards Group",
                                "year": 2021,
                                "venue": "Example Standard",
                                "source": "codex_web_seed",
                            },
                            {
                                "title": "Publication Date Without Year",
                                "authors": ["Date Only"],
                                "publication_date": "2022-01-01",
                                "venue": "Example Venue",
                                "source": "codex_web_seed",
                            },
                            {
                                "title": "Date Field Without Explicit Year",
                                "authors": ["Date Field"],
                                "date": "2022-01-01",
                                "venue": "Example Venue",
                                "source": "codex_web_seed",
                            },
                            {
                                "title": "Missing Year Reference",
                                "authors": ["No Year"],
                                "venue": "Example Venue",
                                "source": "codex_web_seed",
                            },
                            {
                                "title": "Unknown Author Reference",
                                "authors": ["Unknown"],
                                "year": 2022,
                                "venue": "Example Venue",
                                "source": "codex_web_seed",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            result = import_prior_work(
                root,
                seed_file=seed_path,
                source="codex_web_seed",
                require_complete_metadata=True,
            )
            citation_map = json.loads(Path(result["citation_map_json"]).read_text(encoding="utf-8"))
            references_bib = Path(result["references_bib"]).read_text(encoding="utf-8")
            rejection_report = json.loads(Path(result["rejection_report_json"]).read_text(encoding="utf-8"))

            self.assertEqual(rejection_report["accepted_entry_count"], 2)
            self.assertEqual(rejection_report["rejected_entry_count"], 4)
            self.assertEqual(
                rejection_report["reason_counts"],
                {"missing_year": 2, "missing_explicit_year": 1, "missing_author_or_organization": 1},
            )
            self.assertEqual(
                rejection_report["policy"]["publication_date_without_year"],
                "rejected_until_a_concrete_year_is_provided",
            )
            self.assertIn("Complete Metadata Reference", references_bib)
            self.assertIn("Organization Metadata Reference", references_bib)
            self.assertNotIn("Publication Date Without Year", references_bib)
            self.assertNotIn("Date Field Without Explicit Year", references_bib)
            self.assertNotIn("Unknown Author Reference", references_bib)
            self.assertNotIn("year = {},", references_bib)

            state = load_session(root)
            paper = artifact_path(root, "paper.full.tex")
            visible_keys = sorted(citation_map)
            paper.write_text("\\cite{" + ",".join(visible_keys) + "}\n", encoding="utf-8")
            bbl = artifact_path(root, "paper.full.bbl")
            bbl.write_text("\n".join(f"\\bibitem{{{key}}} {key}." for key in visible_keys), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)

            audit = build_rendered_reference_audit(root, quality_mode="claim_safe")
            self.assertEqual(audit["status"], "pass")
            self.assertNotIn("rendered_reference_unknown_metadata", audit["failing_codes"])

    def test_import_prior_work_require_complete_metadata_records_all_rejected_before_failing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            seed_path = root / "prior_work.json"
            seed_path.write_text(
                json.dumps(
                    {
                        "references": [
                            {
                                "title": "Incomplete Reference",
                                "authors": ["No Year"],
                                "publication_date": "2023-01-01",
                                "source": "codex_web_seed",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ContractError):
                import_prior_work(
                    root,
                    seed_file=seed_path,
                    source="codex_web_seed",
                    require_complete_metadata=True,
                )

            report_path = artifact_path(root, "prior_work_import_rejections.json")
            self.assertTrue(report_path.exists())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["input_entry_count"], 1)
            self.assertEqual(report["accepted_entry_count"], 0)
            self.assertEqual(report["rejected_entry_count"], 1)
            self.assertEqual(
                report["policy"]["all_rejected_behavior"],
                "fail_import_and_leave_existing_registry_unchanged",
            )
            state = load_session(root)
            self.assertIsNone(state.artifacts.citation_registry_json)

    def test_import_prior_work_require_complete_metadata_accepts_bibtex_editor_and_organization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            seed_path = root / "prior_work.bib"
            seed_path.write_text(
                "@techreport{OrgStandard,\n"
                "  title = {Organization Authored Standard},\n"
                "  organization = {Example Standards Group},\n"
                "  year = {2020},\n"
                "  url = {https://example.test/org-standard}\n"
                "}\n"
                "@proceedings{EditedVolume,\n"
                "  title = {Edited Benchmark Proceedings},\n"
                "  editor = {Edith Editor},\n"
                "  year = {2021},\n"
                "  url = {https://example.test/edited-volume}\n"
                "}\n",
                encoding="utf-8",
            )

            result = import_prior_work(
                root,
                seed_file=seed_path,
                source="manual_bibtex",
                require_complete_metadata=True,
            )

            report = json.loads(Path(result["rejection_report_json"]).read_text(encoding="utf-8"))
            references_bib = Path(result["references_bib"]).read_text(encoding="utf-8")
            self.assertEqual(report["accepted_entry_count"], 2)
            self.assertEqual(report["rejected_entry_count"], 0)
            self.assertIn("Example Standards Group", references_bib)
            self.assertIn("Edith Editor", references_bib)

    def test_research_prior_work_import_can_require_complete_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)

            result = generate_prior_work_seed(
                root,
                MockProvider(),
                import_seed=True,
                require_complete_metadata=True,
            )

            imported = result["imported"]
            self.assertIn("rejection_report_json", imported)
            report = json.loads(Path(imported["rejection_report_json"]).read_text(encoding="utf-8"))
            self.assertEqual(report["rejected_entry_count"], 0)
            self.assertTrue(Path(imported["references_bib"]).exists())

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

    def test_intro_related_can_persist_recoverable_citation_shortfall_for_supervised_loop(self) -> None:
        class PersistentCitationShortfallProvider(MockProvider):
            def __init__(self, keys: list[str]):
                self.keys = keys

            def complete(self, request: CompletionRequest) -> str:
                return (
                    "```latex\n"
                    "\\section{Introduction}\n"
                    f"Grounded framing \\\\cite{{{self.keys[0]}}}.\n"
                    "\\section{Related Work}\n"
                    f"Prior work comparison \\\\cite{{{self.keys[0]}}}.\n"
                    "```"
                )

        def prepare(root: Path) -> list[str]:
            self._init_session_with_minimal_inputs(root)
            generate_outline(root, MockProvider())
            discover_papers(root, MockProvider(), mode="model")
            verify_papers(root, mode="mock")
            build_bib(root)
            keys = [f"Ref{i}" for i in range(1, 21)]
            state = load_session(root)
            citation_map_path = Path(state.artifacts.citation_map_json or artifact_path(root, "citation_map.json"))
            citation_map_path.write_text(
                json.dumps({key: {"title": f"Verified reference {key}", "verified": True} for key in keys}),
                encoding="utf-8",
            )
            state.artifacts.citation_map_json = str(citation_map_path)
            save_session(root, state)
            plan_narrative_and_claims(root, MockProvider())
            return keys

        with tempfile.TemporaryDirectory() as strict_tmp:
            strict_root = Path(strict_tmp)
            keys = prepare(strict_root)
            with self.assertRaisesRegex(ContractError, "Insufficient citation coverage"):
                write_intro_related(strict_root, PersistentCitationShortfallProvider(keys))

        with tempfile.TemporaryDirectory() as tolerant_tmp:
            tolerant_root = Path(tolerant_tmp)
            keys = prepare(tolerant_root)
            path = write_intro_related(
                tolerant_root,
                PersistentCitationShortfallProvider(keys),
                allow_recoverable_contract_issues=True,
            )
            state = load_session(tolerant_root)
            validation = json.loads(Path(state.artifacts.latest_validation_json).read_text(encoding="utf-8"))
            lane_manifest = json.loads(
                (artifact_path(tolerant_root, "placeholder").parent / "lane-manifest.intro_related.json").read_text(
                    encoding="utf-8"
                )
            )

            self.assertTrue(Path(path).exists())
            self.assertEqual(state.artifacts.intro_related_tex, str(path))
            self.assertFalse(validation["ok"])
            self.assertIn("citation_coverage_insufficient", [issue["code"] for issue in validation["issues"]])
            self.assertTrue(
                any("supervised QA/operator loop" in note for note in lane_manifest.get("notes") or []),
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

    def test_cli_version_flag_is_available_before_subcommands(self) -> None:
        stdout = io.StringIO()
        with self.assertRaises(SystemExit) as raised:
            with contextlib.redirect_stdout(stdout):
                cli_main(["--version"])
        self.assertEqual(raised.exception.code, 0)
        self.assertIn("paperorchestra ", stdout.getvalue())

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

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = cli_main(["environment", "--summary"])
        self.assertEqual(code, 0)
        summary = stdout.getvalue()
        self.assertIn("PaperOrchestra environment summary", summary)
        self.assertIn("Readiness:", summary)
        self.assertIn("MCP:", summary)
        self.assertIn("active Codex session attachment: not checked", summary)
        self.assertIn("scripts/smoke-paperorchestra-mcp.py", summary)

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
        self.assertIn("exec", omx_retry["description"])
        self.assertNotIn("full-auto", omx_retry["description"])
        self.assertIn("never replayed", omx_retry["description"])

        guide = environment_guide_path().read_text(encoding="utf-8")
        readme = env_example_path().read_text(encoding="utf-8")
        combined = guide + "\n" + readme
        for phrase in [
            "retry-safe declaration plus reconnect/disconnect-like transport evidence",
            "plain timeouts are grace-only",
            "OMX exec is grace-only and never replayed",
            "state read --json",
            "single retry owner",
            "forces provider/OMX retry layers off",
            "Requires BOTH PAPERO_PROVIDER_RETRY_SAFE=1 AND PAPERO_PROVIDER_RETRY_ATTEMPTS>0",
            "PAPERO_CODEX_RETRY_JITTER_SECONDS",
            "PAPERO_SMOKE_STEP_RETRY_ATTEMPTS",
            "matching provider trace",
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
        tools_by_name = {tool["name"]: tool for tool in MCP_TOOLS}
        self.assertIn(
            "require_complete_metadata",
            tools_by_name["research_prior_work_seed"]["inputSchema"]["properties"],
        )
        self.assertIn(
            "require_complete_metadata",
            tools_by_name["import_prior_work"]["inputSchema"]["properties"],
        )


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
