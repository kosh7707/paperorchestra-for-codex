from __future__ import annotations

import argparse
from collections.abc import Callable, Iterator
from contextlib import contextmanager
import json
import os
import sys
from pathlib import Path

from paperorchestra.core.models import InputBundle
from paperorchestra.core.session import create_session, load_session
from paperorchestra.engine.pipeline import (
    compile_current_paper,
    import_prior_work,
    research_prior_work as generate_prior_work_seed,
    review_current_paper,
    run_pipeline,
    write_sections,
)
from paperorchestra.feedback.human_needed import record_human_needed_answer
from paperorchestra.interfaces.cli_output import (
    environment_summary_lines,
    print_orchestrator_payload,
    status_summary_lines,
)
from paperorchestra.interfaces.exporting import export_current_artifacts
from paperorchestra.loop_engine.quality.gate import write_quality_gate
from paperorchestra.loop_engine.quality.loop import write_quality_loop_plan
from paperorchestra.loop_engine.ralph.bridge import run_qa_loop_step
from paperorchestra.loop_engine.ralph.handoff import build_ralph_start_payload, launch_omx_ralph
from paperorchestra.manuscript.revisions import write_revision_suggestions
from paperorchestra.orchestra.controller import OrchestraOrchestrator, inspect_state as orchestrator_inspect_state
from paperorchestra.orchestra.evidence import write_orchestrator_evidence_bundle
from paperorchestra.orchestra.executor import LocalActionExecutor
from paperorchestra.orchestra.omx_executor import OmxActionExecutor
from paperorchestra.reviews.critic_trust import build_critic_trust_card, require_live_critic_trust
from paperorchestra.reviews.critics import write_citation_support_review, write_section_review
from paperorchestra.runtime.doctor import build_doctor_report, build_session_recovery_hint
from paperorchestra.runtime.environment import build_environment_inventory
from paperorchestra.runtime.providers import BaseProvider, get_citation_support_provider, get_provider


def _provider_from_args(args: argparse.Namespace) -> BaseProvider:
    return get_provider(args.provider, command=args.provider_command)


@contextmanager
def _strict_omx_env(enabled: bool) -> Iterator[None]:
    if not enabled:
        yield
        return
    previous = os.environ.get("PAPERO_STRICT_OMX_NATIVE")
    os.environ["PAPERO_STRICT_OMX_NATIVE"] = "1"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("PAPERO_STRICT_OMX_NATIVE", None)
        else:
            os.environ["PAPERO_STRICT_OMX_NATIVE"] = previous


def _make_omx_executor(cwd: Path, *, timeout_seconds: float = 30.0) -> OmxActionExecutor:
    return OmxActionExecutor(cwd=cwd, timeout_seconds=timeout_seconds)


CliHandler = Callable[[Path, argparse.Namespace], int]


def handle_cli_command(args: argparse.Namespace, *, cwd: Path, parser: argparse.ArgumentParser) -> int:
    handler = CLI_HANDLERS.get(args.command)
    if handler is None:
        parser.error(f"Unhandled command: {args.command}")
        return 2
    return handler(cwd, args)


def _handle_init(cwd: Path, args: argparse.Namespace) -> int:
    state = create_session(
        cwd,
        InputBundle(
            idea_path=str(Path(args.idea).resolve()),
            experimental_log_path=str(Path(args.experimental_log).resolve()),
            template_path=str(Path(args.template).resolve()),
            guidelines_path=str(Path(args.guidelines).resolve()),
            figures_dir=str(Path(args.figures_dir).resolve()) if args.figures_dir else None,
            cutoff_date=args.cutoff_date,
            venue=args.venue,
            page_limit=args.page_limit,
        ),
        allow_outside_workspace=args.allow_outside_workspace,
    )
    print(state.session_id)
    return 0


