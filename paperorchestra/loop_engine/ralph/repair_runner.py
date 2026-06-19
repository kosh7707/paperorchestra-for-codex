from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from paperorchestra.loop_engine.ralph.repair_candidate import build_repair_candidate
from paperorchestra.runtime.provider_base import BaseProvider


@dataclass
class CitationClaimRepairRunner:
    cwd: str | Path | None
    provider: BaseProvider
    stage: Any
    citation_review_path: str | Path | None = None
    runtime_mode: str = "compatibility"
    require_compile: bool = False
    commit: bool = False
    state: Any = field(init=False)
    mutation_snapshot: dict[str, Any] = field(init=False)
    paper_path: Path = field(init=False)
    original: str = field(init=False)
    citation_map: dict[str, Any] = field(init=False, default_factory=dict)
    issues: list[dict[str, Any]] = field(init=False, default_factory=list)
    claim_safety_issues: list[dict[str, Any]] = field(init=False, default_factory=list)
    result: dict[str, Any] = field(init=False, default_factory=dict)

    def run(self) -> dict[str, Any]:
        self.stage.recover_pending_manuscript_write(self.cwd)
        self.state = self.stage.load_session(self.cwd)
        if not self.state.artifacts.paper_full_tex:
            raise self.stage.ContractError("Need paper.full.tex before repairing citation claims.")

        self.mutation_snapshot = self.stage._session_mutation_snapshot(self.state)
        review_path = self._review_path()
        citation_review = self.stage._read_json(review_path)
        if not isinstance(citation_review, dict):
            raise self.stage.ContractError(f"Citation review is not available: {review_path}")

        self.issues = self.stage._non_supported_citation_items(citation_review)
        self.claim_safety_issues = self.stage._claim_safety_repair_issues(self.cwd)
        self.result = self._initial_result(review_path)
        if not self.issues and not self.claim_safety_issues:
            self._complete("no_citation_claim_or_claim_safety_issues", accepted=True)
            return self.result

        self.paper_path = Path(self.state.artifacts.paper_full_tex)
        self.original = self.paper_path.read_text(encoding="utf-8")
        self.citation_map = self._load_citation_map()
        candidate = self._build_candidate()
        if self.result["unknown_citation_keys"]:
            self._complete("unknown_citation_keys")
            return self.result

        self.stage.guarded_replace_manuscript_text(
            self.cwd,
            self.paper_path,
            candidate,
            reason="citation_repair_candidate_validation",
            original_text=self.original,
        )
        if not self._validation_passes():
            self._restore("citation_repair_validation_failed")
            self._complete("validation_failed")
            return self.result

        if not self._semantic_recheck_passes():
            return self.result
        if self.require_compile and not self._compile_passes():
            return self.result

        self._finalize_candidate()
        return self.result

    def _review_path(self) -> Path:
        if self.citation_review_path:
            return Path(self.citation_review_path).resolve()
        return Path(self.state.artifacts.paper_full_tex).resolve().parent / "citation_support_review.json"

    def _initial_result(self, review_path: Path) -> dict[str, Any]:
        return {
            "schema_version": "citation-claim-repair/1",
            "started_at": self.stage.utc_now_iso(),
            "citation_review": str(review_path),
            "issue_count": len(self.issues),
            "claim_safety_issue_count": len(self.claim_safety_issues),
            "accepted": False,
            "reason": None,
        }

    def _load_citation_map(self) -> dict[str, Any]:
        raw = self.stage._read_json(self.state.artifacts.citation_map_json) if self.state.artifacts.citation_map_json else {}
        return raw if isinstance(raw, dict) else {}

    def _build_candidate(self) -> str:
        candidate, metadata = build_repair_candidate(
            stage=self.stage,
            cwd=self.cwd,
            provider=self.provider,
            runtime_mode=self.runtime_mode,
            original=self.original,
            citation_map=self.citation_map,
            issues=self.issues,
            claim_safety_issues=self.claim_safety_issues,
        )
        self.result.update(metadata)
        return candidate

    def _validation_passes(self) -> bool:
        validation_path, validation_payload = self.stage.record_current_validation_report(
            self.cwd,
            name="validation.citation-repair.json",
        )
        self.result["validation"] = {
            "path": str(validation_path),
            "ok": validation_payload.get("ok"),
            "blocking_issue_count": validation_payload.get("blocking_issue_count"),
        }
        return bool(validation_payload.get("ok"))

    def _semantic_recheck_passes(self) -> bool:
        try:
            semantic_recheck = self.stage._candidate_semantic_recheck(
                self.cwd,
                claim_safety_issues=self.claim_safety_issues,
                original_manuscript_hash=hashlib.sha256(self.original.encode("utf-8")).hexdigest(),
            )
        except Exception as exc:
            self._restore("citation_repair_semantic_recheck_error")
            self.result["semantic_recheck"] = {"status": "error", "error_type": type(exc).__name__}
            self._complete("semantic_recheck_error")
            return False

        self.result["semantic_recheck"] = semantic_recheck
        if semantic_recheck.get("status") == "pass":
            return True
        self._restore("citation_repair_semantic_recheck_failed")
        self._complete("semantic_recheck_failed")
        return False

    def _compile_passes(self) -> bool:
        try:
            pdf_path = self.stage.compile_current_paper(self.cwd)
            self.result["compile"] = {"ok": True, "pdf": str(pdf_path)}
            return True
        except Exception as exc:
            self._restore("citation_repair_compile_failed")
            self.result["compile"] = {"ok": False, "error": str(exc)}
            self._complete("compile_failed")
            return False

    def _finalize_candidate(self) -> None:
        if not self.commit:
            self._restore("citation_repair_uncommitted_candidate_restored")
        else:
            self.stage.clear_pending_manuscript_write(
                self.cwd,
                status="resolved",
                reason="citation_repair_candidate_committed",
            )
        state = self.stage.load_session(self.cwd)
        state.notes.append(
            "Citation-claim repair candidate accepted."
            + (" Committed." if self.commit else " Awaiting citation-support approval.")
        )
        self.stage.save_session(self.cwd, state)
        self.result.update({"accepted": True, "committed": self.commit})
        self._complete("accepted")

    def _restore(self, reason: str) -> None:
        self.stage.atomic_write_text(self.paper_path, self.original)
        self.stage.clear_pending_manuscript_write(self.cwd, status="restored", reason=reason)
        self.stage._restore_session_mutation_snapshot(self.cwd, self.mutation_snapshot)

    def _complete(self, reason: str, *, accepted: bool | None = None) -> None:
        if accepted is not None:
            self.result["accepted"] = accepted
        self.result.update({"reason": reason, "completed_at": self.stage.utc_now_iso()})


__all__ = ["CitationClaimRepairRunner"]
