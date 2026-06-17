from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
import sys
from pathlib import Path

from .critic_trust import build_critic_trust_card, require_live_critic_trust
from .critics import write_citation_support_review, write_section_review
from .doctor import build_doctor_report, build_session_recovery_hint
from .environment import build_environment_inventory
from .exporting import export_current_artifacts
from .human_needed import record_human_needed_answer
from .cli_parser import build_parser
from .models import InputBundle
from .orchestra_evidence import write_orchestrator_evidence_bundle
from .orchestra_executor import LocalActionExecutor
from .orchestra_omx_executor import OmxActionExecutor
from .orchestra_scorecard import render_scorecard_summary
from .orchestrator import OrchestraOrchestrator, inspect_state as orchestrator_inspect_state
from .pipeline import (
    compile_current_paper,
    import_prior_work,
    research_prior_work as generate_prior_work_seed,
    review_current_paper,
    run_pipeline,
    write_sections,
)
from .providers import get_citation_support_provider, get_provider
from .loop_engine.quality.gate import write_quality_gate
from .loop_engine.quality.loop import write_quality_loop_plan
from .loop_engine.ralph.bridge import build_ralph_start_payload, launch_omx_ralph, run_qa_loop_step
from .revisions import write_revision_suggestions
from .session import create_session, load_session, run_dir


def _provider_from_args(args: argparse.Namespace):
    return get_provider(args.provider, command=args.provider_command)


@contextmanager
def _strict_omx_env(enabled: bool):
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


def _path_or_missing(value: str | None) -> str:
    return value if value else "missing"


def _status_summary_lines(cwd: Path, payload: dict[str, object]) -> list[str]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict):
        artifacts = {}
    recovery = payload.get("session_recovery")
    if not isinstance(recovery, dict):
        recovery = {}
    artifact_dir = (
        Path(str(artifacts.get("paper_full_tex"))).resolve().parent
        if artifacts.get("paper_full_tex")
        else run_dir(cwd, str(payload["session_id"])) / "artifacts"
    )
    lines = [
        f"Session: {payload['session_id']}",
        f"Phase: {payload['current_phase']}",
        "",
        "Main files:",
        f"  TeX: {_path_or_missing(artifacts.get('paper_full_tex'))}",
        f"  PDF: {_path_or_missing(artifacts.get('compiled_pdf'))}",
        f"  Review: {_path_or_missing(artifacts.get('latest_review_json'))}",
        f"  Artifact directory: {artifact_dir}",
        "",
        "Next:",
    ]
    next_commands = recovery.get("next_commands")
    if isinstance(next_commands, list) and next_commands:
        lines.extend(f"  {command}" for command in next_commands)
    elif not artifacts.get("compiled_pdf"):
        lines.extend(["  paperorchestra environment --summary", "  PAPERO_ALLOW_TEX_COMPILE=1 paperorchestra compile"])
    else:
        lines.append("  paperorchestra export-current --output ./paperorchestra-output")
    return lines


def _ok_warn(value: bool) -> str:
    return "OK" if value else "WARN"


def _environment_summary_lines(payload: dict[str, object]) -> list[str]:
    package_context = payload.get("package_context") if isinstance(payload.get("package_context"), dict) else {}
    profiles = payload.get("readiness_profiles") if isinstance(payload.get("readiness_profiles"), list) else []
    mcp_health = payload.get("paperorchestra_mcp_health") if isinstance(payload.get("paperorchestra_mcp_health"), dict) else {}
    mcp_config = mcp_health.get("config") if isinstance(mcp_health.get("config"), dict) else {}
    mcp_server = mcp_health.get("server") if isinstance(mcp_health.get("server"), dict) else {}
    mcp_attachment = mcp_health.get("active_session_attachment") if isinstance(mcp_health.get("active_session_attachment"), dict) else {}

    lines = [
        "PaperOrchestra environment summary",
        "",
        "Package:",
        f"  Python: {package_context.get('python_executable', 'unknown')}",
        f"  Package root: {package_context.get('package_root', 'unknown')}",
        "",
        "Readiness:",
    ]
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        ready = bool(profile.get("ready"))
        lines.append(f"  {_ok_warn(ready)} {profile.get('name')}: {profile.get('status')}")
        missing = profile.get("missing")
        if isinstance(missing, list) and missing:
            lines.append(f"    missing: {'; '.join(str(item) for item in missing[:2])}")
    lines.extend(
        [
            "",
            "MCP:",
            f"  {_ok_warn(bool(mcp_config.get('registered')))} config registered: {mcp_config.get('registered', False)}",
            f"  {_ok_warn(bool(mcp_server.get('ok')))} stdio server health: {mcp_server.get('ok', False)}",
            f"  active Codex session attachment: not checked ({mcp_attachment.get('detail', 'cannot be verified from CLI')})",
            "",
            "Next:",
            "  paperorchestra status --summary",
            "  paperorchestra doctor",
        ]
    )
    return lines


