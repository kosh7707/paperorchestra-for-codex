from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json
from paperorchestra.reviews.citation_partition import (
    build_citation_partition_request,
    compute_partitioned_citation_coverage,
)
from paperorchestra.reviews.evaluation_constants import (
    EXPECTED_LITERATURE_REVIEW_AXES,
    EXPECTED_SEARCH_GROUNDED_SOURCES,
)
from paperorchestra.reviews.evaluation_io import _write_json_artifact
from paperorchestra.reviews.evaluation_session_summary import build_session_eval_summary
from paperorchestra.reviews.generated_citations import build_generated_citation_titles
from paperorchestra.reviews.review_gate_comparison import build_review_gate_comparison


def build_reference_comparison(reference_case_path: str | Path, cwd: str | Path | None) -> dict[str, Any]:
    reference_case = read_json(reference_case_path)
    session_summary = build_session_eval_summary(cwd)
    generated_citations = build_generated_citation_titles(cwd)
    review_gate_comparison = build_review_gate_comparison(cwd)
    partitioned_citation_coverage = build_reference_case_partitioned_citation_coverage(reference_case_path, cwd)
    review_axes = session_summary.get("review_axis_scores") or {}
    available_axes = set(review_axes) if isinstance(review_axes, dict) else set()
    return {
        "reference_case_id": reference_case.get("case_id"),
        "session_id": session_summary["session_id"],
        "comparability": {
            "paper_derived_inputs": reference_case.get("source_type") == "paper-derived",
            "baseline_names_available": bool(reference_case.get("baselines")),
            "reported_margin_ranges_available": bool(reference_case.get("reported_margin_ranges")),
            "session_review_available": session_summary.get("review_overall_score") is not None,
            "session_runtime_parity_available": session_summary.get("runtime_parity_overall_status") is not None,
            "search_grounded_sources_present": session_summary.get("search_grounded_required_sources_present", False),
            "search_grounded_attempted_sources_present": session_summary.get("search_grounded_attempted_required_sources_present", False),
            "agentreview_axis_overlap_count": len(available_axes & set(EXPECTED_LITERATURE_REVIEW_AXES)),
            "agentreview_axis_missing": [axis for axis in EXPECTED_LITERATURE_REVIEW_AXES if axis not in available_axes],
        },
        "expected_review_axes": EXPECTED_LITERATURE_REVIEW_AXES,
        "reference_reported_margin_ranges": reference_case.get("reported_margin_ranges", {}),
        "session_summary": session_summary,
        "expected_search_grounded_sources": EXPECTED_SEARCH_GROUNDED_SOURCES,
        "review_gate_comparison": review_gate_comparison,
        "generated_citation_titles": generated_citations,
        "reference_case_partitioned_citation_coverage": partitioned_citation_coverage,
        "comparison_gaps": [
            "This artifact compares a single reconstructed session against a paper-derived benchmark case; it is not yet the full PaperWritingBench evaluation.",
            "Judge/model alignment and PaperBanana/AgentReview equivalence remain open until later benchmark phases.",
        ],
    }


def write_reference_comparison(reference_case_path: str | Path, cwd: str | Path | None, output_path: str | Path) -> Path:
    payload = build_reference_comparison(reference_case_path, cwd)
    return _write_json_artifact(payload, output_path)


def build_reference_case_partition_scaffold(reference_case_path: str | Path) -> dict[str, Any]:
    reference_case = read_json(reference_case_path)
    reference_entries: list[dict[str, Any]] = []
    partition_map: dict[str, str] = {}
    index = 1
    for title in reference_case.get("baselines", []):
        if not isinstance(title, str) or not title.strip():
            continue
        reference_entries.append({"title": title.strip(), "source": "baseline"})
        partition_map[str(index)] = "P0"
        index += 1
    for title in reference_case.get("datasets_or_benchmarks", []):
        if not isinstance(title, str) or not title.strip():
            continue
        reference_entries.append({"title": title.strip(), "source": "dataset_or_benchmark"})
        partition_map[str(index)] = "P0"
        index += 1
    return {
        "reference_entries": reference_entries,
        "partition_map": partition_map,
        "notes": [
            "This scaffold treats baselines and datasets/benchmarks from the reference case as P0 items.",
            "It is a bounded approximation of the paper's P0/P1 partition setup, not a full citation-annotated ground truth.",
        ],
    }


def write_reference_case_partition_scaffold(reference_case_path: str | Path, output_path: str | Path) -> Path:
    payload = build_reference_case_partition_scaffold(reference_case_path)
    return _write_json_artifact(payload, output_path)


def build_reference_case_partitioned_citation_coverage(reference_case_path: str | Path, cwd: str | Path | None) -> dict[str, Any]:
    scaffold = build_reference_case_partition_scaffold(reference_case_path)
    generated = build_generated_citation_titles(cwd)
    coverage = compute_partitioned_citation_coverage(
        scaffold["reference_entries"],
        scaffold["partition_map"],
        generated.get("generated_titles", []),
    )
    return {
        "reference_case_id": read_json(reference_case_path).get("case_id"),
        "scaffold": scaffold,
        "generated_citation_titles": generated,
        "coverage": coverage,
    }


def write_reference_case_partitioned_citation_coverage(reference_case_path: str | Path, cwd: str | Path | None, output_path: str | Path) -> Path:
    payload = build_reference_case_partitioned_citation_coverage(reference_case_path, cwd)
    return _write_json_artifact(payload, output_path)


def write_citation_partition_request(paper_text: str, references: list[dict[str, Any]], output_path: str | Path) -> Path:
    payload = build_citation_partition_request(paper_text, references)
    return _write_json_artifact(payload, output_path)


def write_partitioned_citation_coverage(
    reference_entries: list[dict[str, Any]],
    partition_map: dict[str, str],
    generated_titles: list[str],
    output_path: str | Path,
) -> Path:
    payload = compute_partitioned_citation_coverage(reference_entries, partition_map, generated_titles)
    return _write_json_artifact(payload, output_path)
