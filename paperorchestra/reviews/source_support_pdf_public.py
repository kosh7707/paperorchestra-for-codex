from __future__ import annotations

from typing import Any


def _public_pdf_candidate_decisions(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    public: list[dict[str, Any]] = []
    for item in candidates:
        row = {
            "url": str(item.get("url") or ""),
            "decision": str(item.get("decision") or ""),
            "reason": str(item.get("reason") or ""),
        }
        if item.get("final_url"):
            row["final_url"] = str(item.get("final_url"))
        public.append(row)
    return public
