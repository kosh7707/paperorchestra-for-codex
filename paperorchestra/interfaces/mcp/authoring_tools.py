from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from paperorchestra.core.io import write_json
from paperorchestra.core.session import load_session
from paperorchestra.engine.authoring_round import run_authoring_round
from paperorchestra.engine.pipeline import run_pipeline
from paperorchestra.engine.research_prior_work_stage import import_prior_work, research_prior_work as generate_prior_work_seed
from paperorchestra.engine.review_stages import compile_current_paper, review_current_paper
from paperorchestra.engine.section_writing_stage import write_sections
from paperorchestra.engine.current_manuscript_stages import write_page_layout_review
from paperorchestra.feedback.human_needed import record_human_needed_answer
from paperorchestra.interfaces.exporting import export_current_artifacts
from paperorchestra.interfaces.mcp.common import JSON, default_cwd, ok, provider_from_args
from paperorchestra.manuscript.revisions import write_revision_suggestions
from paperorchestra.reviews.citation_model_writer import write_citation_support_review
from paperorchestra.reviews.section_review import write_section_review
from paperorchestra.runtime.provider_registry import get_citation_support_provider


def tool_research_prior_work(arguments: JSON) -> JSON:
    cwd = default_cwd(arguments)
    return ok(
        generate_prior_work_seed(
            cwd,
            provider_from_args(arguments),
            output=arguments.get("output"),
            paper=arguments.get("paper"),
            artifact_repo=arguments.get("artifact_repo"),
            runtime_mode=arguments.get("runtime_mode", "compatibility"),
            source=arguments.get("source", "codex_web_seed"),
            import_seed=bool(arguments.get("import_seed", False)),
            require_complete_metadata=bool(arguments.get("require_complete_metadata", False)),
        )
    )


def tool_import_prior_work(arguments: JSON) -> JSON:
    return ok(
        import_prior_work(
            default_cwd(arguments),
            seed_file=arguments["seed_file"],
            source=arguments.get("source", "manual_seed"),
            require_complete_metadata=bool(arguments.get("require_complete_metadata", False)),
        )
    )


def tool_authoring_round(arguments: JSON) -> JSON:
    cwd = default_cwd(arguments)
    provider_name = arguments.get("provider", "mock")
    evidence_mode = arguments.get("citation_evidence_mode") or ("heuristic" if provider_name == "mock" else "web")
    provider_command = arguments.get("provider_command")
    if _should_background_authoring_round(arguments):
        return ok(_start_background_authoring_round(cwd, arguments, evidence_mode=evidence_mode))
    return ok(
        run_authoring_round(
            cwd,
            provider_from_args(arguments),
            round_dir=arguments.get("round_dir"),
            runtime_mode=arguments.get("runtime_mode", "compatibility"),
            only_sections=arguments.get("only_sections"),
            output_path=arguments.get("output_path"),
            claim_safe=bool(arguments.get("claim_safe", False)),
            bypass_plan_gate=bool(arguments.get("bypass_plan_gate", False)),
            run_literature=not bool(arguments.get("skip_literature", False)),
            import_literature_seed=not bool(arguments.get("no_import_literature", False)),
            require_complete_metadata=bool(arguments.get("require_complete_metadata", False)),
            require_web_research=bool(arguments.get("require_web_research", False)),
            run_critic=not bool(arguments.get("skip_critic", False)),
            require_live_critic=bool(arguments.get("require_live_critic", False)),
            compile_paper=bool(arguments.get("compile_paper", False)),
            citation_evidence_mode=evidence_mode,
            citation_provider_name=arguments.get("citation_provider"),
            citation_provider_command=arguments.get("citation_provider_command"),
            provider_name=provider_name,
            provider_command=provider_command,
        )
    )


def _should_background_authoring_round(arguments: JSON) -> bool:
    if "background" in arguments:
        return bool(arguments.get("background"))
    return bool(arguments.get("require_web_research") or arguments.get("require_live_critic"))


