from __future__ import annotations

import argparse
import json
from pathlib import Path

from paperorchestra.feedback.human_needed import record_human_needed_answer
from paperorchestra.interfaces.cli_commands.common import provider_from_args, strict_omx_env
from paperorchestra.interfaces.cli_output import print_orchestrator_payload
from paperorchestra.loop_engine.quality.gate import write_quality_gate
from paperorchestra.loop_engine.quality.loop import write_quality_loop_plan
from paperorchestra.loop_engine.ralph.bridge import run_qa_loop_step
from paperorchestra.loop_engine.ralph.handoff import build_ralph_start_payload, launch_omx_ralph


def handle_answer_human_needed(cwd: Path, args: argparse.Namespace) -> int:
    provider = provider_from_args(args) if args.apply else None
    with strict_omx_env(args.strict_omx_native):
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


def handle_quality_gate(cwd: Path, args: argparse.Namespace) -> int:
    provider = provider_from_args(args) if args.auto_refine else None
    with strict_omx_env(args.strict_omx_native):
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


def handle_qa_loop(cwd: Path, args: argparse.Namespace) -> int:
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


def handle_qa_loop_step(cwd: Path, args: argparse.Namespace) -> int:
    provider = provider_from_args(args)
    with strict_omx_env(args.strict_omx_native):
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


def handle_ralph_start(cwd: Path, args: argparse.Namespace) -> int:
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
