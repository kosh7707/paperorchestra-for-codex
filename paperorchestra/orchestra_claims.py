from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .orchestra_draft_control import HIGH_CRITICAL_CLAIM_TYPES, HIGH_CRITICAL_GRAPH_ROLES, MEDIUM_CRITICAL_CLAIM_TYPES
from .orchestra_materials import MaterialInventory, SourceDigest

CLAIM_SENTENCE_LIMIT = 12
TEXT_SOURCE_EXTENSIONS = {".tex", ".md", ".txt", ".rst", ".csv"}


@dataclass(frozen=True)
class ClaimCandidate:
    claim_id: str
    claim_type: str
    graph_role: str
    criticality: str
    text_sha256: str
    text_label: str
    source_label: str
    source_sha256: str
    raw_text: str | None = field(default=None, repr=False)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "claim_type": self.claim_type,
            "graph_role": self.graph_role,
            "criticality": self.criticality,
            "text_sha256": self.text_sha256,
            "text_label": self.text_label,
            "source_label": self.source_label,
            "source_sha256": self.source_sha256,
        }


@dataclass(frozen=True)
class EvidenceObligation:
    obligation_id: str
    claim_id: str
    status: str
    criticality: str
    machine_solvable: bool = True
    reason: str = "claim_requires_source_support"

    def to_public_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class CitationObligation:
    obligation_id: str
    claim_id: str
    status: str
    critical: bool
    machine_solvable: bool = True
    reason: str = "claim_requires_citation_support"

    def to_public_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class ClaimGraphReport:
    schema_version: str
    status: str
    ready: bool
    claim_count: int
    claims: list[ClaimCandidate] = field(default_factory=list)
    evidence_obligations: list[EvidenceObligation] = field(default_factory=list)
    citation_obligations: list[CitationObligation] = field(default_factory=list)
    blocking_reasons: list[str] = field(default_factory=list)
    private_safe_summary: bool = True

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "ready": self.ready,
            "claim_count": self.claim_count,
            "claims": [claim.to_public_dict() for claim in self.claims],
            "evidence_obligations": [item.to_public_dict() for item in self.evidence_obligations],
            "citation_obligations": [item.to_public_dict() for item in self.citation_obligations],
            "blocking_reasons": list(self.blocking_reasons),
            "private_safe_summary": self.private_safe_summary,
        }


@dataclass(frozen=True)
class _SourceText:
    path: Path
    path_sha256: str
    source_label: str
    text: str


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


def _read_source_texts(root: Path, inventory: MaterialInventory) -> list[_SourceText]:
    material_root = root.resolve()
    paths = [material_root] if material_root.is_file() else sorted(item for item in material_root.rglob("*") if item.is_file())
    inventory_by_path_hash = {item.path_sha256: item for item in inventory.files}
    sources: list[_SourceText] = []
    for path in paths:
        if path.suffix.lower() not in TEXT_SOURCE_EXTENSIONS:
            continue
        path_hash = _sha256_text(str(path.relative_to(material_root) if material_root.is_dir() else path.name))
        public_file = inventory_by_path_hash.get(path_hash)
        if public_file is None:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        sources.append(
            _SourceText(
                path=path,
                path_sha256=path_hash,
                source_label=public_file.path_label,
                text=_strip_markup(text),
            )
        )
    return sources


def _candidate_sentences(text: str) -> list[str]:
    normalized = _normalize_space(text)
    pieces = re.split(r"(?<=[.!?])\s+|\n+", normalized)
    sentences: list[str] = []
    for piece in pieces:
        candidate = _normalize_space(piece)
        if len(candidate) < 16:
            continue
        if candidate.startswith("@"):
            continue
        sentences.append(candidate)
    return sentences


def _strip_markup(text: str) -> str:
    stripped = re.sub(r"%.*", " ", text)
    stripped = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{([^{}]*)\})?", r" \1 ", stripped)
    stripped = stripped.replace("{", " ").replace("}", " ")
    return stripped


def _claim_type(sentence: str) -> str:
    lowered = sentence.lower()
    if re.search(r"\d", lowered) or "percent" in lowered or "%" in lowered:
        return "numeric"
    if any(term in lowered for term in ["outperform", "reduce", "reduces", "increase", "improve", "improves", "faster", "slower", "less", "more", "compared"]):
        return "comparative"
    if any(term in lowered for term in ["novel", "new", "first", "introduce", "introduces"]):
        return "novelty"
    if any(term in lowered for term in ["because", "therefore", "causes", "enables", "leads to"]):
        return "causal"
    if any(term in lowered for term in ["we propose", "we present", "method", "system", "workflow", "approach"]):
        return "method"
    return "background"


def _graph_role(claim_type: str, existing_count: int) -> str:
    if existing_count == 0 and claim_type != "background":
        return "root"
    if claim_type in HIGH_CRITICAL_CLAIM_TYPES:
        return "central_support"
    if claim_type == "background":
        return "background"
    return "local"


def _criticality(claim_type: str, graph_role: str) -> str:
    if claim_type in HIGH_CRITICAL_CLAIM_TYPES or graph_role in HIGH_CRITICAL_GRAPH_ROLES:
        return "high"
    if claim_type in MEDIUM_CRITICAL_CLAIM_TYPES:
        return "medium"
    return "low"


def _normalize_space(value: str) -> str:
    return " ".join(value.split())


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()