def _start_background_authoring_round(cwd: Path, arguments: JSON, *, evidence_mode: str) -> JSON:
    job_dir = Path(arguments.get("background_dir") or cwd / ".paper-orchestra" / "mcp-jobs").resolve()
    job_dir.mkdir(parents=True, exist_ok=True)
    job_id = f"authoring-round-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    stdout_path = job_dir / f"{job_id}.stdout.json"
    stderr_path = job_dir / f"{job_id}.stderr.log"
    meta_path = job_dir / f"{job_id}.json"
    argv = _authoring_round_cli_argv(arguments, evidence_mode=evidence_mode)
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
        proc = subprocess.Popen(
            argv,
            cwd=cwd,
            stdout=stdout,
            stderr=stderr,
            text=True,
            start_new_session=True,
            env=env,
        )
    _reap_background_process(proc)
    payload = {
        "status": "started",
        "mode": "background",
        "job_id": job_id,
        "pid": proc.pid,
        "cwd": str(cwd),
        "command": argv,
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "metadata": str(meta_path),
        "poll": {
            "status": f"paperorchestra status --json  # cwd={cwd}",
            "tail_stderr": f"tail -f {stderr_path}",
            "read_stdout_when_done": str(stdout_path),
        },
        "reason": "Live/web authoring rounds can exceed the MCP client tools/call timeout, so the MCP tool started a detached job and returned immediately.",
    }
    write_json(meta_path, payload)
    return payload


def _reap_background_process(proc: subprocess.Popen[str]) -> None:
    def wait_for_exit() -> None:
        proc.wait()

    threading.Thread(target=wait_for_exit, name=f"paperorchestra-mcp-job-{proc.pid}", daemon=True).start()


def _authoring_round_cli_argv(arguments: JSON, *, evidence_mode: str) -> list[str]:
    argv = [sys.executable, "-m", "paperorchestra.cli", "authoring-round"]
    _append_option(argv, "--round-dir", arguments.get("round_dir"))
    _append_option(argv, "--only-sections", _string_or_joined(arguments.get("only_sections")))
    _append_option(argv, "--output-tex", arguments.get("output_path"))
    _append_flag(argv, "--claim-safe", arguments.get("claim_safe"))
    _append_flag(argv, "--bypass-plan-gate", arguments.get("bypass_plan_gate"))
    _append_flag(argv, "--skip-literature", arguments.get("skip_literature"))
    _append_flag(argv, "--no-import-literature", arguments.get("no_import_literature"))
    _append_flag(argv, "--require-complete-metadata", arguments.get("require_complete_metadata"))
    _append_flag(argv, "--require-web-research", arguments.get("require_web_research"))
    _append_flag(argv, "--skip-critic", arguments.get("skip_critic"))
    _append_flag(argv, "--require-live-critic", arguments.get("require_live_critic"))
    _append_flag(argv, "--compile", arguments.get("compile_paper"))
    _append_option(argv, "--citation-evidence-mode", evidence_mode)
    _append_option(argv, "--runtime-mode", arguments.get("runtime_mode"))
    _append_flag(argv, "--strict-omx-native", arguments.get("strict_omx_native"))
    _append_option(argv, "--provider", arguments.get("provider"))
    _append_option(argv, "--provider-command", arguments.get("provider_command"))
    _append_option(argv, "--citation-provider", arguments.get("citation_provider"))
    _append_option(argv, "--citation-provider-command", arguments.get("citation_provider_command"))
    return argv


def _append_option(argv: list[str], flag: str, value: object | None) -> None:
    if value not in {None, ""}:
        argv.extend([flag, str(value)])


def _append_flag(argv: list[str], flag: str, enabled: object | None) -> None:
    if bool(enabled):
        argv.append(flag)


def _string_or_joined(value: object | None) -> str | None:
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    if value in {None, ""}:
        return None
    return str(value)


def tool_write_sections(arguments: JSON) -> JSON:
    cwd = default_cwd(arguments)
    return ok(
        {
            "path": str(
                write_sections(
                    cwd,
                    provider_from_args(arguments),
                    runtime_mode=arguments.get("runtime_mode", "compatibility"),
                    only_sections=arguments.get("only_sections"),
                    output_path=arguments.get("output_path"),
                    claim_safe=bool(arguments.get("claim_safe", False)),
                    bypass_plan_gate=bool(arguments.get("bypass_plan_gate", False)),
                )
            )
        }
    )


