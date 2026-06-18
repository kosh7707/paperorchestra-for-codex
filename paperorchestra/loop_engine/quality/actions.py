from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.quality.action_core import _action


def _citation_actions(reproducibility: dict[str, Any]) -> list[dict[str, Any]]:
    issues = reproducibility.get("citation_artifact_issues") or []
    if not issues:
        return []
    return [
        _action(
            action_id="citation-artifacts:1",
            code="citation_artifact_health",
            source=reproducibility.get("source_artifacts", {}).get("citation_registry_json"),
            target="citation lane",
            automation="automatic",
            reason="Final citation artifacts are empty, malformed, or inconsistent: " + "; ".join(str(item) for item in issues),
            suggested_commands=[
                "paperorchestra run --provider shell --discovery-mode search-grounded",
                "paperorchestra quality-gate --no-fail-on-block",
            ],
            ralph_instruction="Rebuild or re-import the citation lane before attempting more prose refinement; do not accept a manuscript with empty or malformed citation artifacts.",
        )
    ]

def _dedupe_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None, str | None]] = set()
    for action in actions:
        key = (str(action.get("code")), action.get("target"), action.get("source"))
        if key in seen:
            continue
        seen.add(key)
        action = dict(action)
        action["id"] = f"repair-{len(deduped)+1:02d}"
        deduped.append(action)
    return deduped
