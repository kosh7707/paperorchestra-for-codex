from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .compile_env import inspect_compile_environment
from .environment import (
    build_environment_inventory,
    build_readiness_profiles,
    package_context,
)
from .fidelity import build_reproducibility_audit
from .omx_bridge import _resolve_omx_model, _resolve_omx_reasoning_effort
from .session import get_current_session_id, load_session


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _exact_opt_in_env(name: str) -> bool:
    return os.environ.get(name) == "1"


def _command_version(argv: list[str]) -> str | None:
    try:
        proc = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False, timeout=5)
    except Exception:
        return None
    output = (proc.stdout or '').strip()
    if proc.returncode != 0 or not output:
        return None
    return output.splitlines()[0]


def build_session_recovery_hint(cwd: str | Path | None = None) -> dict[str, Any]:
    root = Path(cwd or '.').resolve()
    try:
        state = load_session(root)
    except Exception as exc:
        return {
            'status': 'missing',
            'detail': str(exc),
            'next_commands': ['paperorchestra init --idea ... --experimental-log ... --template ... --guidelines ...'],
        }

    artifacts = state.artifacts
    next_commands: list[str] = []
    notes: list[str] = []

    if artifacts.compiled_pdf and artifacts.paper_full_tex:
        status = 'ok'
        notes.append('Session has a manuscript and compiled PDF artifact.')
    elif state.current_phase in {'complete', 'draft_complete'}:
        status = 'ok'
        notes.append('Session has reached a terminal usable draft state.')
    elif not artifacts.outline_json:
        status = 'actionable'
        next_commands.append('paperorchestra outline --provider shell')
    elif not artifacts.plot_manifest_json:
        status = 'actionable'
        next_commands.append('paperorchestra generate-plots --provider shell')
    elif not artifacts.candidate_papers_json:
        status = 'actionable'
        next_commands.append('paperorchestra discover-papers --mode search-grounded')
    elif not artifacts.citation_registry_json:
        status = 'actionable'
        next_commands.extend([
            'paperorchestra verify-papers --mode live --on-error skip',
            'paperorchestra verify-papers --mode mock  # offline/demo fallback only',
        ])
        notes.append('If live verification was rate-limited, set SEMANTIC_SCHOLAR_API_KEY and retry.')
    elif not artifacts.references_bib:
        status = 'actionable'
        next_commands.append('paperorchestra build-bib')
    elif not artifacts.intro_related_tex:
        status = 'actionable'
        next_commands.append('paperorchestra write-intro-related --provider shell')
    elif not artifacts.paper_full_tex:
        status = 'actionable'
        next_commands.append('paperorchestra write-sections --provider shell')
    elif state.current_phase == 'blocked':
        status = 'blocked'
        next_commands.extend([
            'paperorchestra status --json',
            'paperorchestra review --provider shell',
            'paperorchestra refine --provider shell --iterations 1',
        ])
        notes.append('Inspect latest validation/review artifacts before retrying refinement.')
    else:
        status = 'actionable'
        next_commands.extend(['paperorchestra status --json', 'paperorchestra run --provider shell'])

    if artifacts.latest_verification_errors_json:
        notes.append(f'Live verification errors recorded at: {artifacts.latest_verification_errors_json}')
    if artifacts.latest_runtime_parity_json:
        notes.append(f'Runtime parity report available at: {artifacts.latest_runtime_parity_json}')
    if artifacts.latest_reproducibility_json:
        notes.append(f'Reproducibility audit available at: {artifacts.latest_reproducibility_json}')

    return {
        'status': status,
        'session_id': state.session_id,
        'current_phase': state.current_phase,
        'active_artifact': state.active_artifact,
        'next_commands': next_commands,
        'notes': notes,
    }


