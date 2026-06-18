from __future__ import annotations

import json
from pathlib import Path

import pytest

from paperorchestra.orchestra.evidence import write_orchestrator_evidence_bundle
from paperorchestra.orchestra.state import OrchestraState


def test_evidence_bundle_redacts_private_payloads_and_workspace_paths(tmp_path: Path) -> None:
    state = OrchestraState.new(cwd=tmp_path)
    state.evidence_refs = [
        {
            "kind": "Private Prompt",
            "payload": {
                "raw_text": "secret",
                "path": str(tmp_path / "artifacts" / "trace.json"),
                "nested": {"private_note": "secret", "private_safe": True},
            },
        }
    ]

    result = write_orchestrator_evidence_bundle(tmp_path, state, output_dir="bundle")

    assert result["evidence_count"] == 1
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    evidence_path = Path(result["output_dir"]) / manifest["evidence"][0]["path"]
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    payload = evidence["payload"]
    assert payload["raw_text"] == "<redacted>"
    assert payload["path"] == "artifacts/trace.json"
    assert payload["nested"] == {"private_note": "<redacted>", "private_safe": True}


def test_evidence_bundle_rejects_output_outside_workspace(tmp_path: Path) -> None:
    state = OrchestraState.new(cwd=tmp_path)

    with pytest.raises(ValueError, match="under the current workspace"):
        write_orchestrator_evidence_bundle(tmp_path, state, output_dir=tmp_path.parent / "outside")
