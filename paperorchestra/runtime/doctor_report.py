from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from paperorchestra.core.session import get_current_session_id
from paperorchestra.interfaces.mcp.smoke_report import build_mcp_smoke_report
from paperorchestra.reviews.reproducibility import build_reproducibility_audit
from paperorchestra.runtime.compile_env import inspect_compile_environment
from paperorchestra.runtime.doctor_probes import _command_version, _exact_opt_in_env, _truthy_env, build_omx_control_surface_probe
from paperorchestra.runtime.doctor_session import build_session_recovery_hint
from paperorchestra.runtime.environment import build_environment_inventory, package_context
from paperorchestra.runtime.omx_bridge import _resolve_omx_model, _resolve_omx_reasoning_effort
from paperorchestra.runtime.omx_diagnostics import build_omx_deep_report
from paperorchestra.runtime.readiness_profiles import build_readiness_profiles


def _base_checks(
    *,
    pkg_context: dict[str, Any],
    omx_path: str | None,
    codex_path: str | None,
    omx_version: str | None,
    codex_version: str | None,
    omx_control_surface_probe: dict[str, Any],
    mcp_smoke: dict[str, Any],
    compile_report: dict[str, Any],
    current_session_id: str | None,
    session_recovery: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        {
            "code": "package_import_context",
            "status": "warning" if pkg_context.get("stale_install_warning") else "ok",
            "detail": pkg_context,
        },
        {"code": "omx_available", "status": "ok" if omx_path else "missing", "detail": omx_path},
        {"code": "omx_version", "status": "ok" if omx_version else "warning", "detail": omx_version or "version unavailable"},
        {"code": "codex_available", "status": "ok" if codex_path else "missing", "detail": codex_path},
        {"code": "codex_version", "status": "ok" if codex_version else "warning", "detail": codex_version or "version unavailable"},
        {"code": "omx_control_surface_probe", "status": omx_control_surface_probe["status"], "detail": omx_control_surface_probe},
        {"code": "paperorchestra_mcp_health", "status": mcp_smoke["status"], "detail": mcp_smoke},
        {
            "code": "compile_environment_ready",
            "status": "ok" if compile_report.get("ready_for_compile") else "missing",
            "detail": compile_report,
        },
        {
            "code": "papero_allow_tex_compile",
            "status": "ok" if _exact_opt_in_env("PAPERO_ALLOW_TEX_COMPILE") else "warning",
            "detail": os.environ.get("PAPERO_ALLOW_TEX_COMPILE") or "not set; compile commands will stay blocked",
        },
        {
            "code": "semantic_scholar_api_key",
            "status": "ok" if os.environ.get("SEMANTIC_SCHOLAR_API_KEY") else "warning",
            "detail": "set" if os.environ.get("SEMANTIC_SCHOLAR_API_KEY") else "not set; live verification may be rate-limited",
        },
        {
            "code": "current_session",
            "status": "ok" if current_session_id else "warning",
            "detail": current_session_id or "no current session; run paperorchestra init first",
        },
        {
            "code": "session_recovery",
            "status": "ok" if session_recovery.get("status") == "ok" else "warning",
            "detail": session_recovery,
        },
    ]