def _handle_status(cwd: Path, args: argparse.Namespace) -> int:
    state = load_session(cwd)
    payload = state.to_dict()
    payload["session_recovery"] = build_session_recovery_hint(cwd)
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    elif args.summary:
        print("\n".join(status_summary_lines(cwd, payload)))
    else:
        print(f"session_id: {payload['session_id']}")
        print(f"current_phase: {payload['current_phase']}")
        print(f"active_artifact: {payload['active_artifact']}")
        print(f"artifacts: {json.dumps(payload['artifacts'], indent=2, ensure_ascii=False)}")
    return 0


def _handle_inspect_state(cwd: Path, args: argparse.Namespace) -> int:
    state = orchestrator_inspect_state(cwd, material_path=args.material)
    print_orchestrator_payload(state.to_public_dict(), json_output=args.json)
    return 0


def _handle_orchestrate(cwd: Path, args: argparse.Namespace) -> int:
    orchestrator = OrchestraOrchestrator(cwd)
    if args.execute_local:
        result = orchestrator.step(material_path=args.material, execute=True, executor=LocalActionExecutor(material_path=args.material))
    elif args.plan_full_loop:
        result = orchestrator.plan_full_loop(material_path=args.material)
    elif args.execute_omx:
        result = orchestrator.execute_omx_once(material_path=args.material, executor=_make_omx_executor(cwd))
    else:
        result = orchestrator.run_until_blocked(material_path=args.material)
    payload = result.to_public_dict()
    if args.write_evidence:
        payload["evidence_bundle"] = write_orchestrator_evidence_bundle(cwd, result.state, output_dir=args.evidence_output)
    print_orchestrator_payload(payload, json_output=args.json)
    return 0


def _handle_answer_human_needed(cwd: Path, args: argparse.Namespace) -> int:
    provider = _provider_from_args(args) if args.apply else None
    with _strict_omx_env(args.strict_omx_native):
        payload = record_human_needed_answer(
            cwd,
            args.answer,
            packet_path=args.packet,
            review_scope=args.review_scope,
            intent=args.intent,
            action_id=args.action_id,
            output_answer=args.output_answer,
            output_feedback=args.output_feedback,
            redacted_answer_only=args.redacted_answer_only,
            apply=args.apply,
            imported_feedback_output=args.imported_feedback_output,
            provider=provider,
            max_supervised_iterations=args.max_supervised_iterations,
            require_compile=args.require_compile,
            quality_mode=args.quality_mode,
            max_iterations=args.max_iterations,
            require_live_verification=args.require_live_verification,
            accept_mixed_provenance=args.accept_mixed_provenance,
            runtime_mode=args.runtime_mode,
            citation_evidence_mode=args.citation_evidence_mode,
            citation_provider_name=args.citation_provider,
            citation_provider_command=args.citation_provider_command,
        )
    print_orchestrator_payload(payload, json_output=args.json)
    return 0


def _handle_export_current(cwd: Path, args: argparse.Namespace) -> int:
    payload = export_current_artifacts(cwd, args.output, include_all_artifacts=args.include_all_artifacts)
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"Exported PaperOrchestra outputs for session {payload['session_id']}")
        print(f"Output: {payload['output_dir']}")
        for item in payload["copied"]:
            print(f"  - {item['label']}: {item['destination']}")
    return 0


def _handle_research_prior_work(cwd: Path, args: argparse.Namespace) -> int:
    provider = _provider_from_args(args)
    with _strict_omx_env(args.strict_omx_native):
        payload = generate_prior_work_seed(
            cwd,
            provider,
            output=args.output,
            paper=args.paper,
            artifact_repo=args.artifact_repo,
            runtime_mode=args.runtime_mode,
            source=args.source,
            import_seed=args.import_seed,
            require_complete_metadata=args.require_complete_metadata,
        )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def _handle_import_prior_work(cwd: Path, args: argparse.Namespace) -> int:
    payload = import_prior_work(cwd, seed_file=args.seed_file, source=args.source, require_complete_metadata=args.require_complete_metadata)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def _handle_write_sections(cwd: Path, args: argparse.Namespace) -> int:
    provider = _provider_from_args(args)
    with _strict_omx_env(args.strict_omx_native):
        path = write_sections(
            cwd,
            provider,
            runtime_mode=args.runtime_mode,
            only_sections=args.only_sections,
            output_path=args.output_tex,
            claim_safe=args.claim_safe,
        )
    print(path)
    return 0


