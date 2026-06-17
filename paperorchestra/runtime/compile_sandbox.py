from __future__ import annotations

import subprocess
import shutil
from pathlib import Path


SANDBOX_TOOLS = ["bwrap", "firejail", "nsjail"]


def _command_text(command: list[str]) -> str:
    return " ".join(command)


def _trim_probe_output(text: str, *, limit: int = 240) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 3]}..."


def _sandbox_probe_command(tool_path: str) -> list[str]:
    tool_name = Path(tool_path).name
    if tool_name == "bwrap":
        command = [
            tool_path,
            "--unshare-all",
            "--share-net",
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
        return command
    if tool_name == "firejail":
        return [tool_path, "--quiet", "--net=none", "--private", "/bin/true"]
    if tool_name == "nsjail":
        return [tool_path, "-Mo", "--chroot", "/", "--cwd", "/", "--disable_clone_newnet", "--", "/bin/true"]
    return [tool_path, "--help"]


def _sandbox_tool_usable(tool_path: str) -> tuple[bool, str]:
    command = _sandbox_probe_command(tool_path)
    try:
        proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=8, check=False)
    except subprocess.TimeoutExpired:
        return False, f"probe timed out: {_command_text(command)}"
    except OSError as exc:
        return False, f"probe could not start: {exc}"
    except Exception as exc:
        return False, f"probe raised {type(exc).__name__}: {exc}"

    output = _trim_probe_output("\n".join(part for part in (proc.stderr, proc.stdout) if part))
    if proc.returncode == 0:
        return True, f"probe passed: {_command_text(command)}"
    if output:
        return False, f"probe failed with exit {proc.returncode}: {output}"
    return False, f"probe failed with exit {proc.returncode}: {_command_text(command)}"


def _detect_sandbox_tool_with_notes() -> tuple[str | None, list[str]]:
    notes: list[str] = []
    for tool in SANDBOX_TOOLS:
        path = shutil.which(tool)
        if not path:
            continue
        usable, reason = _sandbox_tool_usable(path)
        if usable:
            notes.append(f"Detected usable sandbox tool: {path} ({reason})")
            return path, notes
        notes.append(f"Detected sandbox tool {path}, but it failed usability probe: {reason}")
    return None, notes


def detect_sandbox_tool() -> str | None:
    return _detect_sandbox_tool_with_notes()[0]


def _wrapper_script_contents(tool_path: str) -> str:
    tool_name = Path(tool_path).name
    if tool_name == "bwrap":
        return f'''#!/usr/bin/env bash
set -euo pipefail
if [ "$#" -lt 1 ]; then
  echo "usage: $0 <command> [args...]" >&2
  exit 2
fi
args=(
  --unshare-all
  --share-net
  --die-with-parent
  --ro-bind /usr /usr
  --ro-bind /bin /bin
  --ro-bind /lib /lib
  --ro-bind /lib64 /lib64
  --ro-bind /etc /etc
  --proc /proc
  --dev /dev
  --tmpfs /tmp
  --bind "$PWD" "$PWD"
  --chdir "$PWD"
)
if [ -n "${{HOME:-}}" ] && [ -d "$HOME" ]; then
  args+=(--bind "$HOME" "$HOME" --setenv HOME "$HOME")
fi
if [ -d /var/lib/texmf ]; then
  args+=(--ro-bind /var/lib/texmf /var/lib/texmf)
fi
exec {tool_path} "${{args[@]}}" "$@"
'''
    if tool_name == "firejail":
        return f'''#!/usr/bin/env bash
set -euo pipefail
if [ "$#" -lt 1 ]; then
  echo "usage: $0 <command> [args...]" >&2
  exit 2
fi
exec {tool_path} --quiet --private="$PWD" --net=none "$@"
'''
    if tool_name == "nsjail":
        return f'''#!/usr/bin/env bash
set -euo pipefail
if [ "$#" -lt 1 ]; then
  echo "usage: $0 <command> [args...]" >&2
  exit 2
fi
exec {tool_path} -Mo --chroot "$PWD" --cwd / --disable_clone_newnet -- "$@"
'''
    raise ValueError(f"Unsupported sandbox tool: {tool_name}")


def _write_sandbox_wrapper(cwd: str | Path | None, tool_path: str) -> str:
    tools_dir = Path(cwd or ".").resolve() / ".paper-orchestra" / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    wrapper = tools_dir / "tex-sandbox.sh"
    wrapper.write_text(_wrapper_script_contents(tool_path), encoding="utf-8")
    wrapper.chmod(0o755)
    return str(wrapper)


def ensure_sandbox_wrapper(cwd: str | Path | None, *, tool_path: str | None = None) -> str | None:
    tool = tool_path or detect_sandbox_tool()
    if not tool:
        return None
    return _write_sandbox_wrapper(cwd, tool)

