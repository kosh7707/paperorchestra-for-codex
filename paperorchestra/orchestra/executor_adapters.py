from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.orchestra.claims import build_claim_graph_from_materials
from paperorchestra.orchestra.executor_policy import FAKE_SUPPORTED_ACTIONS, LOCAL_SUPPORTED_ACTIONS
from paperorchestra.orchestra.executor_records import ExecutionRecord
from paperorchestra.orchestra.materials import build_material_inventory, build_source_digest
from paperorchestra.orchestra.scorecard import build_scorecard_summary
from paperorchestra.orchestra.state import NextAction, OrchestraState


class FakeActionExecutor:
    adapter_name = "fake"

    def execute(self, action: NextAction, state: OrchestraState) -> ExecutionRecord:
        if action.action_type not in FAKE_SUPPORTED_ACTIONS:
            return ExecutionRecord(
                action_type=action.action_type,
                reason=action.reason,
                status="unsupported",
                adapter=self.adapter_name,
                evidence_refs=[],
                state_rebuild_required=False,
            )
        return ExecutionRecord(
            action_type=action.action_type,
            reason=action.reason,
            status="executed_fake",
            adapter=self.adapter_name,
            evidence_refs=[
                {
                    "kind": "fake_action_execution",
                    "payload": {
                        "action_type": action.action_type,
                        "reason": action.reason,
                        "state_rebuild_required": True,
                        "private_safe": True,
                    },
                }
            ],
            state_rebuild_required=True,
        )


class LocalActionExecutor:
    adapter_name = "local"

    def __init__(self, *, material_path: str | Path | None = None) -> None:
        self.material_path = Path(material_path).resolve() if material_path is not None else None

    def execute(self, action: NextAction, state: OrchestraState) -> ExecutionRecord:
        if action.action_type not in LOCAL_SUPPORTED_ACTIONS:
            reason = "material_input_required" if action.action_type == "provide_material" else action.reason
            return ExecutionRecord(
                action_type=action.action_type,
                reason=reason,
                status="unsupported",
                adapter=self.adapter_name,
                evidence_refs=[],
                state_rebuild_required=False,
            )
        if action.action_type == "build_scoring_bundle":
            return self._executed(action, [{"kind": "scorecard_summary", "payload": build_scorecard_summary(state)}])

        material = self._material_path()
        if material is None:
            return self._blocked(action, "material_path_missing")

        inventory = build_material_inventory(material)
        inventory_ref = {"kind": "material_inventory", "payload": inventory.to_public_dict()}
        if action.action_type == "inspect_material":
            return self._executed(action, [inventory_ref])

        digest = build_source_digest(inventory)
        digest_ref = {"kind": "source_digest", "payload": digest.to_public_dict()}
        if action.action_type == "build_source_digest":
            return self._executed(action, [inventory_ref, digest_ref])

        if action.action_type == "build_claim_graph":
            return self._build_claim_graph_record(action, material, inventory, digest, [inventory_ref, digest_ref])

        return ExecutionRecord(
            action_type=action.action_type,
            reason=action.reason,
            status="unsupported",
            adapter=self.adapter_name,
            evidence_refs=[],
            state_rebuild_required=False,
        )

    def _material_path(self) -> Path | None:
        if self.material_path is None or not self.material_path.exists():
            return None
        return self.material_path

    def _build_claim_graph_record(
        self,
        action: NextAction,
        material: Path,
        inventory: Any,
        digest: Any,
        evidence_refs: list[dict[str, Any]],
    ) -> ExecutionRecord:
        if not digest.sufficient:
            return self._blocked(action, "source_digest_not_ready", evidence_refs)
        report = build_claim_graph_from_materials(material, inventory, digest)
        report_ref = {"kind": "claim_graph", "payload": report.to_public_dict()}
        return ExecutionRecord(
            action_type=action.action_type,
            reason=action.reason if report.ready else "claim_graph_not_ready",
            status="executed_local" if report.ready else "blocked",
            adapter=self.adapter_name,
            evidence_refs=[*evidence_refs, report_ref],
            state_rebuild_required=True,
        )

    def _executed(self, action: NextAction, evidence_refs: list[dict[str, Any]]) -> ExecutionRecord:
        return ExecutionRecord(
            action_type=action.action_type,
            reason=action.reason,
            status="executed_local",
            adapter=self.adapter_name,
            evidence_refs=evidence_refs,
            state_rebuild_required=True,
        )

    def _blocked(
        self,
        action: NextAction,
        reason: str,
        evidence_refs: list[dict[str, Any]] | None = None,
    ) -> ExecutionRecord:
        return ExecutionRecord(
            action_type=action.action_type,
            reason=reason,
            status="blocked",
            adapter=self.adapter_name,
            evidence_refs=list(evidence_refs or []),
            state_rebuild_required=False,
        )