def build_doctor_report(cwd: str | Path | None = None, *, omx_deep: bool = False, omx_timeout: float = 10.0) -> dict[str, Any]:
    root = Path(cwd or ".").resolve()
    omx_path = shutil.which("omx")
    codex_path = shutil.which("codex")
    omx_version = _command_version(["omx", "--version"]) if omx_path else None
    codex_version = _command_version(["codex", "--version"]) if codex_path else None
    omx_control_surface_probe = build_omx_control_surface_probe(omx_path, codex_path)
    mcp_smoke = build_mcp_smoke_report(cwd=root, timeout_sec=5.0)
    compile_report = inspect_compile_environment(root).to_dict()
    disk = shutil.disk_usage(root)
    try:
        current_session_id = get_current_session_id(root)
    except Exception:
        current_session_id = None

    session_recovery = build_session_recovery_hint(root)
    reproducibility = None
    if current_session_id:
        try:
            reproducibility = build_reproducibility_audit(root)
        except Exception as exc:
            reproducibility = {"verdict": "WARN", "reasons": [f"Unable to compute reproducibility audit: {exc}"]}
    profiles = build_readiness_profiles(
        omx_available=bool(omx_path),
        codex_available=bool(codex_path),
        omx_control_surface_ready=bool(omx_control_surface_probe.get("ready")),
        omx_control_surface_missing=list(omx_control_surface_probe.get("missing") or []),
        omx_control_surface_next_steps=list(omx_control_surface_probe.get("next_steps") or []),
        provider_command_configured=bool(os.environ.get("PAPERO_MODEL_CMD")),
        semantic_scholar_api_key_set=bool(os.environ.get("SEMANTIC_SCHOLAR_API_KEY")),
        compile_environment_ready=bool(compile_report.get("ready_for_compile")),
        tex_compile_opt_in=_exact_opt_in_env("PAPERO_ALLOW_TEX_COMPILE"),
        strict_omx_native=_truthy_env("PAPERO_STRICT_OMX_NATIVE"),
    )
    docs = build_environment_inventory()["docs"]
    pkg_context = package_context(root)
    checks = _base_checks(
        pkg_context=pkg_context,
        omx_path=omx_path,
        codex_path=codex_path,
        omx_version=omx_version,
        codex_version=codex_version,
        omx_control_surface_probe=omx_control_surface_probe,
        mcp_smoke=mcp_smoke,
        compile_report=compile_report,
        current_session_id=current_session_id,
        session_recovery=session_recovery,
    )
    if reproducibility is not None:
        checks.append(
            {
                "code": "current_session_reproducibility",
                "status": "ok" if reproducibility.get("verdict") == "OK" else "warning",
                "detail": reproducibility,
            }
        )

    missing_summary = [{"profile": profile["name"], "missing": profile["missing"]} for profile in profiles if not profile["ready"]]
    payload = {
        "overall_status": "ok" if all(check["status"] == "ok" for check in checks) else "warning",
        "cwd": str(root),
        "omx_model": _resolve_omx_model(),
        "omx_reasoning_effort": _resolve_omx_reasoning_effort(),
        "package_context": pkg_context,
        "provider_command_configured": bool(os.environ.get("PAPERO_MODEL_CMD")),
        "environment_docs": docs,
        "omx_control_surface_probe": omx_control_surface_probe,
        "paperorchestra_mcp_health": mcp_smoke,
        "readiness_profiles": profiles,
        "missing_summary": missing_summary,
        "session_recovery": session_recovery,
        "disk_usage": {"total_bytes": disk.total, "used_bytes": disk.used, "free_bytes": disk.free},
        "reproducibility": reproducibility,
        "checks": checks,
        "notes": [
            "Use PAPERO_OMX_MODEL and PAPERO_OMX_REASONING_EFFORT to tune OMX-native model quality/cost.",
            "Use `paperorchestra environment` for the canonical environment-variable and prerequisite inventory.",
            "Set PAPERO_ALLOW_TEX_COMPILE=1 before compiling TeX sources.",
            "Set SEMANTIC_SCHOLAR_API_KEY for more reliable live citation verification.",
            "Use `paperorchestra quality-gate --no-fail-on-block` to classify whether the current run is suitable for reproducibility/fidelity claims.",
            "`codex mcp list` confirms registration, not that the active Codex conversation received mcp__paperorchestra__ tools; `paperorchestra doctor` checks stdio server health, while active-session attachment still requires a fresh Codex session with visible mcp__paperorchestra__ tools.",
        ],
    }
    if omx_deep:
        payload["omx_deep"] = build_omx_deep_report(root, timeout=omx_timeout)
    return payload
