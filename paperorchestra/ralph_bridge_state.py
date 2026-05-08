from __future__ import annotations

import hashlib
import json
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .quality_loop_policy import QA_LOOP_SUPPORTED_HANDLER_CODES
from .session import artifact_path, load_session, runtime_root, save_session

QA_LOOP_EXECUTION_SCHEMA_VERSION = "qa-loop-execution/1"
QA_LOOP_BRIEF_FILENAME = "ralph-brief.md"
QA_LOOP_HANDOFF_FILENAME = "ralph-handoff.json"
OMX_TMUX_INJECT_MARKER = "[OMX_TMUX_INJECT]"
OMX_TMUX_INJECT_PROMPT = f"Continue from current mode state. {OMX_TMUX_INJECT_MARKER}"
EXIT_CODES = {
    "ready_for_human_finalization": 0,
    "continue": 10,
    "human_needed": 20,
    "failed": 30,
    "execution_error": 40,
}
TERMINAL_VERDICTS = {"ready_for_human_finalization", "human_needed", "failed"}
SUPPORTED_HANDLER_CODES = QA_LOOP_SUPPORTED_HANDLER_CODES


def _qa_loop_step_command(
    *,
    quality_mode: str,
    max_iterations: int,
    require_live_verification: bool,
    accept_mixed_provenance: bool,
    provider_command_env: str = "PAPERO_MODEL_CMD",
    citation_provider_command_env: str = "PAPERO_WEB_PROVIDER_CMD",
) -> str:
    args = [
        "paperorchestra",
        "qa-loop-step",
        "--quality-mode",
        quality_mode,
        "--max-iterations",
        str(max_iterations),
        "--provider",
        "shell",
        "--runtime-mode",
        "omx_native",
        "--strict-omx-native",
        "--require-compile",
        "--citation-evidence-mode",
        "web",
        "--provider-command",
        f"${provider_command_env}",
        "--citation-provider",
        "shell",
        "--citation-provider-command",
        f"${citation_provider_command_env}",
    ]
    if require_live_verification:
        args.append("--require-live-verification")
    if accept_mixed_provenance:
        args.append("--accept-mixed-provenance")
    return " ".join(shlex.quote(arg) if not arg.startswith("$") else f"\"{arg}\"" for arg in args)
NON_SUPPORTED_CITATION_STATUSES = {
    "unsupported",
    "weakly_supported",
    "insufficient_evidence",
    "needs_manual_check",
    "metadata_only",
    "contradicted",
}


@dataclass(frozen=True)
class StepResult:
    path: Path
    payload: dict[str, Any]
    exit_code: int


def _read_json(path: str | Path | None) -> Any:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists():
        return None
    return json.loads(candidate.read_text(encoding="utf-8"))


def _artifact_sha(path: str | Path | None) -> str | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return None
    return "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest()


def _session_mutation_snapshot(state) -> dict[str, Any]:
    return {
        "latest_validation_json": state.artifacts.latest_validation_json,
        "latest_compile_report_json": state.artifacts.latest_compile_report_json,
        "compiled_pdf": state.artifacts.compiled_pdf,
        "active_artifact": state.active_artifact,
        "current_phase": state.current_phase,
        "notes": list(state.notes),
    }


def _restore_session_mutation_snapshot(cwd: str | Path | None, snapshot: dict[str, Any]) -> None:
    state = load_session(cwd)
    state.artifacts.latest_validation_json = snapshot.get("latest_validation_json")
    state.artifacts.latest_compile_report_json = snapshot.get("latest_compile_report_json")
    state.artifacts.compiled_pdf = snapshot.get("compiled_pdf")
    state.active_artifact = snapshot.get("active_artifact")
    state.current_phase = snapshot.get("current_phase")
    state.notes = list(snapshot.get("notes") or [])
    save_session(cwd, state)


