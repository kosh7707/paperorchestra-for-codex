from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
import shutil
import sys
from pathlib import Path

from . import __version__
from .critic_trust import build_critic_trust_card, require_live_critic_trust
from .critics import write_citation_support_review, write_section_review
from .doctor import build_doctor_report, build_session_recovery_hint
from .environment import build_environment_inventory
from .human_needed import record_human_needed_answer
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
from .quality_gate import write_quality_gate
from .quality_loop import write_quality_loop_plan
from .ralph_bridge import build_ralph_start_payload, launch_omx_ralph, run_qa_loop_step
from .revisions import write_revision_suggestions
from .session import artifact_path, create_session, load_session, run_dir


def _common_provider_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--provider", default="shell", choices=["shell", "mock"])
    parser.add_argument("--provider-command", default=None)


def _citation_provider_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--citation-provider", default=None, choices=["shell", "mock"])
    parser.add_argument("--citation-provider-command", default=None)


def _runtime_mode_args(parser: argparse.ArgumentParser, *, strict_flag: bool = False) -> None:
    parser.add_argument("--runtime-mode", default="compatibility", choices=["compatibility", "omx_native"])
    if strict_flag:
        parser.add_argument("--strict-omx-native", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paperorchestra",
        description="PaperOrchestra CLI: status, research, critic review, authoring, QA loop, and OMX handoff.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    init_parser = sub.add_parser("init", help="Initialize a PaperOrchestra session")
    init_parser.add_argument("--idea", required=True)
    init_parser.add_argument("--experimental-log", required=True)
    init_parser.add_argument("--template", required=True)
    init_parser.add_argument("--guidelines", required=True)
    init_parser.add_argument("--figures-dir")
    init_parser.add_argument("--cutoff-date")
    init_parser.add_argument("--venue")
    init_parser.add_argument("--page-limit", type=int)
    init_parser.add_argument("--allow-outside-workspace", action="store_true")

    status_parser = sub.add_parser("status", help="Show current session state")
    status_parser.add_argument("--json", action="store_true")
    status_parser.add_argument("--summary", action="store_true")

    inspect_state_parser = sub.add_parser("inspect-state", help="Inspect material readiness and the next orchestration action")
    inspect_state_parser.add_argument("--material")
    inspect_state_parser.add_argument("--json", action="store_true")

    orchestrate_parser = sub.add_parser("orchestrate", help="Run the orchestrator until the next bounded action or stop")
    orchestrate_parser.add_argument("--material")
    orchestrate_mode = orchestrate_parser.add_mutually_exclusive_group()
    orchestrate_mode.add_argument("--execute-local", action="store_true")
    orchestrate_mode.add_argument("--plan-full-loop", action="store_true")
    orchestrate_mode.add_argument("--execute-omx", action="store_true")
    orchestrate_parser.add_argument("--write-evidence", action="store_true")
    orchestrate_parser.add_argument("--evidence-output")
    orchestrate_parser.add_argument("--json", action="store_true")


    answer_parser = sub.add_parser("answer-human-needed", help="Record an answer for a human_needed stop and optionally apply it")
    answer_parser.add_argument("--answer", required=True)
    answer_parser.add_argument("--packet")
    answer_parser.add_argument("--review-scope", choices=["pdf_and_tex", "tex_only"])
    answer_parser.add_argument("--intent", choices=["approve_existing_candidate", "generate_new_operator_candidate", "reject_candidate_with_reason"])
    answer_parser.add_argument("--action-id")
    answer_parser.add_argument("--output-answer")
    answer_parser.add_argument("--output-feedback")
    answer_parser.add_argument("--redacted-answer-only", action="store_true")
    answer_parser.add_argument("--apply", action="store_true")
    answer_parser.add_argument("--imported-feedback-output")
    answer_parser.add_argument("--max-supervised-iterations", type=int, default=1)
    answer_parser.add_argument("--quality-mode", default="claim_safe", choices=["draft", "ralph", "claim_safe"])
    answer_parser.add_argument("--max-iterations", type=int, default=10)
    answer_parser.add_argument("--require-live-verification", action="store_true")
    answer_parser.add_argument("--accept-mixed-provenance", action="store_true")
    answer_parser.add_argument("--require-compile", action="store_true")
    answer_parser.add_argument("--citation-evidence-mode", default="web", choices=["heuristic", "model", "web", "source"])
    _runtime_mode_args(answer_parser, strict_flag=True)
    _common_provider_args(answer_parser)
    _citation_provider_args(answer_parser)
    answer_parser.add_argument("--json", action="store_true")

    export_parser = sub.add_parser("export-current", help="Copy current manuscript outputs to a destination directory")
    export_parser.add_argument("--output", required=True)
    export_parser.add_argument("--include-all-artifacts", action="store_true")
    export_parser.add_argument("--json", action="store_true")

    research_parser = sub.add_parser("research-prior-work", help="Generate/import a prior-work seed using the configured provider")
    research_parser.add_argument("--output")
    research_parser.add_argument("--paper")
    research_parser.add_argument("--artifact-repo")
    research_parser.add_argument("--source", default="codex_web_seed")
    research_parser.add_argument("--import", dest="import_seed", action="store_true")
    research_parser.add_argument("--require-complete-metadata", action="store_true")
    _runtime_mode_args(research_parser, strict_flag=True)
    _common_provider_args(research_parser)

    import_parser = sub.add_parser("import-prior-work", help="Import a curated prior-work seed file")
    import_parser.add_argument("--seed-file", required=True)
    import_parser.add_argument("--source", default="manual_seed")
    import_parser.add_argument("--require-complete-metadata", action="store_true")

    sections_parser = sub.add_parser("write-sections", help="Draft or rewrite manuscript sections")
    sections_parser.add_argument("--only-sections")
    sections_parser.add_argument("--output-tex")
    sections_parser.add_argument("--claim-safe", action="store_true")
    _runtime_mode_args(sections_parser, strict_flag=True)
    _common_provider_args(sections_parser)

    sub.add_parser("compile", help="Compile the current manuscript")

    environment_parser = sub.add_parser("environment", help="Show environment-variable and readiness inventory")
    environment_parser.add_argument("--json", action="store_true")
    environment_parser.add_argument("--summary", action="store_true")

    doctor_parser = sub.add_parser("doctor", help="Run a pre-flight environment check")
    doctor_parser.add_argument("--omx-deep", action="store_true")
    doctor_parser.add_argument("--omx-timeout", type=float, default=10.0)

    critique_parser = sub.add_parser("critique", help="Run paper, section, and citation critics")
    critique_parser.add_argument("--source-paper")
    critique_parser.add_argument("--output-dir")
    critique_parser.add_argument("--citation-evidence-mode", default="heuristic", choices=["heuristic", "model", "web", "source"])
    critique_parser.add_argument("--live", action="store_true")
    critique_parser.add_argument("--claim-safe", action="store_true")
    _runtime_mode_args(critique_parser, strict_flag=True)
    _common_provider_args(critique_parser)

    quality_gate_parser = sub.add_parser("quality-gate", help="Run the draft-quality gate")
    quality_gate_parser.add_argument("--output")
    quality_gate_parser.add_argument("--plan-output")
    quality_gate_parser.add_argument("--profile", default="auto", choices=["auto", "mock", "ralph", "claim_safe"])
    quality_gate_parser.add_argument("--quality-mode", default="draft", choices=["draft", "ralph", "claim_safe"])
    quality_gate_parser.add_argument("--max-iterations", type=int, default=10)
    quality_gate_parser.add_argument("--require-live-verification", action="store_true")
    quality_gate_parser.add_argument("--accept-mixed-provenance", action="store_true")
    quality_gate_parser.add_argument("--auto-refine", action="store_true")
    quality_gate_parser.add_argument("--refine-iterations", type=int, default=1)
    quality_gate_parser.add_argument("--require-compile-for-accept", action="store_true")
    quality_gate_parser.add_argument("--no-fail-on-block", action="store_true")
    _runtime_mode_args(quality_gate_parser, strict_flag=True)
    _common_provider_args(quality_gate_parser)

    qa_loop_parser = sub.add_parser("qa-loop", help="Build the next QA-loop repair plan")
    qa_loop_parser.add_argument("--output")
    qa_loop_parser.add_argument("--quality-eval")
    qa_loop_parser.add_argument("--quality-mode", default="ralph", choices=["draft", "ralph", "claim_safe"])
    qa_loop_parser.add_argument("--max-iterations", type=int, default=10)
    qa_loop_parser.add_argument("--accept-mixed-provenance", action="store_true")
    qa_loop_parser.add_argument("--require-live-verification", action="store_true")

    qa_step_parser = sub.add_parser("qa-loop-step", help="Execute one bounded QA-loop repair step")
    qa_step_parser.add_argument("--quality-mode", default="claim_safe", choices=["draft", "ralph", "claim_safe"])
    qa_step_parser.add_argument("--max-iterations", type=int, default=10)
    qa_step_parser.add_argument("--accept-mixed-provenance", action="store_true")
    qa_step_parser.add_argument("--require-live-verification", action="store_true")
    qa_step_parser.add_argument("--require-compile", action="store_true")
    qa_step_parser.add_argument("--citation-evidence-mode", default="web", choices=["heuristic", "model", "web", "source"])
    qa_step_parser.add_argument("--quality-eval")
    qa_step_parser.add_argument("--plan")
    qa_step_parser.add_argument("--citation-support-review")
    _runtime_mode_args(qa_step_parser, strict_flag=True)
    _common_provider_args(qa_step_parser)
    _citation_provider_args(qa_step_parser)

    ralph_parser = sub.add_parser("ralph-start", help="Create or launch an OMX Ralph handoff for the current QA loop")
    ralph_parser.add_argument("--output")
    ralph_parser.add_argument("--quality-mode", default="claim_safe", choices=["draft", "ralph", "claim_safe"])
    ralph_parser.add_argument("--max-iterations", type=int, default=10)
    ralph_parser.add_argument("--require-live-verification", action="store_true")
    ralph_parser.add_argument("--accept-mixed-provenance", action="store_true")
    ralph_parser.add_argument("--evidence-root")
    ralph_parser.add_argument("--dry-run", action="store_true")
    ralph_parser.add_argument("--launch", action="store_true")

    run_parser = sub.add_parser("run", help="Run the full PaperOrchestra pipeline")
    run_parser.add_argument("--discovery-mode", default="model", choices=["model", "scholar-only", "search-grounded"])
    run_parser.add_argument("--verify-mode", default="live", choices=["live", "mock"])
    run_parser.add_argument("--verify-error-policy", default="skip", choices=["skip", "fail"])
    run_parser.add_argument("--verify-fallback-mode", default="none", choices=["none", "mock"])
    run_parser.add_argument("--require-live-verification", action="store_true")
    run_parser.add_argument("--refine-iterations", type=int, default=1)
    run_parser.add_argument("--compile", action="store_true")
    _runtime_mode_args(run_parser, strict_flag=True)
    _common_provider_args(run_parser)

    return parser


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


def _session_artifact_dir(cwd: Path, state) -> Path:
    if state.artifacts.paper_full_tex:
        return Path(state.artifacts.paper_full_tex).resolve().parent
    return run_dir(cwd, state.session_id) / "artifacts"


def _status_summary_lines(cwd: Path, payload: dict[str, object]) -> list[str]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict):
        artifacts = {}
    recovery = payload.get("session_recovery")
    if not isinstance(recovery, dict):
        recovery = {}
    artifact_dir = Path(str(artifacts.get("paper_full_tex"))).resolve().parent if artifacts.get("paper_full_tex") else run_dir(cwd, str(payload["session_id"])) / "artifacts"
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


