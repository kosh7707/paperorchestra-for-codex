from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .io_utils import read_json
from .literature import title_match_ratio
from .session import load_session

EXPECTED_LITERATURE_REVIEW_AXES = [
    "coverage_and_completeness",
    "relevance_and_focus",
    "critical_analysis_and_synthesis",
    "positioning_and_novelty",
    "organization_and_writing",
    "citation_practices_and_rigor",
]
EXPECTED_CITATION_STATISTICS_KEYS = [
    "estimated_unique_citations",
    "citation_density_assessment",
    "breadth_across_subareas",
    "comparison_to_baseline",
    "notes",
]
EXPECTED_REVIEW_SUMMARY_KEYS = ["strengths", "weaknesses", "top_improvements"]
EXPECTED_SEARCH_GROUNDED_SOURCES = ["semantic_scholar", "openalex"]
IGNORED_DISCOVERY_SOURCES = {"model"}


def _write_json_artifact(payload: dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


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


def normalize_eval_title(text: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in text).split())


def _compact_eval_title(text: str) -> str:
    return "".join(ch.lower() for ch in text if ch.isalnum())


def _title_matches_reference(reference_title: str, generated_title: str) -> tuple[bool, float, str]:
    reference_normalized = normalize_eval_title(reference_title)
    generated_normalized = normalize_eval_title(generated_title)
    if reference_normalized == generated_normalized:
        return True, 100.0, "exact"
    reference_compact = _compact_eval_title(reference_title)
    generated_compact = _compact_eval_title(generated_title)
    compact_safe = (
        min(len(reference_normalized.split()), len(generated_normalized.split())) == 1
        or
        min(len(reference_normalized.split()), len(generated_normalized.split())) >= 3
        or min(len(reference_compact), len(generated_compact)) >= 18
    )
    if compact_safe and generated_compact and reference_compact and (
        generated_compact in reference_compact or reference_compact in generated_compact
    ):
        return True, 95.0, "compact"
    score = title_match_ratio(reference_title, generated_title)
    if score >= 70.0:
        return True, score, "fuzzy"
    return False, score, ""


_PERCENT_RANGE_RE = re.compile(r"(\d+(?:\.\d+)?)%\s*(?:–|-|to)\s*(\d+(?:\.\d+)?)%")
_CITE_RE = re.compile(r"\\cite[a-zA-Z*]*\s*(?:\[[^\]]*\]){0,2}\{([^}]+)\}")


def _extract_metric_range(text: str, metric_label: str) -> tuple[float, float] | None:
    patterns = [
        re.compile(
            rf"(\d+(?:\.\d+)?)%\s*(?:–|-|to)\s*(\d+(?:\.\d+)?)%\s+in\s+{re.escape(metric_label)}",
            re.IGNORECASE,
        ),
        re.compile(
            rf"{re.escape(metric_label)}.{0,80}?(\d+(?:\.\d+)?)%\s*(?:–|-|to)\s*(\d+(?:\.\d+)?)%",
            re.IGNORECASE | re.DOTALL,
        ),
    ]
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return float(match.group(1)), float(match.group(2))
    return None


def _extract_first_percent_range(text: str) -> tuple[float, float] | None:
    match = _PERCENT_RANGE_RE.search(text)
    if not match:
        return None
    return float(match.group(1)), float(match.group(2))


def parse_reported_margin_ranges(text: str) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for key, label in [
        ("literature_review_quality", "literature review quality"),
        ("overall_manuscript_quality", "overall manuscript quality"),
    ]:
        margin = _extract_metric_range(text, label)
        if margin is not None:
            results[key] = {
                "min": margin[0],
                "max": margin[1],
                "unit": "absolute_win_rate_margin_percent",
                "source_excerpt": label,
            }
    return results


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
        "verified_citation_count": len(citation_map) if isinstance(citation_map, dict) else 0,
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