def tool_critique(arguments: JSON) -> JSON:
    cwd = default_cwd(arguments)
    provider = provider_from_args(arguments)
    state = load_session(cwd)
    output_dir = Path(arguments["output_dir"]).resolve() if arguments.get("output_dir") else Path(state.artifacts.paper_full_tex or state.inputs.idea_path).resolve().parent
    output_dir.mkdir(parents=True, exist_ok=True)
    review_path = review_current_paper(cwd, provider, runtime_mode=arguments.get("runtime_mode", "compatibility"))
    section_path = write_section_review(cwd, output_dir / "section_review.json")
    evidence_mode = arguments.get("citation_evidence_mode") or "heuristic"
    citation_provider = get_citation_support_provider(arguments.get("provider", "mock"), command=arguments.get("provider_command"), evidence_mode=evidence_mode)
    citation_path = write_citation_support_review(cwd, output_dir / "citation_support_review.json", provider=citation_provider, evidence_mode=evidence_mode)
    suggestions_path = write_revision_suggestions(
        arguments.get("source_paper") or state.artifacts.paper_full_tex,
        review_path,
        output_dir / "revision_suggestions.json",
        section_review_json=section_path,
        citation_review_json=citation_path,
    )
    return ok({"review": str(review_path), "section_review": str(section_path), "citation_support_review": str(citation_path), "revision_suggestions": str(suggestions_path)})


def tool_visual_audit(arguments: JSON) -> JSON:
    path, payload = write_page_layout_review(
        default_cwd(arguments),
        pdf_path=arguments.get("pdf"),
        output_path=arguments.get("output"),
        render_dir=arguments.get("render_dir"),
        findings_json=arguments.get("findings_json"),
    )
    return ok(
        {
            "path": str(path),
            "status": payload.get("status"),
            "failing_codes": payload.get("failing_codes", []),
            "warning_codes": payload.get("warning_codes", []),
            "rendered_pages": payload.get("rendered_pages", []),
            "contact_sheets": payload.get("contact_sheets", {}),
            "repair_candidate_count": len(payload.get("repair_candidates") or []),
        }
    )


def tool_compile_current_paper(arguments: JSON) -> JSON:
    return ok({"path": str(compile_current_paper(default_cwd(arguments)))})


def tool_answer_human_needed(arguments: JSON) -> JSON:
    provider = provider_from_args(arguments) if arguments.get("apply") else None
    payload = record_human_needed_answer(
        default_cwd(arguments),
        str(arguments.get("answer") or ""),
        packet_path=arguments.get("packet_path"),
        review_scope=arguments.get("review_scope"),
        intent=arguments.get("intent"),
        action_id=arguments.get("action_id"),
        output_answer=arguments.get("output_answer"),
        output_feedback=arguments.get("output_feedback"),
        redacted_answer_only=bool(arguments.get("redacted_answer_only", False)),
        apply=bool(arguments.get("apply", False)),
        imported_feedback_output=arguments.get("imported_feedback_output"),
        provider=provider,
        max_supervised_iterations=int(arguments.get("max_supervised_iterations", 1)),
        require_compile=bool(arguments.get("require_compile", False)),
        quality_mode=arguments.get("quality_mode", "claim_safe"),
        max_iterations=int(arguments.get("max_iterations", 10)),
        require_live_verification=bool(arguments.get("require_live_verification", False)),
        accept_mixed_provenance=bool(arguments.get("accept_mixed_provenance", False)),
        runtime_mode=arguments.get("runtime_mode", "compatibility"),
        citation_evidence_mode=arguments.get("citation_evidence_mode", "web"),
        citation_provider_name=arguments.get("citation_provider"),
        citation_provider_command=arguments.get("citation_provider_command"),
    )
    return ok(payload)


def tool_export_current(arguments: JSON) -> JSON:
    return ok(export_current_artifacts(default_cwd(arguments), arguments["output"], include_all_artifacts=bool(arguments.get("include_all_artifacts", False))))


def tool_run_pipeline(arguments: JSON) -> JSON:
    cwd = default_cwd(arguments)
    return ok(
        run_pipeline(
            cwd,
            provider=provider_from_args(arguments),
            discovery_mode=arguments.get("discovery_mode", "model"),
            verify_mode=arguments.get("verify_mode", "live"),
            verify_error_policy=arguments.get("verify_error_policy", "skip"),
            verify_fallback_mode=arguments.get("verify_fallback_mode", "none"),
            require_live_verification=bool(arguments.get("require_live_verification", False)),
            refine_iterations=int(arguments.get("refine_iterations", 1)),
            compile_paper=bool(arguments.get("compile_paper", False)),
            runtime_mode=arguments.get("runtime_mode", "compatibility"),
            bypass_plan_gate=bool(arguments.get("bypass_plan_gate", False)),
        )
    )
