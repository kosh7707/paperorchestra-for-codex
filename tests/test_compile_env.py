from __future__ import annotations

from pathlib import Path

from paperorchestra.runtime import compile_env


def test_inspect_compile_environment_reuses_detected_sandbox_tool_for_wrapper(monkeypatch, tmp_path: Path) -> None:
    probe_calls = 0
    wrapper_calls: list[tuple[str | Path | None, str | None]] = []

    monkeypatch.setattr(compile_env, "detect_latex_engine", lambda: "/usr/bin/latexmk")
    monkeypatch.setattr(compile_env, "detect_package_manager", lambda: None)
    monkeypatch.setattr(compile_env, "detect_cargo", lambda: None)
    monkeypatch.setattr(compile_env, "detect_pkg_config", lambda: None)
    monkeypatch.setattr(
        compile_env,
        "_install_command_context",
        lambda: {
            "is_root": False,
            "sudo_available": False,
            "sudo_usable": False,
            "command_prefix": "",
            "can_run_install_commands_directly": False,
        },
    )
    monkeypatch.delenv("PAPERO_TEX_SANDBOX_CMD", raising=False)

    def detect_once() -> tuple[str | None, list[str]]:
        nonlocal probe_calls
        probe_calls += 1
        return "/usr/bin/bwrap", ["Detected usable sandbox tool: /usr/bin/bwrap (probe passed)"]

    def fake_ensure(cwd: str | Path | None, *, tool_path: str | None = None) -> str | None:
        wrapper_calls.append((cwd, tool_path))
        wrapper = tmp_path / "tex-sandbox.sh"
        wrapper.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        return str(wrapper)

    monkeypatch.setattr(compile_env, "_detect_sandbox_tool_with_notes", detect_once)
    monkeypatch.setattr(compile_env, "ensure_bootstrap_script", lambda cwd: None)
    monkeypatch.setattr(compile_env, "ensure_sandbox_wrapper", fake_ensure)

    report = compile_env.inspect_compile_environment(tmp_path)

    assert probe_calls == 1
    assert wrapper_calls == [(tmp_path, "/usr/bin/bwrap")]
    assert report.sandbox_tool == "/usr/bin/bwrap"
    assert report.sandbox_wrapper_path == f'["{tmp_path / "tex-sandbox.sh"}"]'
    assert report.auto_configured_wrapper is True
    assert report.ready_for_compile is True


def test_ensure_sandbox_wrapper_accepts_pre_detected_tool_without_reprobing(monkeypatch, tmp_path: Path) -> None:
    def fail_if_called() -> str | None:
        raise AssertionError("detect_sandbox_tool should not be called when tool_path is supplied")

    monkeypatch.setattr(compile_env, "detect_sandbox_tool", fail_if_called)

    wrapper = compile_env.ensure_sandbox_wrapper(tmp_path, tool_path="/usr/bin/firejail")

    assert wrapper == str(tmp_path.resolve() / ".paper-orchestra" / "tools" / "tex-sandbox.sh")
    wrapper_path = Path(wrapper)
    assert wrapper_path.exists()
    assert "/usr/bin/firejail --quiet" in wrapper_path.read_text(encoding="utf-8")


def test_compile_env_reexports_sandbox_helpers_from_focused_module() -> None:
    from paperorchestra.runtime import compile_sandbox

    assert compile_env.SANDBOX_TOOLS is compile_sandbox.SANDBOX_TOOLS
    assert compile_env.detect_sandbox_tool is compile_sandbox.detect_sandbox_tool
    assert compile_env._detect_sandbox_tool_with_notes is compile_sandbox._detect_sandbox_tool_with_notes
    assert compile_env._sandbox_probe_command is compile_sandbox._sandbox_probe_command
    assert compile_env._sandbox_tool_usable is compile_sandbox._sandbox_tool_usable
    assert compile_env._wrapper_script_contents is compile_sandbox._wrapper_script_contents
    assert compile_env._write_sandbox_wrapper is compile_sandbox._write_sandbox_wrapper
    assert compile_env.ensure_sandbox_wrapper is not compile_sandbox.ensure_sandbox_wrapper


def test_compile_env_sandbox_wrapper_preserves_facade_monkeypatch_semantics(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(compile_env, "detect_sandbox_tool", lambda: "/usr/bin/firejail")

    wrapper = compile_env.ensure_sandbox_wrapper(tmp_path)

    assert wrapper is not None
    assert "/usr/bin/firejail --quiet" in Path(wrapper).read_text(encoding="utf-8")