def build_review_gate_comparison(cwd: str | Path | None) -> dict[str, Any]:
    state = load_session(cwd)
    latest_review = read_json(state.artifacts.latest_review_json) if state.artifacts.latest_review_json and Path(state.artifacts.latest_review_json).exists() else {}
    axis_scores = latest_review.get("axis_scores") if isinstance(latest_review, dict) else {}
    present_axes = list(axis_scores.keys()) if isinstance(axis_scores, dict) else []
    missing_axes = [axis for axis in EXPECTED_LITERATURE_REVIEW_AXES if axis not in present_axes]
    extra_axes = [axis for axis in present_axes if axis not in EXPECTED_LITERATURE_REVIEW_AXES]
    citation_statistics = latest_review.get("citation_statistics") if isinstance(latest_review, dict) else {}
    summary = latest_review.get("summary") if isinstance(latest_review, dict) else {}
    questions = latest_review.get("questions") if isinstance(latest_review, dict) else []
    missing_citation_statistics_keys = [key for key in EXPECTED_CITATION_STATISTICS_KEYS if key not in citation_statistics] if isinstance(citation_statistics, dict) else EXPECTED_CITATION_STATISTICS_KEYS[:]
    missing_summary_keys = [key for key in EXPECTED_REVIEW_SUMMARY_KEYS if key not in summary] if isinstance(summary, dict) else EXPECTED_REVIEW_SUMMARY_KEYS[:]
    questions_count = len(questions) if isinstance(questions, list) else 0
    overall_score = latest_review.get("overall_score") if isinstance(latest_review, dict) else None
    axis_scores_for_numeric = axis_scores if isinstance(axis_scores, dict) else {}
    numeric_axis_scores = {
        key: value.get("score")
        for key, value in axis_scores_for_numeric.items()
        if isinstance(value, dict) and isinstance(value.get("score"), (int, float))
    }
    anti_inflation_violations: list[str] = []
    if isinstance(overall_score, (int, float)):
        if any(isinstance(score, (int, float)) and score < 50 for score in numeric_axis_scores.values()) and overall_score > 75:
            anti_inflation_violations.append("overall_score_above_75_with_sub50_axis")
        if overall_score > 90:
            anti_inflation_violations.append("overall_score_above_90_requires_exceptional_evidence")
    critical_score = numeric_axis_scores.get("critical_analysis_and_synthesis")
    if isinstance(critical_score, (int, float)) and critical_score > 60 and isinstance(overall_score, (int, float)) and overall_score <= 55:
        anti_inflation_violations.append("critical_analysis_above_60_with_low_overall_score")
    return {
        "session_id": state.session_id,
        "review_path": state.artifacts.latest_review_json,
        "overall_score": overall_score,
        "expected_axes": EXPECTED_LITERATURE_REVIEW_AXES,
        "present_axes": present_axes,
        "missing_axes": missing_axes,
        "extra_axes": extra_axes,
        "overlap_count": len(present_axes) - len(extra_axes),
        "has_citation_statistics": isinstance(latest_review, dict) and isinstance(citation_statistics, dict),
        "has_penalties": isinstance(latest_review, dict) and isinstance(latest_review.get("penalties"), list),
        "has_summary": isinstance(latest_review, dict) and isinstance(summary, dict),
        "has_questions": isinstance(latest_review, dict) and isinstance(questions, list),
        "missing_citation_statistics_keys": missing_citation_statistics_keys,
        "missing_summary_keys": missing_summary_keys,
        "questions_count": questions_count,
        "anti_inflation_violations": anti_inflation_violations,
        "comparability_status": (
            "implemented"
            if not missing_axes
            and not missing_citation_statistics_keys
            and not missing_summary_keys
            and isinstance(latest_review, dict)
            and isinstance(latest_review.get("penalties"), list)
            and questions_count > 0
            and not anti_inflation_violations
            else "partial"
            if latest_review
            else "missing"
        ),
        "notes": [
            "This artifact checks whether the current review surface matches the expected AgentReview-style literature-review autorater structure.",
        ],
    }


def write_review_gate_comparison(cwd: str | Path | None, output_path: str | Path) -> Path:
    payload = build_review_gate_comparison(cwd)
    return _write_json_artifact(payload, output_path)


def build_generated_citation_titles(cwd: str | Path | None) -> dict[str, Any]:
    state = load_session(cwd)
    if not state.artifacts.paper_full_tex or not Path(state.artifacts.paper_full_tex).exists():
        return {"cited_keys": [], "generated_titles": [], "notes": ["No paper_full_tex artifact available."]}
    if not state.artifacts.citation_map_json or not Path(state.artifacts.citation_map_json).exists():
        return {"cited_keys": [], "generated_titles": [], "notes": ["No citation_map_json artifact available."]}

    latex_text = Path(state.artifacts.paper_full_tex).read_text(encoding="utf-8")
    citation_map = read_json(state.artifacts.citation_map_json)
    cited_keys: list[str] = []
    for match in _CITE_RE.findall(latex_text):
        for key in [part.strip() for part in match.split(",") if part.strip()]:
            if key not in cited_keys:
                cited_keys.append(key)

    generated_titles: list[str] = []
    resolved_entries: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for key in cited_keys:
        entry = citation_map.get(key, {}) if isinstance(citation_map, dict) else {}
        title = entry.get("title") if isinstance(entry, dict) else None
        if not isinstance(title, str) or not title.strip():
            continue
        clean_title = title.strip()
        normalized = normalize_eval_title(clean_title)
        if normalized in seen_titles:
            continue
        seen_titles.add(normalized)
        generated_titles.append(clean_title)
        resolved_entries.append(
            {
                "citation_key": key,
                "title": clean_title,
                "normalized_title": normalized,
                "paper_id": entry.get("paper_id") if isinstance(entry, dict) else None,
            }
        )

    return {
        "session_id": state.session_id,
        "cited_keys": cited_keys,
        "generated_titles": generated_titles,
        "resolved_entries": resolved_entries,
        "count": len(generated_titles),
        "notes": [
            "Titles are resolved from the current paper's cite-style commands against citation_map.json.",
            "Duplicate citation titles are collapsed by normalized title for scaffold comparisons.",
        ],
    }


