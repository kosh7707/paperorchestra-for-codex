from __future__ import annotations

from paperorchestra.orchestra.draft_control_evaluation import DraftControlEvaluation
from paperorchestra.orchestra.draft_control_models import DraftControlDecision, DraftControlInput


class DraftControlPolicy:
    def evaluate(self, inputs: DraftControlInput) -> DraftControlDecision:
        return DraftControlEvaluation(inputs).run()
