from __future__ import annotations

import json
from pathlib import Path

from paperorchestra.feedback import packet_bindings


def test_artifact_bound_manuscript_sha_reads_known_role_shapes() -> None:
    assert packet_bindings._normalized_sha("sha256:" + "a" * 64) == "a" * 64
    assert packet_bindings._artifact_bound_manuscript_sha("citation_support_review", {"manuscript_sha256": "sha256:" + "b" * 64}) == "b" * 64
    assert packet_bindings._artifact_bound_manuscript_sha("quality_eval", {"manuscript_hash": "sha256:" + "c" * 64}) == "c" * 64
    assert packet_bindings._artifact_bound_manuscript_sha(
        "qa_loop_plan",
        {"quality_eval_summary": {"manuscript_hash": "sha256:" + "d" * 64}},
    ) == "d" * 64
    assert packet_bindings._artifact_bound_manuscript_sha(
        "qa_loop_execution",
        {"candidate_approval": {"base_manuscript_sha256": "sha256:" + "e" * 64}},
    ) == "e" * 64
    assert packet_bindings._artifact_bound_manuscript_sha(
        "operator_feedback_execution",
        {"candidate_result": {"candidate_approval": {"base_manuscript_sha256": "sha256:" + "f" * 64}}},
    ) == "f" * 64


def test_artifact_payload_reads_dict_only(tmp_path: Path) -> None:
    payload_path = tmp_path / "payload.json"
    payload_path.write_text('{"ok": true}', encoding="utf-8")
    list_path = tmp_path / "list.json"
    list_path.write_text('[1, 2]', encoding="utf-8")

    assert packet_bindings._artifact_payload({"path": str(payload_path)}) == {"ok": True}
    assert packet_bindings._artifact_payload({"path": str(list_path)}) is None
    assert packet_bindings._artifact_payload({"path": str(tmp_path / "missing.json")}) is None


def test_execution_payload_sha256_ignores_embedded_source_execution_sha() -> None:
    execution = {
        "verdict": "human_needed",
        "candidate_approval": {
            "source_execution_sha256": "sha256:old",
            "candidate_sha256": "sha256:candidate",
        },
    }
    changed = json.loads(json.dumps(execution))
    changed["candidate_approval"]["source_execution_sha256"] = "sha256:new"

    assert packet_bindings._execution_payload_sha256(execution) == packet_bindings._execution_payload_sha256(changed)
    assert packet_bindings._execution_payload_sha256(execution).startswith("sha256:")
