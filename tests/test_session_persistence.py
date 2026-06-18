from __future__ import annotations

from pathlib import Path

import pytest

from paperorchestra.core.models import InputBundle
from paperorchestra.core.session import create_session, load_session, save_session


def _write_inputs(root: Path) -> InputBundle:
    root.mkdir(parents=True, exist_ok=True)
    idea = root / "idea.md"
    log = root / "log.md"
    template = root / "template.tex"
    guidelines = root / "guidelines.md"
    for path, text in (
        (idea, "idea"),
        (log, "experiment"),
        (template, "\\documentclass{llncs}"),
        (guidelines, "guidelines"),
    ):
        path.write_text(text, encoding="utf-8")
    return InputBundle(
        idea_path=str(idea),
        experimental_log_path=str(log),
        template_path=str(template),
        guidelines_path=str(guidelines),
    )


def test_create_session_snapshots_workspace_inputs(tmp_path: Path) -> None:
    inputs = _write_inputs(tmp_path / "materials")

    state = create_session(tmp_path, inputs)

    snapped_idea = Path(state.inputs.idea_path)
    assert snapped_idea.name == "idea.md"
    assert snapped_idea.read_text(encoding="utf-8") == "idea"
    assert tmp_path / ".paper-orchestra" / "runs" / state.session_id in snapped_idea.parents


def test_create_session_rejects_outside_workspace_inputs_by_default(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    outside_inputs = _write_inputs(tmp_path / "outside")

    with pytest.raises(ValueError, match="outside the workspace"):
        create_session(workspace, outside_inputs)


def test_save_session_preserves_existing_runtime_trace_fields(tmp_path: Path) -> None:
    state = create_session(tmp_path, _write_inputs(tmp_path / "materials"))
    trace_dir = tmp_path / "trace"
    trace_dir.mkdir()
    provider_identity = tmp_path / "provider.json"
    provider_identity.write_text("{}", encoding="utf-8")
    state.artifacts.latest_prompt_trace_dir = str(trace_dir)
    state.artifacts.latest_provider_identity_json = str(provider_identity)
    state.latest_provider_name = "provider-a"
    state.latest_runtime_mode = "live"
    save_session(tmp_path, state)

    incoming = load_session(tmp_path)
    incoming.artifacts.latest_prompt_trace_dir = None
    incoming.artifacts.latest_provider_identity_json = None
    incoming.latest_provider_name = None
    incoming.latest_runtime_mode = None
    save_session(tmp_path, incoming)

    saved = load_session(tmp_path)
    assert saved.artifacts.latest_prompt_trace_dir == str(trace_dir)
    assert saved.artifacts.latest_provider_identity_json == str(provider_identity)
    assert saved.latest_provider_name == "provider-a"
    assert saved.latest_runtime_mode == "live"
