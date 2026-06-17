from __future__ import annotations

from paperorchestra.loop_engine.quality import actions
from paperorchestra.loop_engine.quality.action_families import reproducibility


def test_quality_actions_facade_reexports_reproducibility_family_helpers() -> None:
    assert actions._mode_actions is reproducibility._mode_actions
    assert actions._warning_actions is reproducibility._warning_actions
    assert actions._fidelity_actions is reproducibility._fidelity_actions


def test_mode_actions_classify_mock_provider_and_mixed_provenance() -> None:
    produced = reproducibility._mode_actions(
        {
            "blocking_reasons": [
                "Provider was mock; manuscript output is not live.",
                "One cited source has mixed cited provenance.",
            ],
            "source_artifacts": {
                "paper_full_tex": "paper.tex",
                "citation_registry_json": "registry.json",
            },
        }
    )
    by_code = {action["code"]: action for action in produced}

    assert by_code["mock_provider"]["automation"] == "human_needed"
    assert by_code["mock_provider"]["source"] == "paper.tex"
    assert by_code["mixed_citation_provenance_requires_acceptance"]["target"] == "citation provenance"
    assert "paperorchestra qa-loop --accept-mixed-provenance" in by_code["mixed_citation_provenance_requires_acceptance"]["suggested_commands"]


def test_warning_actions_ignore_non_blocking_validation_noise() -> None:
    produced = reproducibility._warning_actions(
        {
            "warning_reasons": [
                "non-blocking validation warning: ignored",
                "Latest compile report is not clean.",
                "No lane manifests were recorded.",
                "Something else needs triage.",
            ],
            "source_artifacts": {
                "latest_compile_report_json": "compile.json",
                "latest_lane_summary_json": "lanes.json",
            },
        }
    )

    assert [action["code"] for action in produced] == [
        "compile_not_clean",
        "missing_lane_manifests",
        "unclassified_reproducibility_warning",
    ]
    assert produced[0]["source"] == "compile.json"
    assert produced[1]["automation"] == "human_needed"


def test_fidelity_actions_only_emit_unimplemented_critical_checks() -> None:
    produced = reproducibility._fidelity_actions(
        {
            "checks": [
                {"code": "verified_citation_lane", "status": "missing", "rationale": "not rebuilt"},
                {"code": "runtime_parity", "status": "implemented", "rationale": "ok"},
                {"code": "unknown", "status": "missing", "rationale": "ignored"},
            ]
        }
    )

    assert len(produced) == 1
    assert produced[0]["code"] == "fidelity_verified_citation_lane_missing"
    assert produced[0]["target"] == "verified_citation_lane"