def _copy_if_present(label: str, source: str | None, destination: Path, copied: list[dict[str, str]], skipped: list[dict[str, str]]) -> None:
    if not source:
        skipped.append({"label": label, "reason": "not recorded"})
        return
    source_path = Path(source)
    if not source_path.exists():
        skipped.append({"label": label, "source": str(source_path), "reason": "missing on disk"})
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, destination)
    copied.append({"label": label, "source": str(source_path), "destination": str(destination)})


def _export_current_artifacts(cwd: Path, output: str | Path, *, include_all_artifacts: bool = False) -> dict[str, object]:
    state = load_session(cwd)
    output_dir = Path(output).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    copied: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    artifacts = state.artifacts
    export_map = [
        ("paper_full_tex", artifacts.paper_full_tex, output_dir / "paper.full.tex"),
        ("compiled_pdf", artifacts.compiled_pdf, output_dir / "paper.full.pdf"),
        ("references_bib", artifacts.references_bib, output_dir / "references.bib"),
        ("latest_review_json", artifacts.latest_review_json, output_dir / "review.latest.json"),
        ("quality_gate_report", str(artifact_path(cwd, "quality-gate.report.json")), output_dir / "quality-gate.report.json"),
        ("session_json", str(run_dir(cwd, state.session_id) / "session.json"), output_dir / "session.json"),
    ]
    for label, source, destination in export_map:
        _copy_if_present(label, source, destination, copied, skipped)

    if include_all_artifacts:
        artifact_dir = _session_artifact_dir(cwd, state)
        if artifact_dir.exists():
            shutil.copytree(artifact_dir, output_dir / "artifacts", dirs_exist_ok=True)
            copied.append({"label": "artifacts_dir", "source": str(artifact_dir), "destination": str(output_dir / "artifacts")})
        else:
            skipped.append({"label": "artifacts_dir", "source": str(artifact_dir), "reason": "missing on disk"})

    return {"status": "ok", "session_id": state.session_id, "output_dir": str(output_dir), "copied": copied, "skipped": skipped}


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
            payload = _export_current_artifacts(cwd, args.output, include_all_artifacts=args.include_all_artifacts)
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
