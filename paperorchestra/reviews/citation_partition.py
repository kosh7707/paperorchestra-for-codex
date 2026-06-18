from __future__ import annotations

from typing import Any

from paperorchestra.reviews.eval_text import _title_matches_reference


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
