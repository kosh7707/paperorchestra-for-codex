from __future__ import annotations

from paperorchestra.orchestra.verifier_records import VerifierChecklistItem


def _item(item_id: str, status: str, reason: str, *refs: dict[str, str]) -> VerifierChecklistItem:
    return VerifierChecklistItem(id=item_id, status=status, reason=reason, evidence_refs=list(refs), private_safe=True)


def _safe_ref(kind: str, path: str) -> dict[str, str]:
    return {"kind": kind, "path": path}
