from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from paperorchestra.domains import detect_domain_for_text
from paperorchestra.manuscript.claim_validation import check_citation_placement, check_claim_map_coverage, check_narrative_section_roles
from paperorchestra.manuscript.validator import extract_decimal_like_tokens


def _read_text_if_exists(path: str | Path | None) -> str:
    if not path:
        return ""
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return ""
    return candidate.read_text(encoding="utf-8", errors="replace")


def _source_material_fidelity_check(state) -> dict[str, Any]:
    paper_text = _read_text_if_exists(state.artifacts.paper_full_tex)
    source_parts = [
        _read_text_if_exists(state.inputs.idea_path),
        _read_text_if_exists(state.inputs.experimental_log_path),
        _read_text_if_exists(state.inputs.template_path),
    ]
    source_text = "\n".join(part for part in source_parts if part)
    domain = detect_domain_for_text(source_text)
    lowered_source = source_text.lower()
    lowered_paper = paper_text.lower()

    proof_required = bool(domain.proof_seed_re.search(lowered_source) or re.search(r"\btheorem\b.*\bproof\b", lowered_source, re.IGNORECASE | re.DOTALL))
    proof_present = bool(
        re.search(
            r"\\begin\{(?:theorem|lemma|proof|proposition)\}|\b(proof|theorem|analysis|bound|guarantee)\b|\\section\*?\{[^}]*(?:security|analysis|proof)[^}]*\}",
            lowered_paper,
            re.IGNORECASE | re.DOTALL,
        )
    )
    benchmark_required = bool(domain.benchmark_seed_re.search(source_text))
    source_numbers = extract_decimal_like_tokens(source_text)
    paper_numbers = extract_decimal_like_tokens(paper_text)
    result_numbers_preserved = sorted(source_numbers & paper_numbers)
    results_present = not (benchmark_required and source_numbers) or bool(result_numbers_preserved)

    failing_codes: list[str] = []
    if proof_required and not proof_present:
        failing_codes.append("source_material_proof_omitted")
    if not results_present:
        failing_codes.append("source_material_results_omitted")
    return {
        "status": "fail" if failing_codes else "pass",
        "failing_codes": failing_codes,
        "proof_required": proof_required,
        "proof_present": proof_present,
        "benchmark_required": benchmark_required,
        "source_numeric_token_count": len(source_numbers),
        "preserved_numeric_tokens": result_numbers_preserved,
        "source_material_paths": {
            "idea": state.inputs.idea_path,
            "experimental_log": state.inputs.experimental_log_path,
            "template": state.inputs.template_path,
        },
    }


def _planning_satisfaction_check(state, planning_status: dict[str, Any]) -> dict[str, Any]:
    if planning_status.get("status") != "pass" or not state.artifacts.paper_full_tex or not Path(state.artifacts.paper_full_tex).exists():
        return {"status": "skipped", "failing_codes": [], "reason": "planning artifacts unavailable or manuscript missing"}
    latex = Path(state.artifacts.paper_full_tex).read_text(encoding="utf-8", errors="replace")
    payloads = planning_status.get("payloads") if isinstance(planning_status.get("payloads"), dict) else {}
    issues = []
    issues.extend(check_claim_map_coverage(latex, payloads.get("claim_map")))
    issues.extend(check_citation_placement(latex, payloads.get("citation_placement_plan")))
    issues.extend(check_narrative_section_roles(latex, payloads.get("narrative_plan")))
    failing_codes = sorted({issue.code for issue in issues if issue.severity == "error"})
    return {
        "status": "fail" if failing_codes else "pass",
        "failing_codes": failing_codes,
        "issue_count": len(issues),
        "issues": [issue.to_dict() for issue in issues],
    }
