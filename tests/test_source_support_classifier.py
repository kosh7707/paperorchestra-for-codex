from __future__ import annotations

from paperorchestra.reviews.source_support_classifier import _classify_source_support


def test_source_support_classifier_passes_local_claim_support() -> None:
    case = {
        "key": "smith2024",
        "target": "Smith 2024 reports a recall-preserving SAST alert triage pipeline.",
    }
    text = "Smith 2024 reports a recall-preserving SAST alert triage pipeline for Java alerts."

    verdict, note = _classify_source_support(case, text)

    assert verdict == "pass"
    assert "locally supports" in note


def test_source_support_classifier_detects_in_scope_contradiction() -> None:
    case = {
        "key": "smith2024",
        "target": "Smith 2024 uses static analysis alerts for triage.",
    }
    text = "Smith 2024 does not use static analysis alerts for triage."

    verdict, note = _classify_source_support(case, text)

    assert verdict == "fail"
    assert "contradict" in note


def test_source_support_classifier_returns_weak_for_related_partial_source() -> None:
    case = {
        "key": "smith2024",
        "target": "Smith 2024 evaluates recall-preserving Java SAST alert triage.",
    }
    text = "Smith 2024 is a paper about Java programs and static analysis."

    verdict, note = _classify_source_support(case, text)

    assert verdict == "weak"
    assert "partial" in note
