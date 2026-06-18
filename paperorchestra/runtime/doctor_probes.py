from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _exact_opt_in_env(name: str) -> bool:
    return os.environ.get(name) == "1"


def _command_version(argv: list[str]) -> str | None:
    try:
        proc = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False, timeout=5)
    except Exception:
        return None
    output = (proc.stdout or "").strip()
    if proc.returncode != 0 or not output:
        return None
    return output.splitlines()[0]


def _run_bwrap_namespace_probe(bwrap_path: str) -> tuple[bool, str]:
    command = [
        bwrap_path,
        "--unshare-all",
        "--die-with-parent",
        "--ro-bind",
        "/usr",
        "/usr",
        "--ro-bind",
        "/bin",
        "/bin",
    ]
    if Path("/lib").exists():
        command.extend(["--ro-bind", "/lib", "/lib"])
    if Path("/lib64").exists():
        command.extend(["--ro-bind", "/lib64", "/lib64"])
    command.extend(["--proc", "/proc", "--dev", "/dev", "/bin/true"])
    try:
        proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False, timeout=5)
    except subprocess.TimeoutExpired:
        return False, "bwrap namespace probe timed out"
    except Exception as exc:
        return False, f"bwrap namespace probe could not run: {exc}"
    output = " ".join(part.strip() for part in (proc.stderr, proc.stdout) if part.strip())
    if proc.returncode == 0:
        return True, "bwrap namespace probe passed"
    if "No permissions to create new namespace" in output:
        return False, "bwrap cannot create namespaces in this container"
    return False, output or f"bwrap namespace probe failed with exit {proc.returncode}"


def build_omx_control_surface_probe(omx_path: str | None, codex_path: str | None) -> dict[str, Any]:
    xz_path = shutil.which("xz")
    bwrap_path = shutil.which("bwrap")
    checks: dict[str, Any] = {
        "omx_available": bool(omx_path),
        "codex_available": bool(codex_path),
        "xz_available": bool(xz_path),
        "bwrap_available": bool(bwrap_path),
        "bwrap_namespace_usable": None,
    }
    missing: list[str] = []
    next_steps: list[str] = []
    detail_parts: list[str] = []

    if not omx_path:
        missing.append("Install `omx` and ensure it is on PATH.")
        next_steps.append("omx doctor")
    if not codex_path:
        missing.append("Install `codex` and ensure it is on PATH.")
        next_steps.append("codex --help")
    if not xz_path:
        missing.append("Install xz-utils so OMX can extract .tar.xz control harness archives.")
        next_steps.append("apt-get install -y xz-utils")

    status = "missing" if missing else "ok"
    if bwrap_path:
        usable, reason = _run_bwrap_namespace_probe(bwrap_path)
        checks["bwrap_namespace_usable"] = usable
        detail_parts.append(reason)
        if not usable and status == "ok":
            status = "warning"
            missing.append(
                f"OMX local bwrap namespace probe failed: {reason}. "
                "This is a conservative prerequisite warning; actual `omx explore` may still work if OMX uses a different runtime fallback."
            )
            next_steps.extend(
                [
                    "Use --runtime-mode compatibility for local mock/demo runs.",
                    'Optionally run `omx explore --prompt "Return exactly OK"` to test the actual OMX runtime path on this machine.',
                    "Run OMX-native workflows outside this restricted container or configure an OMX-compatible runtime sandbox.",
                ]
            )
    else:
        detail_parts.append("bwrap not found; bounded probe did not treat this as a blocker because OMX runtime packaging may vary.")

    ready = status == "ok"
    if not detail_parts:
        detail_parts.append("bounded OMX prerequisite probe passed")
    return {
        "ready": ready,
        "status": status,
        "checks": checks,
        "detail": "; ".join(detail_parts),
        "missing": missing,
        "next_steps": list(dict.fromkeys(next_steps)),
        "note": "This is a bounded local prerequisite/control-surface probe, not a full OMX-native model run.",
    }
