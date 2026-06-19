from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paperorchestra.interfaces.mcp import authoring_tools


class _FakeProc:
    pid = 424242

    def __init__(self) -> None:
        self.wait_called = False

    def wait(self) -> int:
        self.wait_called = True
        return 0


def test_authoring_round_auto_backgrounds_live_web_requests(tmp_path: Path, monkeypatch) -> None:
    def fail_sync(*args: Any, **kwargs: Any) -> None:  # pragma: no cover - assertion path
        raise AssertionError("live/web MCP authoring should not block synchronously")

    captured: dict[str, Any] = {}
    fake_proc = _FakeProc()

    def fake_popen(argv: list[str], **kwargs: Any) -> _FakeProc:
        captured["argv"] = argv
        captured["cwd"] = kwargs["cwd"]
        captured["start_new_session"] = kwargs["start_new_session"]
        captured["stdout_closed_before_return"] = kwargs["stdout"].closed
        return fake_proc

    class InlineThread:
        def __init__(self, *, target: Any, name: str, daemon: bool) -> None:
            captured["thread_name"] = name
            captured["thread_daemon"] = daemon
            self._target = target

        def start(self) -> None:
            self._target()

    monkeypatch.setattr(authoring_tools, "run_authoring_round", fail_sync)
    monkeypatch.setattr(authoring_tools.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(authoring_tools.threading, "Thread", InlineThread)

    result = authoring_tools.tool_authoring_round(
        {
            "cwd": str(tmp_path),
            "provider": "shell",
            "provider_command": '["codex","--search","exec","--skip-git-repo-check"]',
            "runtime_mode": "omx_native",
            "require_web_research": True,
            "require_live_critic": True,
            "citation_evidence_mode": "web",
        }
    )

    payload = json.loads(result["content"][0]["text"])
    assert payload["status"] == "started"
    assert payload["mode"] == "background"
    assert payload["pid"] == 424242
    assert payload["cwd"] == str(tmp_path.resolve())
    assert payload["stdout"].endswith(".stdout.json")
    assert payload["stderr"].endswith(".stderr.log")
    assert Path(payload["metadata"]).exists()
    assert captured["cwd"] == tmp_path.resolve()
    assert captured["start_new_session"] is True
    assert captured["thread_name"] == "paperorchestra-mcp-job-424242"
    assert captured["thread_daemon"] is True
    assert fake_proc.wait_called is True
    assert captured["argv"][:3] == [authoring_tools.sys.executable, "-m", "paperorchestra.cli"]
    assert "--require-web-research" in captured["argv"]
    assert "--require-live-critic" in captured["argv"]
    assert "--provider-command" in captured["argv"]


def test_authoring_round_background_can_be_disabled_for_fast_sync_calls(tmp_path: Path, monkeypatch) -> None:
    def fake_sync(cwd: Path, provider: Any, **kwargs: Any) -> dict[str, Any]:
        return {"status": "completed_with_critic", "cwd": str(cwd), "require_web_research": kwargs["require_web_research"]}

    monkeypatch.setattr(authoring_tools, "run_authoring_round", fake_sync)

    result = authoring_tools.tool_authoring_round(
        {
            "cwd": str(tmp_path),
            "provider": "mock",
            "background": False,
            "require_web_research": True,
            "skip_literature": True,
            "citation_evidence_mode": "heuristic",
        }
    )

    payload = json.loads(result["content"][0]["text"])
    assert payload == {"status": "completed_with_critic", "cwd": str(tmp_path.resolve()), "require_web_research": True}


def test_authoring_round_cli_argv_preserves_mcp_options() -> None:
    argv = authoring_tools._authoring_round_cli_argv(
        {
            "round_dir": "round-x",
            "only_sections": ["Introduction", "Methodology"],
            "output_path": "paper.tex",
            "claim_safe": True,
            "bypass_plan_gate": True,
            "skip_literature": True,
            "no_import_literature": True,
            "require_complete_metadata": True,
            "require_web_research": True,
            "skip_critic": True,
            "require_live_critic": True,
            "compile_paper": True,
            "runtime_mode": "omx_native",
            "strict_omx_native": True,
            "provider": "shell",
            "provider_command": '["codex","--search","exec"]',
            "citation_provider": "shell",
            "citation_provider_command": '["codex","--search","exec"]',
        },
        evidence_mode="web",
    )

    assert argv[:3] == [authoring_tools.sys.executable, "-m", "paperorchestra.cli"]
    assert ["--only-sections", "Introduction,Methodology"] == argv[argv.index("--only-sections") : argv.index("--only-sections") + 2]
    for flag in (
        "--claim-safe",
        "--bypass-plan-gate",
        "--skip-literature",
        "--no-import-literature",
        "--require-complete-metadata",
        "--require-web-research",
        "--skip-critic",
        "--require-live-critic",
        "--compile",
        "--strict-omx-native",
    ):
        assert flag in argv