def write_generated_citation_titles(cwd: str | Path | None, output_path: str | Path) -> Path:
    payload = build_generated_citation_titles(cwd)
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


def build_citation_partition_request(paper_text: str, references: list[dict[str, Any]]) -> dict[str, Any]:
    reference_lines = []
    for index, item in enumerate(references, start=1):
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        reference_lines.append(f"[{index}] {title}")
    return {
        "paper_text": paper_text,
        "references_str": "\n".join(reference_lines),
        "reference_count": len(reference_lines),
        "notes": [
            "Use this artifact with the Citation F1 P0/P1 partition autorater prompt.",
            "Reference numbering is synthetic and scoped only to this evaluation request.",
        ],
    }


def write_citation_partition_request(paper_text: str, references: list[dict[str, Any]], output_path: str | Path) -> Path:
    payload = build_citation_partition_request(paper_text, references)
    return _write_json_artifact(payload, output_path)


def compute_partitioned_citation_coverage(
    reference_entries: list[dict[str, Any]],
    partition_map: dict[str, str],
    generated_titles: list[str],
) -> dict[str, Any]:
    generated_pool = [title.strip() for title in generated_titles if isinstance(title, str) and title.strip()]
    generated_total = len(generated_pool)
    partitions: dict[str, list[str]] = {"P0": [], "P1": []}
    for idx, item in enumerate(reference_entries, start=1):
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        label = partition_map.get(str(idx), "P1")
        if label not in partitions:
            continue
        partitions[label].append(title)

    unmatched_generated = list(generated_pool)
    coverage: dict[str, Any] = {}
    matched_pairs: list[dict[str, Any]] = []
    for label, titles in partitions.items():
        matched_titles: list[str] = []
        missing_titles: list[str] = []
        partition_pairs: list[dict[str, Any]] = []
        for title in titles:
            normalized = normalize_eval_title(title)
            best_index = -1
            best_score = -1.0
            best_match_type = ""
            for idx, candidate in enumerate(unmatched_generated):
                matched, score, match_type = _title_matches_reference(title, candidate)
                if matched and match_type == "exact":
                    best_index = idx
                    best_score = score
                    best_match_type = match_type
                    break
                if matched and score > best_score:
                    best_index = idx
                    best_score = score
                    best_match_type = match_type
            if best_index >= 0:
                candidate = unmatched_generated.pop(best_index)
                matched_titles.append(title)
                pair = {
                    "reference_title": title,
                    "generated_title": candidate,
                    "match_type": best_match_type,
                    "match_score": round(best_score, 2),
                    "partition": label,
                }
                partition_pairs.append(pair)
                matched_pairs.append(pair)
            else:
                missing_titles.append(title)
        total = len(titles)
        coverage[label] = {
            "total": total,
            "matched": len(matched_titles),
            "recall": round(len(matched_titles) / total, 4) if total else None,
            "matched_titles": matched_titles,
            "missing_titles": missing_titles,
            "matched_pairs": partition_pairs,
        }
    p0_recall = coverage["P0"]["recall"] or 0.0
    p1_recall = coverage["P1"]["recall"] or 0.0
    weighted = round((0.75 * p0_recall) + (0.25 * p1_recall), 4)
    precision = round(len(matched_pairs) / generated_total, 4) if generated_total else None
    return {
        "partition_coverage": coverage,
        "weighted_priority_recall": weighted,
        "generated_title_count": generated_total,
        "matched_generated_title_count": len(matched_pairs),
        "generated_precision": precision,
        "matched_pairs": matched_pairs,
        "unmatched_generated_titles": unmatched_generated,
        "notes": [
            "This is a scaffold metric over normalized-title matching with bounded fuzzy fallback; it is not yet a full Semantic Scholar-ID-grounded Citation F1 implementation.",
        ],
    }


def write_partitioned_citation_coverage(
    reference_entries: list[dict[str, Any]],
    partition_map: dict[str, str],
    generated_titles: list[str],
    output_path: str | Path,
) -> Path:
    payload = compute_partitioned_citation_coverage(reference_entries, partition_map, generated_titles)
    return _write_json_artifact(payload, output_path)
