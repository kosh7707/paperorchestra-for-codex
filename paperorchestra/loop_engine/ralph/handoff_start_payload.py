from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from paperorchestra.core.io import write_json
from paperorchestra.core.session import artifact_path, load_session
from paperorchestra.loop_engine.quality.loop import DEFAULT_MAX_ITERATIONS
from paperorchestra.loop_engine.ralph.handoff_brief import write_qa_loop_brief
from paperorchestra.loop_engine.ralph.handoff_contracts import (
    evidence_contract as _evidence_contract,
    execution_contract as _execution_contract,
    handoff_payload as _handoff_payload,
    hook_contract as _hook_contract,
)
from paperorchestra.loop_engine.ralph.handoff_plan_docs import (
    canonical_prd_text as _canonical_prd_text,
    canonical_test_spec_text as _canonical_test_spec_text,
    write_legacy_prd as _write_legacy_prd,
    write_plan_docs as _write_plan_docs,
)
from paperorchestra.loop_engine.ralph.state import _qa_loop_step_command


def build_ralph_start_payload(
    cwd: str | Path | None,
    *,
    quality_mode: str = "claim_safe",
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    output_path: str | Path | None = None,
    require_live_verification: bool = False,
    accept_mixed_provenance: bool = False,
    evidence_root: str | Path | None = None,
    _write_brief_fn=write_qa_loop_brief,
    _load_session_fn=load_session,
    _write_json_fn=write_json,
    _artifact_path_fn=artifact_path,
    _step_command_fn=_qa_loop_step_command,
) -> dict[str, Any]:
    brief_path, brief = _write_brief_fn(
        cwd,
        output_path,
        quality_mode=quality_mode,
        max_iterations=max_iterations,
        require_live_verification=require_live_verification,
        accept_mixed_provenance=accept_mixed_provenance,
    )
    state = _load_session_fn(cwd)
    cwd_path = Path(cwd or ".").resolve()
    step_cmd = _step_command_fn(
        quality_mode=quality_mode,
        max_iterations=max_iterations,
        require_live_verification=require_live_verification,
        accept_mixed_provenance=accept_mixed_provenance,
    )
    prd_path = _write_legacy_prd(
        cwd_path,
        state.session_id,
        brief_path,
        max_iterations=max_iterations,
        write_json_fn=_write_json_fn,
    )
    canonical_prd_path, canonical_test_spec_path = _write_plan_docs(
        cwd_path,
        state.session_id,
        brief_path=brief_path,
        step_cmd=step_cmd,
    )
    payload = _handoff_payload(
        cwd=cwd,
        cwd_path=cwd_path,
        state=state,
        brief_path=brief_path,
        prd_path=prd_path,
        canonical_prd_path=canonical_prd_path,
        canonical_test_spec_path=canonical_test_spec_path,
        step_cmd=step_cmd,
        quality_mode=quality_mode,
        max_iterations=max_iterations,
        require_live_verification=require_live_verification,
        accept_mixed_provenance=accept_mixed_provenance,
        evidence_root=evidence_root,
        artifact_path_fn=_artifact_path_fn,
    )
    _write_json_fn(Path(payload["handoff_path"]), payload)
    return {**payload, "brief_preview": brief[:1200]}


def launch_omx_ralph(argv: list[str], *, cwd: str | Path | None) -> subprocess.Popen:
    return subprocess.Popen(argv, cwd=Path(cwd or ".").resolve(), start_new_session=True)


__all__ = [
    "_canonical_prd_text",
    "_canonical_test_spec_text",
    "_evidence_contract",
    "_execution_contract",
    "_handoff_payload",
    "_hook_contract",
    "_write_legacy_prd",
    "_write_plan_docs",
    "build_ralph_start_payload",
    "launch_omx_ralph",
]
