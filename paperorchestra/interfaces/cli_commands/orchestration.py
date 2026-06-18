from __future__ import annotations

import argparse
from pathlib import Path

from paperorchestra.interfaces.cli_commands.common import make_omx_executor
from paperorchestra.interfaces.cli_output import print_orchestrator_payload
from paperorchestra.orchestra.controller import OrchestraOrchestrator, inspect_state as orchestrator_inspect_state
from paperorchestra.orchestra.evidence import write_orchestrator_evidence_bundle
from paperorchestra.orchestra.executor import LocalActionExecutor


def handle_inspect_state(cwd: Path, args: argparse.Namespace) -> int:
    state = orchestrator_inspect_state(cwd, material_path=args.material)
    print_orchestrator_payload(state.to_public_dict(), json_output=args.json)
    return 0


def handle_orchestrate(cwd: Path, args: argparse.Namespace) -> int:
    orchestrator = OrchestraOrchestrator(cwd)
    if args.execute_local:
        result = orchestrator.step(material_path=args.material, execute=True, executor=LocalActionExecutor(material_path=args.material))
    elif args.plan_full_loop:
        result = orchestrator.plan_full_loop(material_path=args.material)
    elif args.execute_omx:
        result = orchestrator.execute_omx_once(material_path=args.material, executor=make_omx_executor(cwd))
    else:
        result = orchestrator.run_until_blocked(material_path=args.material)
    payload = result.to_public_dict()
    if args.write_evidence:
        payload["evidence_bundle"] = write_orchestrator_evidence_bundle(cwd, result.state, output_dir=args.evidence_output)
    print_orchestrator_payload(payload, json_output=args.json)
    return 0
