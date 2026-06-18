from __future__ import annotations

import pytest

from paperorchestra.core.errors import ContractError
from paperorchestra.engine import schemas


def test_outline_normalization_preserves_schema_facade_contract() -> None:
    payload = {
        "plotting_plan": [
            {
                "figure_id": "fig1",
                "title": "Architecture",
                "plot_type": "flow diagram",
                "data_source": "notes",
                "objective": "Explain the pipeline.",
                "aspect_ratio": "wide",
            }
        ],
        "intro_related_work_plan": {"introduction_strategy": {}, "related_work_strategy": {}},
        "section_plan": [],
    }

    normalized = schemas.normalize_outline_payload(payload)

    item = normalized["plotting_plan"][0]
    assert item["plot_type"] == "diagram"
    assert item["aspect_ratio"] == "16:9"
    assert "Original requested chart form: flow diagram." in item["objective"]


def test_outline_validation_rejects_invalid_plot_values() -> None:
    with pytest.raises(ContractError, match="Invalid plot_type"):
        schemas.validate_outline(
            {
                "plotting_plan": [
                    {
                        "figure_id": "fig1",
                        "title": "Chart",
                        "plot_type": "bar",
                        "data_source": "data",
                        "objective": "Show data.",
                        "aspect_ratio": "16:9",
                    }
                ],
                "intro_related_work_plan": {},
                "section_plan": [],
            }
        )


def test_plot_manifest_validation_rejects_missing_required_keys() -> None:
    with pytest.raises(ContractError, match="Plot manifest figure missing key: caption"):
        schemas.validate_plot_manifest(
            {
                "figures": [
                    {
                        "figure_id": "fig1",
                        "title": "Chart",
                        "plot_type": "plot",
                        "data_source": "data",
                        "objective": "Show data.",
                        "aspect_ratio": "16:9",
                        "rendering_brief": "Use bars.",
                        "source_fidelity_notes": "Derived from data.",
                    }
                ]
            }
        )


def test_schema_facade_exposes_pipeline_schema_constants() -> None:
    assert schemas.OUTLINE_SCHEMA["type"] == "object"
    assert schemas.PLOT_SCHEMA["properties"]["figures"]["type"] == "array"
    assert "macro_candidates" in schemas.CANDIDATE_SCHEMA["properties"]
    assert "references" in schemas.PRIOR_WORK_SEED_SCHEMA["properties"]
    assert "overall_score" in schemas.REVIEW_SCHEMA["properties"]
