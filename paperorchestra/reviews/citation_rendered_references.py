from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import write_json
from paperorchestra.core.session import artifact_path
from paperorchestra.loop_engine.quality.utils import _file_sha256
from paperorchestra.manuscript.citations import extract_citation_keys
from paperorchestra.reviews.citation_reference_identity import (
    _duplicate_reference_identity_groups,
    _entry_has_stable_identity,
    _entry_unknown_fields,
    _reference_identity_label,
)
from paperorchestra.reviews.citation_reference_inputs import _bib_entries, _read_text, _visible_reference_keys

RENDERED_REFERENCE_AUDIT_FILENAME = "rendered_reference_audit.json"


def rendered_reference_audit_path(cwd: str | Path | None) -> Path:
    return artifact_path(cwd, RENDERED_REFERENCE_AUDIT_FILENAME)


def build_rendered_reference_audit(cwd: str | Path | None, *, quality_mode: str = "ralph") -> dict[str, Any]:
    from paperorchestra.core.session import load_session

    state = load_session(cwd)
    manuscript_sha = _file_sha256(state.artifacts.paper_full_tex)
    cited_keys = sorted(extract_citation_keys(_read_text(state.artifacts.paper_full_tex)))
    entries = _bib_entries(_read_text(state.artifacts.references_bib))
    denominator_source, visible_keys_raw = _visible_reference_keys(state)
    visible_keys = sorted(dict.fromkeys(key for key in visible_keys_raw if key))
    bib_keys = set(entries)
    visible_key_set = set(visible_keys)
    cited_key_set = set(cited_keys)
    missing_bib = sorted(visible_key_set - bib_keys)
    unknown: list[str] = []
    weak_identity: list[str] = []
    malformed: dict[str, list[str]] = {}
    for key in visible_keys:
        entry = entries.get(key)
        if not entry:
            continue
        fields = _entry_unknown_fields(entry)
        if fields:
            unknown.append(key)
            malformed[key] = fields
            continue
        if not _entry_has_stable_identity(entry):
            weak_identity.append(key)
    duplicate_identity_groups = _duplicate_reference_identity_groups(visible_keys, entries)
    unused = sorted(bib_keys - cited_key_set)
    failing: list[str] = []
    if missing_bib:
        failing.append("rendered_reference_missing_bib_key")
    if unknown:
        failing.append("rendered_reference_unknown_metadata")
    if duplicate_identity_groups:
        failing.append("rendered_reference_duplicate_identity")
    if quality_mode == "claim_safe" and denominator_source == "tex_cited_keys_fallback":
        failing.append("rendered_reference_denominator_not_visible")
    return {
        "schema_version": "rendered-reference-audit/1",
        "status": "fail" if failing else "pass",
        "manuscript_sha256": manuscript_sha,
        "paper_full_tex_sha256": manuscript_sha,
        "denominator_source": denominator_source,
        "visible_reference_count": len(visible_keys),
        "visible_reference_keys": visible_keys,
        "bib_entry_count": len(entries),
        "bib_keys": sorted(entries),
        "cited_key_count": len(cited_keys),
        "cited_keys": cited_keys,
        "unused_bib_keys": unused,
        "missing_bib_keys_for_cites": missing_bib,
        "unknown_metadata_keys": sorted(unknown),
        "weak_identity_keys": sorted(weak_identity),
        "duplicate_identity_groups": duplicate_identity_groups,
        "malformed_bibtex_keys": malformed,
        "failing_codes": sorted(dict.fromkeys(failing)),
    }


def write_rendered_reference_audit(
    cwd: str | Path | None,
    *,
    quality_mode: str = "ralph",
    output_path: str | Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    payload = build_rendered_reference_audit(cwd, quality_mode=quality_mode)
    path = Path(output_path).resolve() if output_path else rendered_reference_audit_path(cwd)
    write_json(path, payload)
    return path, payload
