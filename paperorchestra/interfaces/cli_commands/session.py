from __future__ import annotations

import argparse
import json
from pathlib import Path

from paperorchestra.core.models import InputBundle
from paperorchestra.core.session import create_session
from paperorchestra.engine.plan_gate import approve_plan
from paperorchestra.engine.review_stages import compile_current_paper
from paperorchestra.interfaces.cli_output import environment_summary_lines, status_summary_lines
from paperorchestra.interfaces.exporting import export_current_artifacts
from paperorchestra.interfaces.status_payload import build_session_status_payload
from paperorchestra.runtime.doctor import build_doctor_report
from paperorchestra.runtime.environment import build_environment_inventory


def handle_init(cwd: Path, args: argparse.Namespace) -> int:
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


def handle_status(cwd: Path, args: argparse.Namespace) -> int:
    payload = build_session_status_payload(cwd, include_recovery=True)
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


def handle_approve_plan(cwd: Path, args: argparse.Namespace) -> int:
    payload = approve_plan(cwd, plan_path=args.plan, revision=args.revision, approved_by=args.approved_by)
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print("paper-plan approved")
        print(f"Plan: {payload['plan_path']}")
        print(f"Approval record: {payload['approval_record_path']}")
    return 0


def handle_export_current(cwd: Path, args: argparse.Namespace) -> int:
    payload = export_current_artifacts(cwd, args.output, include_all_artifacts=args.include_all_artifacts)
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"Exported PaperOrchestra outputs for session {payload['session_id']}")
        print(f"Output: {payload['output_dir']}")
        for item in payload["copied"]:
            print(f"  - {item['label']}: {item['destination']}")
    return 0


def handle_compile(cwd: Path, args: argparse.Namespace) -> int:
    print(compile_current_paper(cwd))
    return 0


def handle_environment(cwd: Path, args: argparse.Namespace) -> int:
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


def handle_doctor(cwd: Path, args: argparse.Namespace) -> int:
    payload = build_doctor_report(cwd, omx_deep=args.omx_deep, omx_timeout=args.omx_timeout)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0
