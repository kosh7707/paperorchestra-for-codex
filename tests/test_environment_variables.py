from __future__ import annotations

from paperorchestra.runtime.environment_variables import (
    ENVIRONMENT_VARIABLES,
    grouped_environment_variables,
    operator_environment_variable_names,
)


def test_environment_variable_catalog_grouping_and_order() -> None:
    groups = grouped_environment_variables()

    assert [group["category"] for group in groups] == ["core_runtime", "shell_provider", "verification", "compile"]
    assert len(ENVIRONMENT_VARIABLES) == 30
    assert operator_environment_variable_names()[0] == "PAPERO_OMX_MODEL"
    assert operator_environment_variable_names()[-1] == "TEXINPUTS"


def test_environment_variable_catalog_keeps_required_run_controls() -> None:
    specs = {spec.name: spec for spec in ENVIRONMENT_VARIABLES}

    assert len(specs) == len(ENVIRONMENT_VARIABLES)
    assert "full_live_run_ready" in specs["PAPERO_MODEL_CMD"].required_for
    assert "claim_safe_full_run_ready" in specs["PAPERO_ALLOW_TEX_COMPILE"].required_for
    assert specs["SEMANTIC_SCHOLAR_API_KEY"].category == "verification"
