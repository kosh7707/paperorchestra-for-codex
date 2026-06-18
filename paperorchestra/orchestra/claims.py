from __future__ import annotations

from pathlib import Path

from paperorchestra.orchestra.claim_extraction import (
    TEXT_SOURCE_EXTENSIONS,
    candidate_sentences as _candidate_sentences,
    claim_type as _claim_type,
    criticality as _criticality,
    graph_role as _graph_role,
    normalize_space as _normalize_space,
    read_source_texts as _read_source_texts,
    sha256_text as _sha256_text,
    strip_markup as _strip_markup,
)
from paperorchestra.orchestra.claim_records import (
    CitationObligation,
    ClaimCandidate,
    ClaimGraphReport,
    EvidenceObligation,
    SourceText as _SourceText,
)
from paperorchestra.orchestra.materials import MaterialInventory, SourceDigest

CLAIM_SENTENCE_LIMIT = 12


def build_claim_graph_from_materials(
    material_path: str | Path,
    inventory: MaterialInventory,
    digest: SourceDigest,
    *,
    max_claims: int = CLAIM_SENTENCE_LIMIT,
) -> ClaimGraphReport:
    if not digest.sufficient:
        return ClaimGraphReport(
            schema_version="claim-graph/1",
            status="blocked",
            ready=False,
            claim_count=0,
            blocking_reasons=["source_digest_not_ready", *digest.blocking_reasons],
        )

    sources = _read_source_texts(Path(material_path), inventory)
    candidates: list[ClaimCandidate] = []
    seen_text_hashes: set[str] = set()
    for source in sources:
        for sentence in _candidate_sentences(source.text):
            text_hash = _sha256_text(_normalize_space(sentence))
            if text_hash in seen_text_hashes:
                continue
            seen_text_hashes.add(text_hash)
            claim_type = _claim_type(sentence)
            graph_role = _graph_role(claim_type, len(candidates))
            criticality = _criticality(claim_type, graph_role)
            candidates.append(
                ClaimCandidate(
                    claim_id=f"C{len(candidates) + 1}",
                    claim_type=claim_type,
                    graph_role=graph_role,
                    criticality=criticality,
                    text_sha256=text_hash,
                    text_label=f"redacted-claim:{text_hash[:12]}",
                    source_label=source.source_label,
                    source_sha256=source.path_sha256,
                    raw_text=_normalize_space(sentence),
                )
            )
            if len(candidates) >= max_claims:
                break
        if len(candidates) >= max_claims:
            break

    if not candidates:
        return ClaimGraphReport(
            schema_version="claim-graph/1",
            status="blocked",
            ready=False,
            claim_count=0,
            blocking_reasons=["no_candidate_claims_found"],
        )

    evidence_obligations = [
        EvidenceObligation(
            obligation_id=f"E{idx}",
            claim_id=claim.claim_id,
            status="research_needed" if claim.criticality == "high" else "missing",
            criticality=claim.criticality,
            machine_solvable=True,
        )
        for idx, claim in enumerate(candidates, start=1)
    ]
    citation_obligations = [
        CitationObligation(
            obligation_id=f"R{idx}",
            claim_id=claim.claim_id,
            status="unknown_reference" if claim.criticality == "high" else "not_checked",
            critical=claim.criticality == "high",
            machine_solvable=True,
        )
        for idx, claim in enumerate(candidates, start=1)
    ]
    return ClaimGraphReport(
        schema_version="claim-graph/1",
        status="candidate",
        ready=True,
        claim_count=len(candidates),
        claims=candidates,
        evidence_obligations=evidence_obligations,
        citation_obligations=citation_obligations,
    )


__all__ = [
    "CLAIM_SENTENCE_LIMIT",
    "TEXT_SOURCE_EXTENSIONS",
    "CitationObligation",
    "ClaimCandidate",
    "ClaimGraphReport",
    "EvidenceObligation",
    "_SourceText",
    "_candidate_sentences",
    "_claim_type",
    "_criticality",
    "_graph_role",
    "_normalize_space",
    "_read_source_texts",
    "_sha256_text",
    "_strip_markup",
    "build_claim_graph_from_materials",
]
