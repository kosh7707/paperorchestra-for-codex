from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.quality.action_core import _action


def _mode_actions(reproducibility: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    reasons = [str(reason) for reason in reproducibility.get("blocking_reasons") or []]
    if any("Provider was mock" in reason for reason in reasons):
        actions.append(
            _action(
                action_id="provider-mode:1",
                code="mock_provider",
                source=reproducibility.get("source_artifacts", {}).get("paper_full_tex"),
                target="run configuration",
                automation="human_needed",
                reason="Provider was mock; manuscript output is not a live factual draft.",
                suggested_commands=["paperorchestra run --provider shell --runtime-mode omx_native"],
                ralph_instruction="Do not continue quality claims on mock output; rerun with a real provider or mark the artifact as demo-only.",
            )
        )
    if any("Citation verification used mock mode" in reason for reason in reasons):
        actions.append(
            _action(
                action_id="verification-mode:1",
                code="mock_verification",
                source=reproducibility.get("source_artifacts", {}).get("citation_registry_json"),
                target="verification lane",
                automation="human_needed",
                reason="Citation verification used mock mode.",
                suggested_commands=["paperorchestra run --provider shell --discovery-mode search-grounded", "paperorchestra quality-gate --no-fail-on-block --require-live-verification"],
                ralph_instruction="Use live verification for claim-safe runs, or stop and record that only an offline demo is available.",
            )
        )
    if any("seed-only or curated metadata without live verification" in reason for reason in reasons):
        actions.append(
            _action(
                action_id="verification-mode:2",
                code="incomplete_live_verification",
                source=reproducibility.get("source_artifacts", {}).get("citation_registry_json"),
                target="verification lane",
                automation="human_needed",
                reason="The citation registry still contains seed-only or curated metadata entries after a required live verification pass.",
                suggested_commands=[
                    "paperorchestra run --provider shell --discovery-mode search-grounded --require-live-verification",
                    "paperorchestra quality-gate --no-fail-on-block --require-live-verification",
                ],
                ralph_instruction="Do not present citation provenance as fully live until every registry entry is live-verified or explicitly removed/scoped.",
            )
        )
    if any("mixed cited provenance" in reason for reason in reasons):
        actions.append(
            _action(
                action_id="verification-mode:3",
                code="mixed_citation_provenance_requires_acceptance",
                source=reproducibility.get("source_artifacts", {}).get("citation_registry_json"),
                target="citation provenance",
                automation="human_needed",
                reason="One or more cited references have mixed cited provenance rather than live verification.",
                suggested_commands=[
                    "paperorchestra qa-loop --accept-mixed-provenance",
                    "paperorchestra quality-gate --no-fail-on-block --require-live-verification",
                ],
                ralph_instruction=(
                    "Do not treat mixed cited provenance as fully live. Either replace the affected cited references "
                    "with live-verified sources or explicitly accept the mixed provenance with an operator-owned "
                    "acceptance artifact before final readiness."
                ),
            )
        )
    if any("Prompt trace artifacts are missing" in reason for reason in reasons):
        actions.append(
            _action(
                action_id="provenance:1",
                code="missing_prompt_trace",
                source=reproducibility.get("source_artifacts", {}).get("latest_prompt_trace_dir"),
                target="provenance",
                automation="human_needed",
                reason="Prompt traces are missing, so the generation cannot be audited.",
                suggested_commands=["paperorchestra run --provider shell --runtime-mode omx_native"],
                ralph_instruction="Rerun the affected generation stage with prompt tracing enabled before accepting the draft.",
            )
        )
    return actions
