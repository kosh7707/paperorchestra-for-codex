from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json
from paperorchestra.core.session import load_session
from paperorchestra.manuscript.citations import canonical_citation_keys
from paperorchestra.reviews.citation_partition import (
    build_citation_partition_request,
    compute_partitioned_citation_coverage,
)
from paperorchestra.reviews.evaluation_constants import (
    EXPECTED_LITERATURE_REVIEW_AXES,
    EXPECTED_SEARCH_GROUNDED_SOURCES,
    IGNORED_DISCOVERY_SOURCES,
)
from paperorchestra.reviews.evaluation_io import _write_json_artifact
from paperorchestra.reviews.generated_citations import build_generated_citation_titles
from paperorchestra.reviews.review_gate_comparison import build_review_gate_comparison
from paperorchestra.reviews.eval_text import parse_reported_margin_ranges


def _session_artifact_dir(state) -> Path | None:
    for candidate in [state.artifacts.paper_full_tex, state.artifacts.candidate_papers_json]:
        if candidate and Path(candidate).exists():
            return Path(candidate).resolve().parent
    return None


def _attempted_grounded_sources(session_artifact_dir: Path | None) -> list[str]:
    if session_artifact_dir is None:
        return []
    lane_manifest_path = session_artifact_dir / "lane-manifest.literature.json"
    if not lane_manifest_path.exists():
        return []
    try:
        payload = read_json(lane_manifest_path)
    except Exception:
        return []
    notes = payload.get("notes", []) if isinstance(payload, dict) else []
    attempted: list[str] = []
    joined = "\n".join(note for note in notes if isinstance(note, str)).lower()
    if "semantic scholar grounded query" in joined and "semantic_scholar" not in attempted:
        attempted.append("semantic_scholar")
    if "openalex grounded query" in joined and "openalex" not in attempted:
        attempted.append("openalex")
    return attempted


def build_reference_benchmark_case(reference_dir: str | Path, *, source_pdf: str | Path | None = None) -> dict[str, Any]:
    root = Path(reference_dir).resolve()
    seed_answers = json.loads((root / "seed_answers.json").read_text(encoding="utf-8"))
    results_text = (root / "results.md").read_text(encoding="utf-8")
    methodology_text = (root / "methodology.md").read_text(encoding="utf-8")
    task_text = (root / "task_and_dataset.md").read_text(encoding="utf-8")
    margins = parse_reported_margin_ranges(results_text)
    return {
        "case_id": "paperorchestra-reference",
        "source_type": "paper-derived",
        "source_pdf": str(Path(source_pdf).resolve()) if source_pdf else None,
        "reference_dir": str(root),
        "inputs": {
            "seed_answers_path": str(root / "seed_answers.json"),
            "results_path": str(root / "results.md"),
            "methodology_path": str(root / "methodology.md"),
            "task_and_dataset_path": str(root / "task_and_dataset.md"),
            "template_path": str(root / "template.tex"),
        },
        "baselines": seed_answers.get("baselines", []),
        "datasets_or_benchmarks": seed_answers.get("datasets_or_benchmarks", []),
        "reported_margin_ranges": margins,
        "comparability": {
            "baseline_names_present": bool(seed_answers.get("baselines")),
            "paper_derived_materials_present": True,
            "reported_margins_present": bool(margins),
            "appendix_f_prompt_target_required": True,
            "review_gate_comparability_required": True,
        },
        "evaluation_gaps": [
            "Citation F1 / ScholarPeer / full PaperWritingBench autorater pipeline not yet reconstructed in codebase.",
            "Paper-derived benchmark case is a directional proxy, not a substitute for the full benchmark corpus.",
        ],
        "notes": [
            "This case packages reverse-engineered materials from a PaperOrchestra reference paper PDF for benchmark/eval scaffold work.",
            "Use this artifact as a reproducible reference fixture while the broader benchmark/eval harness is being reconstructed.",
        ],
        "source_previews": {
            "methodology_excerpt": methodology_text[:600],
            "task_excerpt": task_text[:600],
        },
    }


def write_reference_benchmark_case(reference_dir: str | Path, output_path: str | Path, *, source_pdf: str | Path | None = None) -> Path:
    payload = build_reference_benchmark_case(reference_dir, source_pdf=source_pdf)
    return _write_json_artifact(payload, output_path)


