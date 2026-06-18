from __future__ import annotations

from paperorchestra.manuscript.validator_content import check_comparative_claims, check_numeric_grounding


def test_numeric_grounding_ignores_layout_decimal_values() -> None:
    latex = r"\includegraphics[width=0.5\textwidth]{plot} Result is 12.3%."
    log = "Result is 12.3%."

    assert check_numeric_grounding(latex, log) == []


def test_comparative_claim_gate_reports_unbacked_claim_terms() -> None:
    issues = check_comparative_claims("Our method outperforms baselines.", "The experiment measured runtime.")

    assert [issue.code for issue in issues] == ["unsupported_comparative_claim"]
