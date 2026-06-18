from __future__ import annotations

from paperorchestra.orchestra.reference_audit_builder import build_reference_metadata_audit


def test_reference_metadata_audit_redacts_seed_labels_and_flags_unknown_fields(tmp_path) -> None:
    seed = tmp_path / "refs.bib"
    seed.write_text(
        """
@inproceedings{Known2024,
  title={Known Paper},
  author={Alice and Bob},
  year={2024},
  booktitle={Conf}
}
@article{Unknown2025,
  title={TBD},
  author={Anonymous},
  journal={Journal}
}
""",
        encoding="utf-8",
    )

    audit = build_reference_metadata_audit(tmp_path)
    public = audit.to_public_dict()

    assert public["status"] == "fail"
    assert public["seed_file_count"] == 1
    assert public["entry_count"] == 2
    assert public["unknown_entry_count"] == 1
    assert public["failing_codes"] == ["reference_metadata_unknown_fields"]
    assert public["seed_file_labels"][0].startswith("redacted-reference-seed:")
    assert public["entries"][0]["key_label"].startswith("redacted-reference:")
    assert "Known2024" not in str(public)


def test_reference_metadata_audit_reports_missing_seed() -> None:
    audit = build_reference_metadata_audit("/path/that/does/not/exist")

    assert audit.status == "fail"
    assert audit.failing_codes == ["reference_metadata_seed_missing"]
    assert audit.to_public_dict()["private_safe_summary"] is True
