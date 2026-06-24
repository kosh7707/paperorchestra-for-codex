#!/usr/bin/env python3
"""Compare the source-checkout PaperOrchestra CLI with the installed console.

The common failure mode this catches is an old editable install on PATH:
``paperorchestra`` imports a different checkout than the one the current skills
were installed from, so newly added commands (for example ``visual-audit``)
appear to be missing even though the source tree supports them.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULT_REQUIRED_COMMANDS = ("visual-audit",)
TIMEOUT_SECONDS = 10


def _run(argv: list[str], *, cwd: Path | str | None = None, env: dict[str, str] | None = None) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd) if cwd is not None else None,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        return {
            "argv": argv,
            "ok": False,
            "returncode": 127,
            "stdout": "",
            "stderr": str(exc),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "argv": argv,
            "ok": False,
            "returncode": None,
            "stdout": exc.stdout or "",
            "stderr": f"timed out after {TIMEOUT_SECONDS}s",
        }
    return {
        "argv": argv,
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def _compact_result(result: dict[str, Any]) -> dict[str, Any]:
    def first_lines(value: str, limit: int = 8) -> list[str]:
        return value.splitlines()[:limit]

    return {
        "argv": result["argv"],
        "ok": result["ok"],
        "returncode": result["returncode"],
        "stdout_head": first_lines(result.get("stdout") or ""),
        "stderr_head": first_lines(result.get("stderr") or ""),
    }


def _source_env(source_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(source_root) if not existing else f"{source_root}{os.pathsep}{existing}"
    return env


def _import_origin(python: str, *, cwd: Path | str | None, env: dict[str, str] | None = None) -> dict[str, Any]:
    code = (
        "from pathlib import Path\n"
        "import paperorchestra\n"
        "print(Path(paperorchestra.__file__).resolve())\n"
    )
    return _compact_result(_run([python, "-c", code], cwd=cwd, env=env))


def _is_within(path_text: str | None, root: Path) -> bool:
    if not path_text:
        return False
    try:
        Path(path_text).resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _origin_path(origin: dict[str, Any]) -> str | None:
    lines = origin.get("stdout_head") or []
    return lines[0] if lines else None


def build_report(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    source_root = Path(args.source_root).expanduser().resolve()
    python = args.python or sys.executable
    required = list(dict.fromkeys(args.require or DEFAULT_REQUIRED_COMMANDS))
    source_env = _source_env(source_root)
    console_path = shutil.which(args.command)
    venv_cli = source_root / ".venv" / "bin" / "paperorchestra"

    source_top_help = _compact_result(_run([python, "-m", "paperorchestra.cli", "--help"], cwd=source_root, env=source_env))
    source_version = _compact_result(_run([python, "-m", "paperorchestra.cli", "--version"], cwd=source_root, env=source_env))
    source_origin = _import_origin(python, cwd=source_root, env=source_env)
    default_origin = _import_origin(python, cwd=Path("/"), env=None)

    installed_top_help = None
    installed_version = None
    if console_path:
        installed_top_help = _compact_result(_run([console_path, "--help"], cwd=source_root))
        installed_version = _compact_result(_run([console_path, "--version"], cwd=source_root))

    venv_top_help = None
    venv_version = None
    if venv_cli.exists():
        venv_top_help = _compact_result(_run([str(venv_cli), "--help"], cwd=source_root))
        venv_version = _compact_result(_run([str(venv_cli), "--version"], cwd=source_root))

    commands: dict[str, Any] = {}
    source_missing: list[str] = []
    installed_missing: list[str] = []
    venv_missing: list[str] = []

    for command in required:
        source_probe = _compact_result(
            _run([python, "-m", "paperorchestra.cli", command, "--help"], cwd=source_root, env=source_env)
        )
        installed_probe = (
            _compact_result(_run([console_path, command, "--help"], cwd=source_root)) if console_path else None
        )
        venv_probe = _compact_result(_run([str(venv_cli), command, "--help"], cwd=source_root)) if venv_cli.exists() else None
        commands[command] = {
            "source_module": source_probe,
            "installed_console": installed_probe,
            "checkout_venv": venv_probe,
        }
        if not source_probe["ok"]:
            source_missing.append(command)
        if installed_probe is None or not installed_probe["ok"]:
            installed_missing.append(command)
        if venv_cli.exists() and (venv_probe is None or not venv_probe["ok"]):
            venv_missing.append(command)

    source_origin_path = _origin_path(source_origin)
    default_origin_path = _origin_path(default_origin)
    source_origin_matches = _is_within(source_origin_path, source_root)
    default_origin_matches = _is_within(default_origin_path, source_root)
    installed_required_missing = bool(installed_missing)
    venv_required_missing = bool(venv_missing)

    recommended_invocation = f"PYTHONPATH={source_root} {python} -m paperorchestra.cli <command> [args...]"
    if venv_cli.exists() and not venv_required_missing:
        recommended_invocation = f"{venv_cli} <command> [args...]"

    status = "ok"
    exit_code = 0
    if source_missing or not source_top_help["ok"] or not source_origin_matches:
        status = "source_error"
        exit_code = 2
    elif args.strict_installed and installed_required_missing:
        status = "installed_mismatch"
        exit_code = 3
    elif installed_required_missing or (default_origin_path and not default_origin_matches):
        status = "warning"

    report = {
        "status": status,
        "source_root": str(source_root),
        "python": python,
        "installed_console": console_path,
        "checkout_venv_console": str(venv_cli) if venv_cli.exists() else None,
        "required_commands": required,
        "source_import_origin": source_origin_path,
        "default_import_origin": default_origin_path,
        "source_origin_matches_checkout": source_origin_matches,
        "default_origin_matches_checkout": default_origin_matches,
        "installed_required_missing": installed_missing,
        "checkout_venv_required_missing": venv_missing,
        "source_required_missing": source_missing,
        "recommended_invocation": recommended_invocation,
        "repair_commands": [
            "python3 -m venv .venv",
            ".venv/bin/python -m pip install -e .",
            'export PATH="$(pwd)/.venv/bin:$PATH"',
            "scripts/register-codex-mcp.sh --use-local-venv",
        ],
        "top_level": {
            "source_module_help": source_top_help,
            "source_module_version": source_version,
            "installed_console_help": installed_top_help,
            "installed_console_version": installed_version,
            "checkout_venv_help": venv_top_help,
            "checkout_venv_version": venv_version,
        },
        "commands": commands,
    }
    return report, exit_code


def print_human(report: dict[str, Any]) -> None:
    print(f"CLI surface status: {report['status']}")
    print(f"source root: {report['source_root']}")
    print(f"source import: {report['source_import_origin']}")
    print(f"default import: {report['default_import_origin']}")
    print(f"installed console: {report['installed_console'] or '<missing>'}")
    print(f"checkout venv console: {report['checkout_venv_console'] or '<missing>'}")
    for command in report["required_commands"]:
        probes = report["commands"][command]
        installed = probes["installed_console"]
        venv = probes["checkout_venv"]
        print(
            f"command {command}: "
            f"source={'ok' if probes['source_module']['ok'] else 'missing'}; "
            f"installed={'ok' if installed and installed['ok'] else 'missing'}; "
            f"venv={'ok' if venv and venv['ok'] else 'missing'}"
        )
    if report["status"] != "ok":
        print("recommended invocation:")
        print(f"  {report['recommended_invocation']}")
        print("repair:")
        for command in report["repair_commands"]:
            print(f"  {command}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", default=".", help="PaperOrchestra checkout root to verify")
    parser.add_argument("--python", help="Python executable for source-module probes. Default: current interpreter")
    parser.add_argument("--command", default="paperorchestra", help="Installed console command to compare")
    parser.add_argument("--require", action="append", help="Required subcommand. Repeatable; default: visual-audit")
    parser.add_argument(
        "--strict-installed",
        action="store_true",
        help="Exit non-zero when the installed console lacks a source-available required command.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    report, exit_code = build_report(args)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_human(report)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
