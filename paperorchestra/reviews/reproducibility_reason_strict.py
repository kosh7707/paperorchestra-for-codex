from __future__ import annotations

from paperorchestra.reviews.reproducibility_context import ReproducibilityAuditContext


def append_strict_content_blockers(blocking: list[str], context: ReproducibilityAuditContext) -> None:
    if not (context.strict_content_gates and context.strict_content_gate_issues):
        return
    codes = ", ".join(sorted({str(issue.get("code")) for issue in context.strict_content_gate_issues}))
    blocking.append(f"Strict content gates blocked warning code(s): {codes}.")
