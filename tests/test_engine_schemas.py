from __future__ import annotations

import pytest

from paperorchestra.core.errors import ContractError
from paperorchestra.engine.schema_outline import OUTLINE_SCHEMA, normalize_outline_payload, validate_outline
from paperorchestra.engine.schema_plot import PLOT_SCHEMA, validate_plot_manifest
from paperorchestra.engine.schema_research import CANDIDATE_SCHEMA, PRIOR_WORK_SEED_SCHEMA
from paperorchestra.engine.schema_review import REVIEW_SCHEMA


def test_outline_normalization_preserves_schema_contract() -> None:
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

    normalized = normalize_outline_payload(payload)

    item = normalized["plotting_plan"][0]
    assert item["plot_type"] == "diagram"
    assert item["aspect_ratio"] == "16:9"
    assert "Original requested chart form: flow diagram." in item["objective"]


def test_outline_validation_rejects_invalid_plot_values() -> None:
    with pytest.raises(ContractError, match="Invalid plot_type"):
        validate_outline(
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
        validate_plot_manifest(
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


def test_pipeline_schema_constants_are_available_from_owner_modules() -> None:
    assert OUTLINE_SCHEMA["type"] == "object"
    assert PLOT_SCHEMA["properties"]["figures"]["type"] == "array"
    assert "macro_candidates" in CANDIDATE_SCHEMA["properties"]
    assert "references" in PRIOR_WORK_SEED_SCHEMA["properties"]
    assert "overall_score" in REVIEW_SCHEMA["properties"]
