from __future__ import annotations

import json
from pathlib import Path

import pytest

from paperorchestra.core.errors import ContractError
from paperorchestra.feedback import packet_artifacts, packets


def test_packets_facade_reexports_packet_artifact_helpers() -> None:
    assert packets._sha256_bytes is packet_artifacts._sha256_bytes
    assert packets._file_sha256 is packet_artifacts._file_sha256
    assert packets._sha256_digest is packet_artifacts._sha256_digest
    assert packets._sha256_prefixed is packet_artifacts._sha256_prefixed
    assert packets._canonical_sha256 is packet_artifacts._canonical_sha256
    assert packets._packet_sha256 is packet_artifacts._packet_sha256
    assert packets._artifact_record is packet_artifacts._artifact_record
    assert packets._snapshot_operator_packet_artifacts is packet_artifacts._snapshot_operator_packet_artifacts


def test_artifact_record_requires_existing_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"

    assert packet_artifacts._artifact_record("optional", missing) is None
    with pytest.raises(ContractError, match="required operator review artifact is missing"):
        packet_artifacts._artifact_record("required", missing, required=True)

    artifact = tmp_path / "artifact.json"
    artifact.write_text('{"ok": true}', encoding="utf-8")
    record = packet_artifacts._artifact_record("quality_eval", artifact, required=True)

    assert record is not None
    assert record["role"] == "quality_eval"
    assert record["path"] == str(artifact.resolve())
    assert record["sha256"] == packet_artifacts._file_sha256(artifact)
    assert record["size_bytes"] == artifact.stat().st_size


def test_snapshot_operator_packet_artifacts_freezes_artifacts_next_to_packet(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"version": 1}), encoding="utf-8")
    digest = packet_artifacts._file_sha256(source)
    packet_path = tmp_path / "operator_review_packet.json"

    frozen = packet_artifacts._snapshot_operator_packet_artifacts(
        packet_path,
        [{"role": "qa_loop_execution", "path": str(source), "sha256": digest}],
    )

    assert len(frozen) == 1
    record = frozen[0]
    snapshot = Path(record["snapshot_path"])
    assert snapshot.exists()
    assert snapshot.parent == tmp_path / "operator_review_packet.artifacts"
    assert record["original_path"] == str(source.resolve())
    assert record["path"] == str(snapshot.resolve())
    assert record["sha256"] == digest
    assert packet_artifacts._file_sha256(snapshot) == digest


def test_packet_sha256_ignores_existing_packet_hash() -> None:
    left = {"a": 1, "packet_sha256": "old"}
    right = {"a": 1, "packet_sha256": "new"}

    assert packet_artifacts._packet_sha256(left) == packet_artifacts._packet_sha256(right)
    assert packet_artifacts._sha256_prefixed("sha256:abc") == "sha256:abc"
    assert packet_artifacts._sha256_prefixed("abc") == "sha256:abc"
