from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any


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


def _run_probe(argv: list[str], *, cwd: str | Path | None, timeout: float = 10.0) -> dict[str, Any]:
    executable = shutil.which(argv[0])
    if not executable:
        return {"status": "unavailable", "argv": argv, "return_code": None, "stdout": "", "stderr": f"{argv[0]} not found on PATH"}
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
        return {"status": "error", "argv": argv, "return_code": None, "stdout": "", "stderr": str(exc)}
    return {
        "status": "ok" if proc.returncode == 0 else "failed",
        "argv": argv,
        "return_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def _probe_summary(probe: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": probe.get("status"),
        "command": " ".join(str(part) for part in probe.get("argv") or []),
        "return_code": probe.get("return_code"),
        "stdout_summary": _truncate(probe.get("stdout")),
        "stderr_summary": _truncate(probe.get("stderr")),
    }


def build_omx_integration_table() -> list[dict[str, Any]]:
    return [
        {
            "id": 1,
            "name": "Ralph handoff",
            "status": "implemented",
            "auto_launched": False,
            "evidence": ["ralph-handoff.json", "qa-loop-history.jsonl"],
            "notes": "PaperOrchestra emits bounded Ralph handoff payloads; unbounded team launches remain operator-controlled.",
        },
        {
            "id": 2,
            "name": "Critic/citation review",
            "status": "implemented",
            "auto_launched": False,
            "evidence": ["review.latest.json", "section_review.json", "citation_support_review.json"],
            "notes": "The public surface is the high-level critique command/tool, not per-audit command sprawl.",
        },
        {
            "id": 3,
            "name": "doctor --omx-deep",
            "status": "implemented",
            "auto_launched": False,
            "evidence": ["doctor --omx-deep"],
            "notes": "Bounded probes cover local OMX/Codex readiness without exporting private traces.",
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
    }
    blocking = [
        name
        for name in ["omx_version", "codex_version", "omx_explore_help", "omx_state_list_active", "omx_trace_summary", "omx_ralph_help"]
        if probes[name]["status"] != "ok"
    ]
    return {
        "schema_version": "paperorchestra-omx-deep-report/2",
        "status": "ok" if not blocking else "degraded",
        "blocking_probe_codes": blocking,
        "probes": probes,
        "probe_summaries": {name: _probe_summary(probe) for name, probe in probes.items()},
        "integrations": build_omx_integration_table(),
        "next_steps": [
            "Run `omx doctor` if any OMX probe is degraded.",
            "Use CLI fallback when native MCP tool attachment is absent.",
        ],
    }
