from __future__ import annotations

from paperorchestra.feedback import operator_feedback
from paperorchestra.feedback.operator_contexts import citations


def test_operator_feedback_binds_protected_citation_regression_helper() -> None:
    assert operator_feedback._protected_supported_citation_regressions is citations._protected_supported_citation_regressions
