from __future__ import annotations

from paperorchestra.engine.citation_coverage import _citation_coverage_target, _ensure_minimum_citation_coverage


def _citation_map(count: int) -> dict[str, dict]:
    return {f"key{i}": {"canonical_bibtex_key": f"key{i}", "title": f"Paper {i}"} for i in range(1, count + 1)}


def test_citation_coverage_target_scales_with_reference_population() -> None:
    assert _citation_coverage_target(_citation_map(0)) == 0
    assert _citation_coverage_target(_citation_map(10)) == 10
    assert _citation_coverage_target(_citation_map(20)) == 17
    assert _citation_coverage_target(_citation_map(40)) == 32
    assert _citation_coverage_target(_citation_map(100)) == 70


def test_minimum_citation_coverage_adds_bounded_related_work_bridge() -> None:
    latex = (
        "\\section{Introduction}\nIntro.\n"
        "\\section{Related Work}\nPrior work~\\cite{key1}.\n"
        "\\section{Method}\nMethod.\n"
    )

    bridged = _ensure_minimum_citation_coverage(latex, _citation_map(3), target=3, max_shortfall=2)

    assert "\\paragraph{Additional related context.}" in bridged
    assert "\\cite{key2,key3}" in bridged
    assert bridged.index("\\paragraph{Additional related context.}") < bridged.index("\\section{Method}")


def test_minimum_citation_coverage_refuses_large_shortfall() -> None:
    latex = "\\section{Related Work}\nPrior work~\\cite{key1}.\n\\section{Method}\nMethod.\n"

    assert _ensure_minimum_citation_coverage(latex, _citation_map(5), target=5, max_shortfall=2) == latex