def _orchestrator_summary_lines(payload: dict[str, object]) -> list[str]:
    actions = payload.get("next_actions") if isinstance(payload.get("next_actions"), list) else []
    readiness = payload.get("readiness") if isinstance(payload.get("readiness"), dict) else {}
    scorecard = payload.get("scorecard_summary") if isinstance(payload.get("scorecard_summary"), dict) else {}
    first_action = actions[0].get("action_type") if actions and isinstance(actions[0], dict) else "none"
    return [
        "PaperOrchestra orchestrator state",
        render_scorecard_summary(scorecard) if scorecard else "Score: unscored",
        f"Readiness: {readiness.get('label', 'unknown')}",
        f"Next action: {first_action}",
    ]


def _print_orchestrator_payload(payload: dict[str, object], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    state_payload = payload.get("state") if isinstance(payload.get("state"), dict) else payload
    lines: list[str] = []
    if isinstance(payload.get("execution_record"), dict):
        execution_record = payload["execution_record"]
        lines.extend(
            [
                f"Execution: {payload.get('execution', 'unknown')}",
                f"Action taken: {payload.get('action_taken', 'none')}",
                f"Execution status: {execution_record.get('status', 'unknown')}",
                f"Adapter: {execution_record.get('adapter', 'unknown')}",
                f"Reason: {execution_record.get('reason', 'unknown')}",
                f"State rebuild required: {execution_record.get('state_rebuild_required', 'unknown')}",
                "",
            ]
        )
    lines.extend(_orchestrator_summary_lines(state_payload))
    print("\n".join(lines))


def _make_omx_executor(cwd: Path, *, timeout_seconds: float = 30.0) -> OmxActionExecutor:
    return OmxActionExecutor(cwd=cwd, timeout_seconds=timeout_seconds)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cwd = Path.cwd()

    try:
        if args.command == "init":
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

        if args.command == "status":
            state = load_session(cwd)
            payload = state.to_dict()
            payload["session_recovery"] = build_session_recovery_hint(cwd)
            if args.json:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            elif args.summary:
                print("\n".join(_status_summary_lines(cwd, payload)))
            else:
                print(f"session_id: {payload['session_id']}")
                print(f"current_phase: {payload['current_phase']}")
                print(f"active_artifact: {payload['active_artifact']}")
                print(f"artifacts: {json.dumps(payload['artifacts'], indent=2, ensure_ascii=False)}")
            return 0

        if args.command == "inspect-state":
            state = orchestrator_inspect_state(cwd, material_path=args.material)
            _print_orchestrator_payload(state.to_public_dict(), json_output=args.json)
            return 0

        if args.command == "orchestrate":
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
            _print_orchestrator_payload(payload, json_output=args.json)
            return 0


        if args.command == "answer-human-needed":
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
            _print_orchestrator_payload(payload, json_output=args.json)
            return 0

        if args.command == "export-current":
            payload = export_current_artifacts(cwd, args.output, include_all_artifacts=args.include_all_artifacts)
            if args.json:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                print(f"Exported PaperOrchestra outputs for session {payload['session_id']}")
                print(f"Output: {payload['output_dir']}")
                for item in payload["copied"]:
                    print(f"  - {item['label']}: {item['destination']}")
            return 0

        if args.command == "research-prior-work":
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

        if args.command == "import-prior-work":
            payload = import_prior_work(cwd, seed_file=args.seed_file, source=args.source, require_complete_metadata=args.require_complete_metadata)
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return 0

        if args.command == "write-sections":
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

        if args.command == "compile":
            print(compile_current_paper(cwd))
            return 0

        if args.command == "environment":
            inventory = build_environment_inventory()
            doctor = build_doctor_report(cwd)
            payload = {
                **inventory,
                "readiness_profiles": doctor["readiness_profiles"],
                "paperorchestra_mcp_health": doctor.get("paperorchestra_mcp_health"),
                "next_steps": ["paperorchestra doctor"],
            }
            if args.summary:
                print("\n".join(_environment_summary_lines(payload)))
            else:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            return 0

        if args.command == "doctor":
            payload = build_doctor_report(cwd, omx_deep=args.omx_deep, omx_timeout=args.omx_timeout)
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return 0

        if args.command == "critique":
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
            print(json.dumps({
                "critic_trust": trust_card,
                "review": str(review_path),
                "section_review": str(section_path),
                "citation_support_review": str(citation_path),
                "revision_suggestions": str(suggestions_path),
            }, indent=2, ensure_ascii=False))
            return 0

        if args.command == "quality-gate":
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

        if args.command == "qa-loop":
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

        if args.command == "qa-loop-step":
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

        if args.command == "ralph-start":
            if args.dry_run and args.launch:
                parser.error("ralph-start accepts either --dry-run or --launch, not both")
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

        if args.command == "run":
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

        parser.error(f"Unhandled command: {args.command}")
        return 2
    except Exception as exc:  # pragma: no cover - CLI boundary
        print(f"error: {exc}", file=sys.stderr)
        if getattr(args, "strict_omx_native", False) and "Strict OMX-native mode forbids fallback" in str(exc):
            return 2
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