def _handle_compile(cwd: Path, args: argparse.Namespace) -> int:
    print(compile_current_paper(cwd))
    return 0


def _handle_environment(cwd: Path, args: argparse.Namespace) -> int:
    inventory = build_environment_inventory()
    doctor = build_doctor_report(cwd)
    payload = {
        **inventory,
        "readiness_profiles": doctor["readiness_profiles"],
        "paperorchestra_mcp_health": doctor.get("paperorchestra_mcp_health"),
        "next_steps": ["paperorchestra doctor"],
    }
    if args.summary:
        print("\n".join(environment_summary_lines(payload)))
    else:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def _handle_doctor(cwd: Path, args: argparse.Namespace) -> int:
    payload = build_doctor_report(cwd, omx_deep=args.omx_deep, omx_timeout=args.omx_timeout)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def _handle_critique(cwd: Path, args: argparse.Namespace) -> int:
    trust_card = build_critic_trust_card(
        provider_name=args.provider,
        provider_command=args.provider_command,
        citation_evidence_mode=args.citation_evidence_mode,
        claim_safe=args.claim_safe,
    )
    if args.live:
        require_live_critic_trust(trust_card)
    provider = _provider_from_args(args)
    state = load_session(cwd)
    output_dir = Path(args.output_dir).resolve() if args.output_dir else Path(state.artifacts.paper_full_tex or state.inputs.idea_path).resolve().parent
    output_dir.mkdir(parents=True, exist_ok=True)
    with _strict_omx_env(args.strict_omx_native):
        review_path = review_current_paper(cwd, provider, runtime_mode=args.runtime_mode)
    section_path = write_section_review(cwd, output_dir / "section_review.json")
    citation_provider = get_citation_support_provider(args.provider, command=args.provider_command, evidence_mode=args.citation_evidence_mode)
    citation_path = write_citation_support_review(
        cwd,
        output_dir / "citation_support_review.json",
        provider=citation_provider,
        evidence_mode=args.citation_evidence_mode,
        progress_stream=sys.stderr if args.citation_evidence_mode in {"model", "web"} else None,
    )
    source_paper = args.source_paper or state.artifacts.paper_full_tex
    suggestions_path = write_revision_suggestions(
        source_paper,
        review_path,
        output_dir / "revision_suggestions.json",
        section_review_json=section_path,
        citation_review_json=citation_path,
    )
    print(
        json.dumps(
            {
                "critic_trust": trust_card,
                "review": str(review_path),
                "section_review": str(section_path),
                "citation_support_review": str(citation_path),
                "revision_suggestions": str(suggestions_path),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def _handle_quality_gate(cwd: Path, args: argparse.Namespace) -> int:
    provider = _provider_from_args(args) if args.auto_refine else None
    with _strict_omx_env(args.strict_omx_native):
        path, payload = write_quality_gate(
            cwd,
            Path(args.output).resolve() if args.output else None,
            plan_output_path=Path(args.plan_output).resolve() if args.plan_output else None,
            profile=args.profile,
            quality_mode=args.quality_mode,
            require_live_verification=args.require_live_verification,
            accept_mixed_provenance=args.accept_mixed_provenance,
            max_iterations=args.max_iterations,
            auto_refine=args.auto_refine,
            provider=provider,
            refine_iterations=args.refine_iterations,
            runtime_mode=args.runtime_mode,
            require_compile_for_accept=args.require_compile_for_accept,
        )
    print(json.dumps({"path": str(path), "quality_gate": payload}, indent=2, ensure_ascii=False))
    return 10 if payload.get("decision", {}).get("blocked") and not args.no_fail_on_block else 0


def _handle_qa_loop(cwd: Path, args: argparse.Namespace) -> int:
    path, payload = write_quality_loop_plan(
        cwd,
        Path(args.output).resolve() if args.output else None,
        require_live_verification=args.require_live_verification,
        quality_mode=args.quality_mode,
        max_iterations=args.max_iterations,
        accept_mixed_provenance=args.accept_mixed_provenance,
        quality_eval_input_path=args.quality_eval,
    )
    print(json.dumps({"path": str(path), "plan": payload}, indent=2, ensure_ascii=False))
    return 0


def _handle_qa_loop_step(cwd: Path, args: argparse.Namespace) -> int:
    provider = _provider_from_args(args)
    with _strict_omx_env(args.strict_omx_native):
        result = run_qa_loop_step(
            cwd,
            provider,
            quality_mode=args.quality_mode,
            max_iterations=args.max_iterations,
            require_live_verification=args.require_live_verification,
            accept_mixed_provenance=args.accept_mixed_provenance,
            runtime_mode=args.runtime_mode,
            require_compile=args.require_compile,
            citation_evidence_mode=args.citation_evidence_mode,
            citation_provider_name=args.citation_provider,
            citation_provider_command=args.citation_provider_command,
            quality_eval_input_path=args.quality_eval,
            qa_loop_plan_input_path=args.plan,
            citation_support_review_path=args.citation_support_review,
        )
    print(json.dumps({"path": str(result.path), "execution": result.payload}, indent=2, ensure_ascii=False))
    return result.exit_code


def _handle_ralph_start(cwd: Path, args: argparse.Namespace) -> int:
    payload = build_ralph_start_payload(
        cwd,
        quality_mode=args.quality_mode,
        max_iterations=args.max_iterations,
        output_path=Path(args.output).resolve() if args.output else None,
        require_live_verification=args.require_live_verification,
        accept_mixed_provenance=args.accept_mixed_provenance,
        evidence_root=args.evidence_root,
    )
    if args.launch:
        proc = launch_omx_ralph(payload["argv"], cwd=cwd)
        payload["launch"] = {"pid": proc.pid, "status": "started"}
    else:
        payload["launch"] = {"status": "dry_run"}
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def _handle_run(cwd: Path, args: argparse.Namespace) -> int:
    provider = _provider_from_args(args)
    with _strict_omx_env(args.strict_omx_native):
        result = run_pipeline(
            cwd,
            provider=provider,
            discovery_mode=args.discovery_mode,
            verify_mode=args.verify_mode,
            verify_error_policy=args.verify_error_policy,
            verify_fallback_mode=args.verify_fallback_mode,
            require_live_verification=args.require_live_verification,
            refine_iterations=args.refine_iterations,
            compile_paper=args.compile,
            runtime_mode=args.runtime_mode,
        )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if result.get("status") == "blocked" else 0


CLI_HANDLERS: dict[str, CliHandler] = {
    "init": _handle_init,
    "status": _handle_status,
    "inspect-state": _handle_inspect_state,
    "orchestrate": _handle_orchestrate,
    "answer-human-needed": _handle_answer_human_needed,
    "export-current": _handle_export_current,
    "research-prior-work": _handle_research_prior_work,
    "import-prior-work": _handle_import_prior_work,
    "write-sections": _handle_write_sections,
    "compile": _handle_compile,
    "environment": _handle_environment,
    "doctor": _handle_doctor,
    "critique": _handle_critique,
    "quality-gate": _handle_quality_gate,
    "qa-loop": _handle_qa_loop,
    "qa-loop-step": _handle_qa_loop_step,
    "ralph-start": _handle_ralph_start,
    "run": _handle_run,
}