def build_session_eval_summary(cwd: str | Path | None) -> dict[str, Any]:
    state = load_session(cwd)
    latest_review = read_json(state.artifacts.latest_review_json) if state.artifacts.latest_review_json and Path(state.artifacts.latest_review_json).exists() else None
    latest_fidelity = read_json(state.artifacts.latest_fidelity_json) if state.artifacts.latest_fidelity_json and Path(state.artifacts.latest_fidelity_json).exists() else None
    latest_runtime_parity = read_json(state.artifacts.latest_runtime_parity_json) if state.artifacts.latest_runtime_parity_json and Path(state.artifacts.latest_runtime_parity_json).exists() else None
    citation_map = read_json(state.artifacts.citation_map_json) if state.artifacts.citation_map_json and Path(state.artifacts.citation_map_json).exists() else {}
    candidate_papers = read_json(state.artifacts.candidate_papers_json) if state.artifacts.candidate_papers_json and Path(state.artifacts.candidate_papers_json).exists() else None
    validation_payload = read_json(state.artifacts.latest_validation_json) if state.artifacts.latest_validation_json and Path(state.artifacts.latest_validation_json).exists() else None
    session_artifact_dir = _session_artifact_dir(state)
    discovery_sources: list[str] = []
    candidate_count = 0
    if isinstance(candidate_papers, dict):
        for bucket in ("macro_candidates", "micro_candidates"):
            for candidate in candidate_papers.get(bucket, []):
                if not isinstance(candidate, dict):
                    continue
                candidate_count += 1
                sources = candidate.get("discovery_sources")
                if isinstance(sources, list) and sources:
                    for source in sources:
                        if isinstance(source, str) and source not in IGNORED_DISCOVERY_SOURCES and source not in discovery_sources:
                            discovery_sources.append(source)
                else:
                    source = candidate.get("discovery_source")
                    if isinstance(source, str) and source not in IGNORED_DISCOVERY_SOURCES and source not in discovery_sources:
                        discovery_sources.append(source)
    attempted_sources = _attempted_grounded_sources(session_artifact_dir)

    source_counts = {source: 0 for source in discovery_sources}
    if isinstance(candidate_papers, dict):
        for bucket in ("macro_candidates", "micro_candidates"):
            for candidate in candidate_papers.get(bucket, []):
                if not isinstance(candidate, dict):
                    continue
                sources = candidate.get("discovery_sources")
                if isinstance(sources, list) and sources:
                    for source in sources:
                        if isinstance(source, str) and source not in IGNORED_DISCOVERY_SOURCES:
                            source_counts[source] = source_counts.get(source, 0) + 1
                else:
                    source = candidate.get("discovery_source")
                    if isinstance(source, str) and source not in IGNORED_DISCOVERY_SOURCES:
                        source_counts[source] = source_counts.get(source, 0) + 1
    search_grounded_sources_present = state.latest_discovery_mode == "search-grounded" and set(EXPECTED_SEARCH_GROUNDED_SOURCES) <= set(discovery_sources)
    search_grounded_attempted_sources_present = state.latest_discovery_mode == "search-grounded" and set(EXPECTED_SEARCH_GROUNDED_SOURCES) <= set(attempted_sources)

    return {
        "session_id": state.session_id,
        "current_phase": state.current_phase,
        "refinement_iteration": state.refinement_iteration,
        "review_overall_score": latest_review.get("overall_score") if isinstance(latest_review, dict) else None,
        "review_axis_scores": latest_review.get("axis_scores") if isinstance(latest_review, dict) else None,
        "verified_citation_count": len(canonical_citation_keys(citation_map)) if isinstance(citation_map, dict) else 0,
        "candidate_discovery_sources": discovery_sources,
        "candidate_discovery_source_counts": source_counts,
        "candidate_discovery_attempted_sources": attempted_sources,
        "candidate_discovery_mode": state.latest_discovery_mode,
        "search_grounded_required_sources_present": search_grounded_sources_present,
        "search_grounded_attempted_required_sources_present": search_grounded_attempted_sources_present,
        "candidate_count": candidate_count,
        "latest_validation": validation_payload,
        "fidelity_overall_status": latest_fidelity.get("overall_status") if isinstance(latest_fidelity, dict) else None,
        "runtime_parity_overall_status": latest_runtime_parity.get("overall_status") if isinstance(latest_runtime_parity, dict) else None,
        "artifacts": {
            "paper_full_tex": state.artifacts.paper_full_tex,
            "latest_review_json": state.artifacts.latest_review_json,
            "latest_fidelity_json": state.artifacts.latest_fidelity_json,
            "latest_runtime_parity_json": state.artifacts.latest_runtime_parity_json,
        },
        "notes_tail": state.notes[-6:],
    }


def write_session_eval_summary(cwd: str | Path | None, output_path: str | Path) -> Path:
    payload = build_session_eval_summary(cwd)
    return _write_json_artifact(payload, output_path)


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
