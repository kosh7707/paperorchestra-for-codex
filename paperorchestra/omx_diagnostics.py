from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .io_utils import write_json
from .quality_loop_utils import _file_sha256
from .session import artifact_path

OMX_EVIDENCE_SUMMARY_FILENAME = "omx-evidence-summary.json"
OMX_REVIEW_HANDOFF_FILENAME = "omx-review-handoff.json"


def _run_probe(argv: list[str], *, cwd: str | Path | None, timeout: float = 10.0) -> dict[str, Any]:
    executable = shutil.which(argv[0])
    if not executable:
        return {
            "status": "unavailable",
            "argv": argv,
            "return_code": None,
            "stdout": "",
            "stderr": f"{argv[0]} not found on PATH",
        }
    try:
        proc = subprocess.run(
            argv,
            cwd=Path(cwd or ".").resolve(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "timeout",
            "argv": argv,
            "return_code": None,
            "stdout": _text_or_empty(exc.stdout),
            "stderr": _text_or_empty(exc.stderr) or f"timed out after {timeout:g}s",
        }
    except Exception as exc:  # pragma: no cover - defensive shell boundary
        return {
            "status": "error",
            "argv": argv,
            "return_code": None,
            "stdout": "",
            "stderr": str(exc),
        }
    return {
        "status": "ok" if proc.returncode == 0 else "failed",
        "argv": argv,
        "return_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def _text_or_empty(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _truncate(text: Any, *, limit: int = 500) -> str:
    normalized = str(text or "").replace("\x00", "").strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit] + "...<truncated>"


def _probe_summary(probe: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": probe.get("status"),
        "command": " ".join(str(part) for part in probe.get("argv") or []),
        "return_code": probe.get("return_code"),
        "stdout_summary": _truncate(probe.get("stdout")),
        "stderr_summary": _truncate(probe.get("stderr")),
    }


def _redacted_probe_summary(probe: dict[str, Any], *, reason: str) -> dict[str, Any]:
    summary = _probe_summary(probe)
    summary["stdout_summary"] = f"<redacted: {reason}>"
    summary["stderr_summary"] = _truncate(probe.get("stderr"))
    return summary


def _json_or_probe(probe: dict[str, Any]) -> Any:
    if probe.get("status") != "ok":
        return probe
    try:
        return json.loads(str(probe.get("stdout") or "{}"))
    except json.JSONDecodeError:
        return {**probe, "status": "malformed_json"}


def _trace_timeline_summary(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "schema_version": "paperorchestra-omx-trace-timeline-summary/1",
            "status": "degraded",
            "source_status": payload.get("status") if isinstance(payload, dict) else "unavailable",
            "raw_trace_timeline_exported": False,
            "prompt_text_exported": False,
        }
    if ("argv" in payload or "return_code" in payload) and "entryCount" not in payload and "timeline" not in payload:
        return {
            "schema_version": "paperorchestra-omx-trace-timeline-summary/1",
            "status": "degraded",
            "source_status": payload.get("status") or "unavailable",
            "entryCount": None,
            "totalAvailable": None,
            "filter": None,
            "first_entry": None,
            "last_entry": None,
            "raw_trace_timeline_exported": False,
            "prompt_text_exported": False,
        }
    timeline = payload.get("timeline") if isinstance(payload.get("timeline"), list) else []

    def compact(entry: Any) -> dict[str, Any] | None:
        if not isinstance(entry, dict):
            return None
        return {
            "timestamp": entry.get("timestamp"),
            "type": entry.get("type"),
            "turn_type": entry.get("turn_type"),
        }

    compact_entries = [item for item in (compact(entry) for entry in timeline) if item]
    return {
        "schema_version": "paperorchestra-omx-trace-timeline-summary/1",
        "status": "ok",
        "entryCount": payload.get("entryCount"),
        "totalAvailable": payload.get("totalAvailable"),
        "filter": payload.get("filter"),
        "first_entry": compact_entries[0] if compact_entries else None,
        "last_entry": compact_entries[-1] if compact_entries else None,
        "raw_trace_timeline_exported": False,
        "prompt_text_exported": False,
    }


def build_omx_integration_table() -> list[dict[str, Any]]:
    return [
        {
            "id": 1,
            "name": "Ralph force handoff",
            "status": "implemented",
            "auto_launched": False,
            "evidence": ["ralph-handoff.json", "qa-loop-history.jsonl"],
            "notes": "Claim-safe handoff contracts require Ralph, Critic, Citation Integrity, and human_needed cycle policy.",
        },
        {
            "id": 2,
            "name": "OMX Critic citation gate",
            "status": "implemented_as_artifact_contract",
            "auto_launched": False,
            "evidence": ["citation_integrity.critic.json", OMX_REVIEW_HANDOFF_FILENAME],
            "notes": "Native tool/session attachment is not assumed; the gate is hash-bound artifact evidence.",
        },
        {
            "id": 3,
            "name": "OMX Trace evidence export",
            "status": "implemented_degrading",
            "auto_launched": False,
            "evidence": ["omx-trace-summary.json", "omx-trace-timeline-summary.json"],
            "notes": "Exports summary/count metadata only; raw trace timelines and prompt previews are not copied.",
        },
        {
            "id": 4,
            "name": "OMX State sync",
            "status": "implemented_degrading",
            "auto_launched": False,
            "evidence": ["omx-state.json", "omx-status.txt"],
            "notes": "Exports non-secret OMX state/status summaries only.",
        },
        {
            "id": 5,
            "name": "Long smoke runner with omx sparkshell",
            "status": "implemented_as_handoff",
            "auto_launched": False,
            "evidence": ["sparkshell-long-smoke.md"],
            "notes": "Documented command is emitted; PaperOrchestra does not auto-launch long private smoke.",
        },
        {
            "id": 6,
            "name": "doctor --omx-deep",
            "status": "implemented",
            "auto_launched": False,
            "evidence": ["doctor --omx-deep"],
            "notes": "Bounded probes cover omx/codex/state/trace/ralph/sparkshell/team without private credentials.",
        },
        {
            "id": 7,
            "name": "Team/Ultrawork multi-review",
            "status": "safe_handoff_only",
            "auto_launched": False,
            "evidence": [OMX_REVIEW_HANDOFF_FILENAME],
            "notes": "Automatic team/ultrawork launch is intentionally rejected unless a human starts it.",
        },
    ]


def build_omx_deep_report(cwd: str | Path | None = None, *, timeout: float = 10.0) -> dict[str, Any]:
    probes = {
        "omx_version": _run_probe(["omx", "version"], cwd=cwd, timeout=timeout),
        "codex_version": _run_probe(["codex", "--version"], cwd=cwd, timeout=timeout),
        "omx_explore_help": _run_probe(["omx", "explore", "--help"], cwd=cwd, timeout=timeout),
        "omx_state_list_active": _run_probe(["omx", "state", "list-active", "--json"], cwd=cwd, timeout=timeout),
        "omx_trace_summary": _run_probe(["omx", "trace", "summary", "--json"], cwd=cwd, timeout=timeout),
        "omx_ralph_help": _run_probe(["omx", "ralph", "--help"], cwd=cwd, timeout=timeout),
        "omx_sparkshell_help": _run_probe(["omx", "sparkshell", "--help"], cwd=cwd, timeout=timeout),
        "omx_team_help": _run_probe(["omx", "team", "--help"], cwd=cwd, timeout=timeout),
        "omx_list": _run_probe(["omx", "list", "--json"], cwd=cwd, timeout=timeout),
    }
    blocking = [
        name
        for name in ["omx_version", "codex_version", "omx_explore_help", "omx_state_list_active", "omx_trace_summary", "omx_ralph_help"]
        if probes[name]["status"] != "ok"
    ]
    return {
        "schema_version": "paperorchestra-omx-deep-report/1",
        "status": "ok" if not blocking else "degraded",
        "blocking_probe_codes": blocking,
        "probes": probes,
        "probe_summaries": {name: _probe_summary(probe) for name, probe in probes.items()},
        "integrations": build_omx_integration_table(),
        "next_steps": [
            "Run `omx doctor` if any OMX probe is degraded.",
            "Run `paperorchestra export-omx-evidence --output <dir>` after a session to preserve trace/state summaries.",
            "Use CLI fallback when native MCP tool attachment is absent.",
        ],
    }


def export_omx_evidence(cwd: str | Path | None, output_dir: str | Path, *, timeout: float = 10.0) -> dict[str, Any]:
    root = Path(cwd or ".").resolve()
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    state_probe = _run_probe(["omx", "state", "list-active", "--json"], cwd=root, timeout=timeout)
    status_probe = _run_probe(["omx", "status"], cwd=root, timeout=timeout)
    trace_summary_probe = _run_probe(["omx", "trace", "summary", "--json"], cwd=root, timeout=timeout)
    trace_timeline_probe = _run_probe(["omx", "trace", "timeline", "--json"], cwd=root, timeout=timeout)
    files: dict[str, str] = {}

    def write_named(name: str, payload: Any) -> None:
        path = out / name
        if isinstance(payload, str):
            path.write_text(payload, encoding="utf-8")
        else:
            write_json(path, payload)
        files[name] = str(path)

    write_named("omx-state.json", _json_or_probe(state_probe))
    write_named("omx-status.txt", status_probe.get("stdout") or status_probe.get("stderr") or json.dumps(status_probe, ensure_ascii=False))
    write_named("omx-trace-summary.json", _json_or_probe(trace_summary_probe))
    trace_timeline_payload = _json_or_probe(trace_timeline_probe)
    write_named("omx-trace-timeline-summary.json", _trace_timeline_summary(trace_timeline_payload))
    write_named(
        "sparkshell-long-smoke.md",
        "\n".join(
            [
                "# OMX sparkshell long-smoke handoff",
                "",
                "This file is a handoff, not an automatic launch.",
                "",
                "Suggested bounded read-only inspection:",
                "",
                "```bash",
                "omx sparkshell --tmux-pane <pane-id> --tail-lines 400",
                "```",
                "",
                "Suggested private long smoke stays outside the public repo and records evidence under a host/private evidence root.",
            ]
        )
        + "\n",
    )
    overall_status = "ok" if all(probe.get("status") == "ok" for probe in [state_probe, status_probe, trace_summary_probe, trace_timeline_probe]) else "degraded"
    summary = {
        "schema_version": "paperorchestra-omx-evidence-summary/1",
        "status": overall_status,
        "output_dir": str(out),
        "files": files,
        "integrations": build_omx_integration_table(),
        "probes": {
            "state": _probe_summary(state_probe),
            "status": _probe_summary(status_probe),
            "trace_summary": _probe_summary(trace_summary_probe),
            "trace_timeline": _redacted_probe_summary(trace_timeline_probe, reason="raw OMX trace timeline may contain prompts or private paths"),
        },
        "redaction": {
            "raw_trace_timeline_exported": False,
            "prompt_text_exported": False,
        },
    }
    write_named(OMX_EVIDENCE_SUMMARY_FILENAME, summary)
    try:
        session_summary_path = artifact_path(root, OMX_EVIDENCE_SUMMARY_FILENAME)
        write_json(session_summary_path, summary)
        summary["session_artifact"] = str(session_summary_path)
        summary["session_artifact_sha256"] = _file_sha256(session_summary_path)
    except Exception as exc:
        summary["session_artifact"] = None
        summary["session_artifact_error"] = str(exc)
    write_json(out / OMX_EVIDENCE_SUMMARY_FILENAME, summary)
    return summary


def write_omx_review_handoff(cwd: str | Path | None, *, output_path: str | Path | None = None) -> tuple[Path, dict[str, Any]]:
    root = Path(cwd or ".").resolve()
    omx_available = shutil.which("omx") is not None
    payload = {
        "schema_version": "paperorchestra-omx-review-handoff/1",
        "status": "ready_for_manual_launch" if omx_available else "omx_unavailable",
        "auto_launched": False,
        "automatic_launch": "rejected_safe_handoff_only",
        "rationale": "Team/Ultrawork multi-review can spend unbounded model time and may expose private evidence; PaperOrchestra emits a handoff instead of auto-launching.",
        "commands": {
            "critic_citation_gate": "Ask an OMX Critic/Reviewer to inspect citation_integrity.audit.json and write citation_integrity.critic.json.",
            "team_review": "omx team 3:critic \"Review PaperOrchestra citation integrity artifacts and manuscript evidence; write findings only.\"",
            "ultrawork_review": "Use the installed $ultrawork workflow only from an interactive OMX session with private evidence mounted outside the public repo.",
            "trace_export": "paperorchestra export-omx-evidence --output <private-or-public-safe-evidence-dir>",
        },
        "integrations": build_omx_integration_table(),
        "next_steps": [
            "Run `paperorchestra doctor --omx-deep` to verify local OMX capability.",
            "Run the suggested commands manually only in the intended private/public evidence context.",
        ],
    }
    path = Path(output_path).resolve() if output_path else artifact_path(root, OMX_REVIEW_HANDOFF_FILENAME)
    write_json(path, payload)
    return path, payload