def _file_content_snapshot(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {"path": None, "exists": False, "content": None}
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return {"path": str(candidate), "exists": False, "content": None}
    return {"path": str(candidate), "exists": True, "content": candidate.read_bytes()}


def _restore_file_content_snapshot(snapshot: dict[str, Any]) -> None:
    path_value = snapshot.get("path")
    if not path_value:
        return
    path = Path(path_value)
    if snapshot.get("exists"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(snapshot.get("content") or b"")
    elif path.exists():
        path.unlink()



def _plan_path(cwd: str | Path | None, name: str) -> Path:
    return artifact_path(cwd, name)


def _next_execution_path(cwd: str | Path | None) -> tuple[int, Path]:
    root = runtime_root(cwd)
    existing = sorted(root.glob("qa-loop-execution.iter-*.json"))
    index = len(existing) + 1
    return index, root / f"qa-loop-execution.iter-{index:02d}.json"


def _failing_codes(quality_eval: dict[str, Any]) -> list[str]:
    result: list[str] = []
    tiers = quality_eval.get("tiers") if isinstance(quality_eval, dict) else {}
    if not isinstance(tiers, dict):
        return result
    for key, tier in tiers.items():
        if not str(key).startswith("tier_") or not isinstance(tier, dict):
            continue
        if tier.get("status") not in {"fail", "warn"}:
            continue
        result.extend(str(code) for code in tier.get("failing_codes") or [])
    return sorted(dict.fromkeys(result))


def _citation_summary(cwd: str | Path | None) -> dict[str, int]:
    state = load_session(cwd)
    if not state.artifacts.paper_full_tex:
        return {}
    path = Path(state.artifacts.paper_full_tex).resolve().parent / "citation_support_review.json"
    payload = _read_json(path)
    summary = payload.get("summary") if isinstance(payload, dict) else {}
    return dict(summary) if isinstance(summary, dict) else {}


def _citation_issue_count(summary: dict[str, int]) -> int:
    return sum(int(value or 0) for key, value in summary.items() if key != "supported")


def _manuscript_hash(payload: dict[str, Any]) -> str | None:
    value = payload.get("manuscript_hash") if isinstance(payload, dict) else None
    if value:
        return str(value)
    return None


def quality_eval_status(quality_eval: dict[str, Any]) -> dict[str, str]:
    tiers = quality_eval.get("tiers") if isinstance(quality_eval, dict) else {}
    result: dict[str, str] = {}
    if isinstance(tiers, dict):
        for key, tier in tiers.items():
            if isinstance(tier, dict):
                result[str(key)] = str(tier.get("status"))
    return result


def compute_progress_delta(before_eval: dict[str, Any], after_eval: dict[str, Any], before_summary: dict[str, int], after_summary: dict[str, int]) -> dict[str, Any]:
    before_codes = set(_failing_codes(before_eval))
    after_codes = set(_failing_codes(after_eval))
    before_issues = _citation_issue_count(before_summary)
    after_issues = _citation_issue_count(after_summary)
    before_hash = _manuscript_hash(before_eval)
    after_hash = _manuscript_hash(after_eval)
    manuscript_identity_known = bool(before_hash and after_hash)
    same_manuscript = manuscript_identity_known and before_hash == after_hash
    progress_signal = bool((before_codes - after_codes) or after_issues < before_issues)
    forward_progress = progress_signal
    if not manuscript_identity_known:
        forward_progress = False
    elif after_codes and same_manuscript:
        forward_progress = False
    return {
        "resolved_codes": sorted(before_codes - after_codes),
        "new_codes": sorted(after_codes - before_codes),
        "before_failing_codes": sorted(before_codes),
        "after_failing_codes": sorted(after_codes),
        "before_manuscript_hash": before_hash,
        "after_manuscript_hash": after_hash,
        "same_manuscript_as_previous": same_manuscript if manuscript_identity_known else None,
        "manuscript_identity_known": manuscript_identity_known,
        "before_citation_issue_count": before_issues,
        "after_citation_issue_count": after_issues,
        "citation_issue_delta": after_issues - before_issues,
        "forward_progress": forward_progress,
    }


def qa_loop_exit_code(verdict: str) -> int:
    return EXIT_CODES.get(verdict, EXIT_CODES["execution_error"])