def build_doctor_report(cwd: str | Path | None = None) -> dict[str, Any]:
    root = Path(cwd or '.').resolve()
    omx_path = shutil.which('omx')
    codex_path = shutil.which('codex')
    omx_version = _command_version(['omx', '--version']) if omx_path else None
    codex_version = _command_version(['codex', '--version']) if codex_path else None
    compile_report = inspect_compile_environment(root).to_dict()
    disk = shutil.disk_usage(root)
    current_session_id: str | None = None
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
            reproducibility = {'verdict': 'WARN', 'reasons': [f'Unable to compute reproducibility audit: {exc}']}
    profiles = build_readiness_profiles(
        omx_available=bool(omx_path),
        codex_available=bool(codex_path),
        provider_command_configured=bool(os.environ.get('PAPERO_MODEL_CMD')),
        semantic_scholar_api_key_set=bool(os.environ.get('SEMANTIC_SCHOLAR_API_KEY')),
        compile_environment_ready=bool(compile_report.get('ready_for_compile')),
        tex_compile_opt_in=_exact_opt_in_env('PAPERO_ALLOW_TEX_COMPILE'),
        strict_omx_native=_truthy_env('PAPERO_STRICT_OMX_NATIVE'),
    )
    docs = build_environment_inventory()['docs']
    pkg_context = package_context(root)

    checks = [
        {
            'code': 'package_import_context',
            'status': 'warning' if pkg_context.get('stale_install_warning') else 'ok',
            'detail': pkg_context,
        },
        {'code': 'omx_available', 'status': 'ok' if omx_path else 'missing', 'detail': omx_path},
        {'code': 'omx_version', 'status': 'ok' if omx_version else 'warning', 'detail': omx_version or 'version unavailable'},
        {'code': 'codex_available', 'status': 'ok' if codex_path else 'missing', 'detail': codex_path},
        {'code': 'codex_version', 'status': 'ok' if codex_version else 'warning', 'detail': codex_version or 'version unavailable'},
        {
            'code': 'compile_environment_ready',
            'status': 'ok' if compile_report.get('ready_for_compile') else 'missing',
            'detail': compile_report,
        },
        {
            'code': 'papero_allow_tex_compile',
            'status': 'ok' if _exact_opt_in_env('PAPERO_ALLOW_TEX_COMPILE') else 'warning',
            'detail': os.environ.get('PAPERO_ALLOW_TEX_COMPILE') or 'not set; compile commands will stay blocked',
        },
        {
            'code': 'semantic_scholar_api_key',
            'status': 'ok' if os.environ.get('SEMANTIC_SCHOLAR_API_KEY') else 'warning',
            'detail': 'set' if os.environ.get('SEMANTIC_SCHOLAR_API_KEY') else 'not set; live verification may be rate-limited',
        },
        {
            'code': 'current_session',
            'status': 'ok' if current_session_id else 'warning',
            'detail': current_session_id or 'no current session; run paperorchestra init or guided intake first',
        },
        {
            'code': 'session_recovery',
            'status': 'ok' if session_recovery.get('status') == 'ok' else 'warning',
            'detail': session_recovery,
        },
    ]
    if reproducibility is not None:
        checks.append(
            {
                'code': 'current_session_reproducibility',
                'status': 'ok' if reproducibility.get('verdict') == 'OK' else 'warning',
                'detail': reproducibility,
            }
        )

    overall = 'ok' if all(check['status'] == 'ok' for check in checks) else 'warning'
    missing_summary = [
        {'profile': profile['name'], 'missing': profile['missing']}
        for profile in profiles
        if not profile['ready']
    ]
    return {
        'overall_status': overall,
        'cwd': str(root),
        'omx_model': _resolve_omx_model(),
        'omx_reasoning_effort': _resolve_omx_reasoning_effort(),
        'package_context': pkg_context,
        'provider_command_configured': bool(os.environ.get('PAPERO_MODEL_CMD')),
        'environment_docs': docs,
        'readiness_profiles': profiles,
        'missing_summary': missing_summary,
        'session_recovery': session_recovery,
        'disk_usage': {
            'total_bytes': disk.total,
            'used_bytes': disk.used,
            'free_bytes': disk.free,
        },
        'reproducibility': reproducibility,
        'checks': checks,
        'notes': [
            'Use PAPERO_OMX_MODEL and PAPERO_OMX_REASONING_EFFORT to tune OMX-native model quality/cost.',
            'Use `paperorchestra environment` for the canonical environment-variable and prerequisite inventory.',
            'Set PAPERO_ALLOW_TEX_COMPILE=1 before compiling TeX sources.',
            'Set SEMANTIC_SCHOLAR_API_KEY for more reliable live citation verification.',
            'Use `paperorchestra audit-reproducibility` to classify whether the current run is suitable for reproducibility/fidelity claims.',
        ],
    }
