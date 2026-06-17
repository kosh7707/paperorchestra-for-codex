from __future__ import annotations

import json
from pathlib import Path

from paperorchestra.loop_engine.quality import actions
from paperorchestra.loop_engine.quality import action_core
from paperorchestra.loop_engine.quality.action_families import validation as validation_family
from paperorchestra.loop_engine.quality.policy import AUTO_REPAIR_CODES, SEMI_AUTO_REPAIR_CODES


def test_quality_actions_facade_reexports_validation_family_helpers() -> None:
    assert actions._action is action_core._action
    assert actions.AUTO_REPAIR_CODES is AUTO_REPAIR_CODES
    assert actions.SEMI_AUTO_REPAIR_CODES is SEMI_AUTO_REPAIR_CODES
    assert actions._commands_for_validation_issue is validation_family._commands_for_validation_issue
    assert actions._claim_safety_approval is validation_family._claim_safety_approval
    assert actions._validation_actions is validation_family._validation_actions
    assert actions._strict_content_actions is validation_family._strict_content_actions


def test_validation_actions_build_section_scoped_commands_and_approval(tmp_path: Path) -> None:
    report = tmp_path / "validation.json"
    report.write_text(
        json.dumps(
            {
                "stage": "intro_related",
                "issues": [
                    {
                        "code": "unsupported_comparative_claim",
                        "severity": "warning",
                        "message": "Unsupported comparison.",
                    },
                    {
                        "code": "unsupported_comparative_claim",
                        "severity": "warning",
                        "message": "Duplicate should collapse.",
                    },
                    {"code": "ignored_info", "severity": "info", "message": "ignored"},
                ],
            }
        ),
        encoding="utf-8",
    )

    produced = validation_family._validation_actions({"validation_warning_reports": [{"path": str(report)}]})

    assert len(produced) == 1
    action = produced[0]
    assert action["code"] == "unsupported_comparative_claim"
    assert action["automation"] == "semi_auto"
    assert action["target"] == "Introduction, Related Work"
    assert "write-sections --only-sections" in " ".join(action["suggested_commands"])
    assert action["approval_required_from"] == "citation_support_critic"
    assert "Softening or deleting" in action["why_not_automatic"]


def test_strict_content_actions_classify_figure_warnings_as_human_needed() -> None:
    produced = validation_family._strict_content_actions(
        {
            "strict_content_gate_issues": [
                {
                    "code": "figure_tail_clump",
                    "kind": "figure_placement_warning",
                    "source": "figure-review.json",
                    "message": "Several figures are clumped at the end.",
                    "stage": "refinement",
                }
            ]
        }
    )

    assert produced[0]["automation"] == "human_needed"
    assert produced[0]["source"] == "figure-review.json"
    assert produced[0]["target"] == "refinement"
    assert produced[0]["approval_required_from"] == "figure_placement_review_critic"
    assert "cannot safely auto-commit" in produced[0]["why_not_automatic"]


def test_strict_content_actions_regenerate_stale_validation_reports_automatically() -> None:
    produced = validation_family._strict_content_actions(
        {
            "strict_content_gate_issues": [
                {
                    "code": "validation_report_stale",
                    "source": "validation.json",
                    "message": "Validation report is stale.",
                }
            ]
        }
    )

    assert produced[0]["automation"] == "automatic"
    assert produced[0]["code"] == "validation_report_stale"
    assert produced[0]["suggested_commands"] == [
        "paperorchestra quality-gate --no-fail-on-block",
        "paperorchestra quality-gate --no-fail-on-block",
        "paperorchestra qa-loop --quality-mode claim_safe",
    ]
