#!/usr/bin/env python3
"""Synthetic controlled smoke for strict quality-gate hardening.

This smoke intentionally avoids live APIs. It exercises the contract surfaces
that must be green before another expensive full live smoke is useful:
process-residue detection, mixed citation scope, candidate staging, citation
review identity, and claim-safe evidence-mode defaults.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from paperorchestra.boundary import control_prose_markers
from paperorchestra.cli import main as cli_main
from paperorchestra.critics import build_citation_support_review, write_citation_support_review
from paperorchestra.models import InputBundle
from paperorchestra.operator_feedback import _candidate_hard_gate, _stage_candidate_text_for_verification
from paperorchestra.providers import BaseProvider, CompletionRequest
from paperorchestra.quality_loop_citation_support import _citation_support_check
from paperorchestra.quality_loop import append_quality_loop_history, write_quality_eval, write_quality_loop_plan
from paperorchestra.quality_loop_history import operator_feedback_cycle_count
from paperorchestra.session import artifact_path, create_session, load_session, save_session
from paperorchestra.validator import check_prompt_meta_leakage


def _require(condition: bool, label: str) -> None:
    if not condition:
        raise SystemExit(f"CONTROLLED_SMOKE_FAIL: {label}")


class FakeWebProvider(BaseProvider):
    name = "fake-web"

    def complete(self, request: CompletionRequest) -> str:
        import re

        ids = sorted(set(re.findall(r'"id":\s*"(cite-\d+)"', request.user_prompt)))
        return json.dumps(
            {
                "items": [
                    {
                        "id": item_id,
                        "support_status": "needs_manual_check",
                        "risk": "medium",
                        "claim_type": "background",
                        "evidence": [],
                        "reasoning": "Fake web provider records provenance without asserting support.",
                        "suggested_fix": "Verify manually.",
                    }
                    for item_id in ids
                ],
                "research_notes": ["fake web provenance path exercised"],
            }
        )


def _init_session(root: Path):
    for name, content in {
        "idea.md": "Demo construction, proof, and benchmark source packet.\n",
        "experimental_log.md": "Cycles: 12.5\n",
        "template.tex": "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\n\\end{document}\n",
        "guidelines.md": "DemoConf\n",
    }.items():
        (root / name).write_text(content, encoding="utf-8")
    (root / "figures").mkdir()
    return create_session(
        root,
        InputBundle(
            idea_path=str(root / "idea.md"),
            experimental_log_path=str(root / "experimental_log.md"),
            template_path=str(root / "template.tex"),
            guidelines_path=str(root / "guidelines.md"),
            figures_dir=str(root / "figures"),
            cutoff_date="2026-01-01",
        ),
    )


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    m0_path = repo / "docs/strict-review-quality-gate-hardening-m0.md"
    _require(m0_path.exists(), "M0 tracked ownership lock missing")
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(m0_path.relative_to(repo))],
        cwd=repo,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    _require(tracked.returncode == 0, "M0 ownership lock is not tracked by git")
    _require(control_prose_markers("No reviewable figure files were available."), "process-residue classifier missed figure logistics")
    _require(not control_prose_markers("Available evidence suggests the theorem bound is conservative."), "process-residue classifier overfired on clean prose")
    _require(check_prompt_meta_leakage("\\section{Discussion} Available source logs were used."), "validator missed shared leakage classifier")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        state = _init_session(root)
        paper = artifact_path(root, "paper.full.tex")
        paper.write_text(
            "\\section{Method}\n"
            "Prior deployment-scope systems motivate the design, and our construction proves invariant-safety security "
            "with a 2.5x benchmark improvement~\\cite{PriorSystem}.\n",
            encoding="utf-8",
        )
        citation_map = artifact_path(root, "citation_map.json")
        citation_map.write_text(
            json.dumps({"PriorSystem": {"title": "A Prior Distributed Scheduling System"}}),
            encoding="utf-8",
        )
        state.artifacts.paper_full_tex = str(paper)
        state.artifacts.citation_map_json = str(citation_map)
        save_session(root, state)

        citation_review = build_citation_support_review(root, evidence_mode="heuristic")
        _require(
            any("mixed_paper_specific_citation_scope" in (item.get("flags") or []) for item in citation_review["items"]),
            "mixed citation-scope guard did not fire",
        )
        paper.write_text(
            "\\section{Background}\nPrevious work provides background for distributed scheduling~\\cite{PriorSystem}.\n",
            encoding="utf-8",
        )
        clean_review = build_citation_support_review(root, evidence_mode="heuristic")
        _require(
            not any("mixed_paper_specific_citation_scope" in (item.get("flags") or []) for item in clean_review["items"]),
            "mixed citation-scope guard overfired on background citation",
        )
        paper.write_text(
            "\\section{Analysis}\nOur construction proves invariant-safety security with the stated theorem~\\cite{PriorSystem}.\n",
            encoding="utf-8",
        )
        paper_specific_review = build_citation_support_review(root, evidence_mode="heuristic")
        _require(
            any("paper_specific_external_citation_scope" in (item.get("flags") or []) for item in paper_specific_review["items"]),
            "paper-specific citation-scope guard did not fire",
        )

        review_path = artifact_path(root, "citation_support_review.json")
        payload = {
            "schema_version": "citation-support-review/2",
            "manuscript_sha256": hashlib.sha256(paper.read_bytes()).hexdigest(),
            "citation_map_sha256": hashlib.sha256(citation_map.read_bytes()).hexdigest(),
            "review_mode": "heuristic",
            "evidence_provenance": {"claim_support_not_metadata_lookup": True},
            "claims_checked": 1,
            "summary": {"unsupported": 1},
            "items": [{"support_status": "unsupported", "citation_keys": ["TLS13"], "citation_entries": []}],
        }
        review_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        check = _citation_support_check(root, load_session(root), quality_mode="claim_safe")
        _require(check.get("citation_review_sha256") == hashlib.sha256(review_path.read_bytes()).hexdigest(), "citation review hash not propagated")
        _require(check.get("canonical_summary") == {"unsupported": 1}, "citation canonical summary not propagated")
        quality_path, quality_eval = write_quality_eval(root, quality_mode="draft")
        payload["summary"] = {"metadata_only": 1}
        review_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        _, stale_plan = write_quality_loop_plan(root, quality_mode="draft", quality_eval_input_path=quality_path)
        _require(
            stale_plan["source_artifacts"].get("citation_review_identity_status") == "stale_or_divergent",
            "tampered citation review did not emit stale/divergent identity status",
        )
        _require(
            stale_plan["reads"]["citation_support"].get("identity_status") == "stale_or_divergent",
            "tampered citation review did not surface stale/divergent read status",
        )
        web_review_path = write_citation_support_review(root, provider=FakeWebProvider(), evidence_mode="web")
        web_review = json.loads(web_review_path.read_text(encoding="utf-8"))
        web_trace = json.loads(web_review_path.with_name(web_review_path.stem + ".trace.json").read_text(encoding="utf-8"))
        _require(web_review["review_mode"] == "web", "web citation review artifact did not preserve review_mode=web")
        _require(web_review["evidence_provenance"].get("mode") == "web", "web citation review artifact did not preserve provenance mode")
        _require(web_review["evidence_provenance"].get("web_search_required") is True, "web citation review did not require web search")
        _require(web_trace.get("web_search_required") is True, "web citation review trace did not preserve web requirement")

        candidate = artifact_path(root, "paper.operator-candidate.tex")
        candidate.write_text("\\section{Method}\nCandidate.\n", encoding="utf-8")
        original_text = paper.read_text(encoding="utf-8")
        _stage_candidate_text_for_verification(root, candidate)
        _require(paper.read_text(encoding="utf-8") == original_text, "candidate staging overwrote canonical manuscript")
        same_blocker_ok, same_blocker_reasons = _candidate_hard_gate(
            validation_payload={"ok": True},
            compile_payload=None,
            quality_eval={"tiers": {"tier_0_preconditions": {"status": "pass"}, "tier_1_structural": {"status": "pass"}}},
            quality_mode="claim_safe",
            incorporation=[{"status": "reflected"}],
            candidate_result={"score_before": 70, "score_after": 70},
            require_issue_progress=True,
            manuscript_changed=True,
            new_tier2_failures=[],
            base_active_failures=["existing_claim_issue"],
            resolved_active_failures=[],
        )
        _require(not same_blocker_ok and "active_blocker_progress_missing" in same_blocker_reasons, "same-blocker candidate passed A3 promotion gate")
        resolved_ok, resolved_reasons = _candidate_hard_gate(
            validation_payload={"ok": True},
            compile_payload=None,
            quality_eval={"tiers": {"tier_0_preconditions": {"status": "pass"}, "tier_1_structural": {"status": "pass"}}},
            quality_mode="claim_safe",
            incorporation=[{"status": "reflected"}],
            candidate_result={"score_before": 70, "score_after": 70},
            require_issue_progress=True,
            manuscript_changed=True,
            new_tier2_failures=[],
            base_active_failures=["existing_claim_issue"],
            resolved_active_failures=["existing_claim_issue"],
        )
        _require(resolved_ok and not resolved_reasons, "resolved-blocker candidate failed A3 promotion gate")

        eval_payload = {"session_id": load_session(root).session_id, "mode": "claim_safe", "tiers": {}}
        append_quality_loop_history(root, eval_payload, event_type="operator_feedback_cycle", consumes_budget=False)
        append_quality_loop_history(root, eval_payload, event_type="qa_loop_step", consumes_budget=True)
        append_quality_loop_history(root, {"session_id": "po-other-session", "mode": "claim_safe", "tiers": {}}, event_type="operator_feedback_cycle", consumes_budget=False)
        append_quality_loop_history(root, eval_payload, event_type="operator_feedback_cycle", consumes_budget=False)
        _require(operator_feedback_cycle_count(root) == 2, "operator-feedback cycle counter is not ledger-derived")
        _require(operator_feedback_cycle_count(root) != 4, "operator-feedback counter includes non-operator or non-session command evidence")
        _require(operator_feedback_cycle_count(root, session_id="po-other-session") == 1, "operator-feedback counter cannot isolate another session")

    with patch("paperorchestra.cli.apply_operator_feedback", return_value=(Path("operator_feedback.execution.json"), {"verdict": "human_needed"})) as apply:
        rc = cli_main(["apply-operator-feedback", "--imported-feedback", "dummy.json", "--provider", "mock"])
        _require(rc == 0, "CLI apply-operator-feedback default smoke failed")
        _require(apply.call_args.kwargs["citation_evidence_mode"] == "web", "claim-safe CLI default is not web")

    print(
        json.dumps(
            {
                "status": "pass",
                "checks": [
                    "M0 ownership",
                    "A1 leakage classifier/validator",
                    "A2 mixed citation scope",
                    "A2 paper-specific citation scope",
                    "A3 candidate staging",
                    "A3 active-blocker promotion gate",
                    "A4 citation identity",
                    "A4 divergent citation identity status",
                    "A4 ledger-derived operator counter",
                    "A5 claim-safe CLI evidence default",
                    "A5 web provenance artifact",
                ],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
