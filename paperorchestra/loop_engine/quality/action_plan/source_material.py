from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.quality.action_core import _action


def _append_source_material_fidelity_actions(actions: list[dict[str, Any]], source_check: Any) -> None:
    if not (isinstance(source_check, dict) and source_check.get("status") == "fail"):
        return

    actions.append(
        _action(
            action_id="quality-eval:source-material-fidelity",
            code="source_material_coverage_insufficient",
            source=None,
            target="source-material fidelity",
            automation="semi_auto",
            reason="The manuscript omits required proof/results material that appears in the source packet or experiment log.",
            suggested_commands=[
                "paperorchestra write-sections",
                "paperorchestra critique",
                "paperorchestra critique --citation-evidence-mode web",
                "paperorchestra qa-loop --quality-mode claim_safe",
            ],
            ralph_instruction="Run one bounded evidence-backed rewrite/refinement pass that restores omitted proof or benchmark material without inventing new facts.",
            why_not_automatic="Restoring omitted technical content changes manuscript substance; the candidate must pass source-material, section, citation, validation, and compile critics.",
            approval_required_from="source_material_critic",
        )
    )


def _append_source_obligation_actions(actions: list[dict[str, Any]], obligation_check: Any) -> None:
    if not isinstance(obligation_check, dict):
        return

    obligation_codes = {str(code) for code in obligation_check.get("failing_codes") or []}
    if obligation_codes & {"source_obligations_missing", "source_obligations_stale", "source_obligations_legacy_untrusted"}:
        code = "source_obligations_stale" if "source_obligations_stale" in obligation_codes else "source_obligations_missing"
        actions.append(
            _action(
                action_id=f"quality-eval:{code}",
                code=code,
                source=obligation_check.get("path"),
                target="source obligations",
                automation="automatic",
                reason="Claim-safe source-material fidelity requires a current source-obligations matrix for the session input packet.",
                suggested_commands=["paperorchestra quality-gate --no-fail-on-block", "paperorchestra qa-loop --quality-mode claim_safe"],
                ralph_instruction="Regenerate source_obligations.json from the current snapshotted input packet before continuing claim-safe evaluation.",
            )
        )
    if obligation_codes & {"source_obligation_missing", "source_obligation_anchor_missing", "source_obligation_numeric_mismatch"}:
        actions.append(
            _action(
                action_id="quality-eval:source-obligation-satisfaction",
                code="source_material_coverage_insufficient",
                source=obligation_check.get("path"),
                target="source-material fidelity",
                automation="semi_auto",
                reason="The manuscript does not satisfy one or more source-material obligations.",
                suggested_commands=["paperorchestra write-sections", "paperorchestra critique", "paperorchestra qa-loop --quality-mode claim_safe"],
                ralph_instruction="Run one bounded evidence-backed rewrite/refinement pass that satisfies the missing source obligations without inventing new facts.",
                why_not_automatic="Filling missing source obligations changes manuscript substance and must be checked by source/material critics.",
                approval_required_from="source_material_critic",
            )
        )
