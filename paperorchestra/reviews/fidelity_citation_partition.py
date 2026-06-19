from __future__ import annotations

from pathlib import Path

from paperorchestra.core.io import read_json
from paperorchestra.core.models import SessionState
from paperorchestra.manuscript.citation_map_model import canonical_citation_map
from paperorchestra.reviews.evaluation import write_citation_partition_request
from paperorchestra.reviews.fidelity_types import FidelityCheck
from paperorchestra.reviews.reproducibility_artifacts import _read_json_if_exists


def ensure_default_citation_partition_request(state: SessionState, session_artifact_dir: Path | None) -> Path | None:
    if session_artifact_dir is None or not state.artifacts.paper_full_tex or not state.artifacts.citation_map_json:
        return None
    output_path = session_artifact_dir / "citation_partition_request.json"
    if output_path.exists():
        return output_path
    citation_map = _read_json_if_exists(state.artifacts.citation_map_json)
    if not isinstance(citation_map, dict) or not citation_map:
        return None
    references = [
        {"title": entry.get("title"), "citation_key": key}
        for key, entry in canonical_citation_map(citation_map).items()
        if isinstance(entry, dict) and isinstance(entry.get("title"), str) and entry.get("title", "").strip()
    ]
    if not references:
        return None
    paper_text = Path(state.artifacts.paper_full_tex).read_text(encoding="utf-8")
    return write_citation_partition_request(paper_text, references, output_path)


def _citation_partition_scaffold_check(state: SessionState, session_artifact_dir: Path | None) -> FidelityCheck:
    partition_scaffold_status = "missing"
    if state.artifacts.paper_full_tex and session_artifact_dir is not None:
        ensure_default_citation_partition_request(state, session_artifact_dir)
        partition_request = session_artifact_dir / "citation_partition_request.json"
        if partition_request.exists():
            partition_request_payload = read_json(partition_request)
            if partition_request_payload.get("reference_count", 0) > 0:
                partition_scaffold_status = "partial"
        partition_artifact = session_artifact_dir / "reference_case_partitioned_citation_coverage.json"
        if partition_artifact.exists():
            partition_payload = read_json(partition_artifact)
            if partition_payload.get("coverage", {}).get("partition_coverage"):
                partition_scaffold_status = "implemented"
            else:
                partition_scaffold_status = "partial"
    return FidelityCheck(
        code="citation_partition_scaffold_surface",
        status=partition_scaffold_status,
        rationale="Benchmark/eval proof should include a partition-based citation coverage scaffold tying generated citations back to a reference-case P0/P1-style split.",
        next_step=(
            "Run `paperorchestra quality-gate --no-fail-on-block` after adding partitioned coverage evidence to the session artifacts."
            if partition_scaffold_status != "implemented"
            else None
        ),
    )
