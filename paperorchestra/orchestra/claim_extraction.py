from __future__ import annotations

import hashlib
import re
from pathlib import Path

from paperorchestra.orchestra.claim_records import SourceText
from paperorchestra.orchestra.draft_control import HIGH_CRITICAL_CLAIM_TYPES, HIGH_CRITICAL_GRAPH_ROLES, MEDIUM_CRITICAL_CLAIM_TYPES
from paperorchestra.orchestra.materials import MaterialInventory

TEXT_SOURCE_EXTENSIONS = {".tex", ".md", ".txt", ".rst", ".csv"}


def read_source_texts(root: Path, inventory: MaterialInventory) -> list[SourceText]:
    material_root = root.resolve()
    paths = [material_root] if material_root.is_file() else sorted(item for item in material_root.rglob("*") if item.is_file())
    inventory_by_path_hash = {item.path_sha256: item for item in inventory.files}
    sources: list[SourceText] = []
    for path in paths:
        if path.suffix.lower() not in TEXT_SOURCE_EXTENSIONS:
            continue
        path_hash = sha256_text(str(path.relative_to(material_root) if material_root.is_dir() else path.name))
        public_file = inventory_by_path_hash.get(path_hash)
        if public_file is None:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        sources.append(
            SourceText(
                path=path,
                path_sha256=path_hash,
                source_label=public_file.path_label,
                text=strip_markup(text),
            )
        )
    return sources


def candidate_sentences(text: str) -> list[str]:
    normalized = normalize_space(text)
    pieces = re.split(r"(?<=[.!?])\s+|\n+", normalized)
    sentences: list[str] = []
    for piece in pieces:
        candidate = normalize_space(piece)
        if len(candidate) < 16:
            continue
        if candidate.startswith("@"):
            continue
        sentences.append(candidate)
    return sentences


def strip_markup(text: str) -> str:
    stripped = re.sub(r"%.*", " ", text)
    stripped = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{([^{}]*)\})?", r" \1 ", stripped)
    stripped = stripped.replace("{", " ").replace("}", " ")
    return stripped


def claim_type(sentence: str) -> str:
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


def graph_role(claim_type_value: str, existing_count: int) -> str:
    if existing_count == 0 and claim_type_value != "background":
        return "root"
    if claim_type_value in HIGH_CRITICAL_CLAIM_TYPES:
        return "central_support"
    if claim_type_value == "background":
        return "background"
    return "local"


def criticality(claim_type_value: str, graph_role_value: str) -> str:
    if claim_type_value in HIGH_CRITICAL_CLAIM_TYPES or graph_role_value in HIGH_CRITICAL_GRAPH_ROLES:
        return "high"
    if claim_type_value in MEDIUM_CRITICAL_CLAIM_TYPES:
        return "medium"
    return "low"


def normalize_space(value: str) -> str:
    return " ".join(value.split())


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()
