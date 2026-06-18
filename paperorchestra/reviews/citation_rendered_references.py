from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from paperorchestra.core.io import write_json
from paperorchestra.core.session import artifact_path
from paperorchestra.loop_engine.quality.utils import _file_sha256, _read_json_if_exists
from paperorchestra.manuscript.citations import extract_citation_keys

RENDERED_REFERENCE_AUDIT_FILENAME = "rendered_reference_audit.json"


def rendered_reference_audit_path(cwd: str | Path | None) -> Path:
    return artifact_path(cwd, RENDERED_REFERENCE_AUDIT_FILENAME)


def _read_text(path: str | Path | None) -> str:
    if not path:
        return ""
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return ""
    return candidate.read_text(encoding="utf-8", errors="replace")


def _bib_entries(text: str) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    for match in re.finditer(r"@(\w+)\s*\{\s*([^,]+)\s*,(.*?)(?=\n@\w+\s*\{|\Z)", text, re.DOTALL):
        key = match.group(2).strip()
        body = match.group(3)
        fields: dict[str, Any] = {"entry_type": match.group(1).strip().lower()}
        for field_match in re.finditer(
            r"([A-Za-z][A-Za-z0-9_-]*)\s*=\s*(\{(?:[^{}]|\{[^{}]*\})*\}|\"[^\"]*\"|[^,\n]+)",
            body,
            re.DOTALL,
        ):
            raw = field_match.group(2).strip().rstrip(",")
            if (raw.startswith("{") and raw.endswith("}")) or (raw.startswith('"') and raw.endswith('"')):
                raw = raw[1:-1]
            fields[field_match.group(1).strip().lower()] = re.sub(r"\s+", " ", raw).strip()
        entries[key] = fields
    return entries


def _bbl_visible_keys(path: Path) -> list[str]:
    text = _read_text(path)
    return [match.group(1).strip() for match in re.finditer(r"\\bibitem(?:\[[^]]*\])?\{([^}]+)\}", text)]


def _candidate_bbl_paths(state: Any) -> list[Path]:
    candidates: list[Path] = []
    if state.artifacts.paper_full_tex:
        paper = Path(state.artifacts.paper_full_tex)
        candidates.append(paper.with_suffix(".bbl"))
    compile_report = _read_json_if_exists(state.artifacts.latest_compile_report_json)
    if isinstance(compile_report, dict):
        pdf_path = compile_report.get("pdf_path")
        if isinstance(pdf_path, str):
            candidates.append(Path(pdf_path).with_suffix(".bbl"))
    seen: set[Path] = set()
    result: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve() if candidate.exists() else candidate
        if resolved not in seen:
            seen.add(resolved)
            result.append(candidate)
    return result


def _visible_reference_keys(state: Any) -> tuple[str, list[str]]:
    for path in _candidate_bbl_paths(state):
        if path.exists():
            keys = _bbl_visible_keys(path)
            if keys:
                return "bbl_bibitems", keys
    latex = _read_text(state.artifacts.paper_full_tex)
    return "tex_cited_keys_fallback", sorted(extract_citation_keys(latex))


def _is_unknown_value(value: str | None) -> bool:
    normalized = re.sub(r"\s+", " ", str(value or "").strip()).lower()
    return normalized in {"", "unknown", "n/a", "na", "none", "null", "tbd", "todo", "anonymous"}


def _entry_unknown_fields(entry: dict[str, Any]) -> list[str]:
    fields: list[str] = []
    if _is_unknown_value(str(entry.get("title") or "")):
        fields.append("title")
    if _is_unknown_value(str(entry.get("author") or entry.get("editor") or entry.get("organization") or "")):
        fields.append("author_or_organization")
    if _is_unknown_value(str(entry.get("year") or entry.get("date") or "")):
        fields.append("year_or_date")
    return fields


_STABLE_REFERENCE_IDENTITY_FIELDS = {
    "doi",
    "url",
    "eprint",
    "archiveprefix",
    "arxiv",
    "pmid",
    "pmcid",
    "isbn",
    "issn",
    "howpublished",
    "number",
    "reportnumber",
}
_REFERENCE_IDENTITY_FALLBACK_FIELDS = {
    "journal",
    "booktitle",
    "venue",
    "publisher",
    "institution",
    "organization",
    "school",
    "series",
}


def _has_known_field(entry: dict[str, Any], fields: set[str]) -> bool:
    for field in fields:
        value = entry.get(field)
        if value is not None and not _is_unknown_value(str(value)):
            return True
    return False


def _entry_has_stable_identity(entry: dict[str, Any]) -> bool:
    """Return whether a visible reference has enough identity to be auditable.

    This is deliberately generic: DOI/URL/eprint-like fields are strongest,
    while venue/publisher/organization/institution fields are acceptable
    fallback identity for standards, books, reports, and proceedings.  The
    rendered-reference audit records weak identity; citation-quality decides
    whether that weakness is load-bearing for a critical claim.
    """

    return _has_known_field(entry, _STABLE_REFERENCE_IDENTITY_FIELDS) or _has_known_field(
        entry,
        _REFERENCE_IDENTITY_FALLBACK_FIELDS,
    )


def _normalize_doi(value: Any) -> str | None:
    text = re.sub(r"\s+", "", str(value or "").strip())
    if not text or _is_unknown_value(text):
        return None
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^doi:\s*", "", text, flags=re.IGNORECASE)
    text = text.strip(" .;,")
    return text.lower() or None


def _normalize_url_for_identity(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text or _is_unknown_value(text):
        return None
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", text):
        parts = urlsplit(text)
    else:
        parts = urlsplit(f"https://{text}")
    host = (parts.hostname or "").lower()
    if not host:
        return None
    port = f":{parts.port}" if parts.port else ""
    path = re.sub(r"/+", "/", parts.path or "/").rstrip("/") or "/"
    # Deliberately drop scheme, credentials, fragment, and token-like query
    # params.  Keep non-sensitive query params in the hash input so distinct
    # landing resources such as ?id=1 and ?id=2 do not collapse.
    sensitive_query_keys = {
        "access_token",
        "api_key",
        "auth",
        "credential",
        "key",
        "pass",
        "passwd",
        "password",
        "secret",
        "session",
        "sig",
        "signature",
        "token",
    }
    query_items = []
    for key, item_value in parse_qsl(parts.query, keep_blank_values=True):
        normalized_key = key.strip().lower()
        if any(marker in normalized_key for marker in sensitive_query_keys):
            continue
        query_items.append((normalized_key, item_value.strip()))
    query = urlencode(sorted(query_items), doseq=True)
    return urlunsplit(("", f"{host}{port}", path, query, ""))


def _hash_identity(prefix: str, value: str) -> str:
    return f"{prefix}:{hashlib.sha256(value.encode('utf-8')).hexdigest()[:12]}"


def _normalize_eprint(value: Any) -> str | None:
    text = re.sub(r"\s+", "", str(value or "").strip())
    if not text or _is_unknown_value(text):
        return None
    text = re.sub(r"^arxiv:", "", text, flags=re.IGNORECASE)
    return text.lower().strip(" .;,") or None


def _standard_identity_from_text(value: Any) -> str | None:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text or _is_unknown_value(text):
        return None
    match = re.search(r"\b(rfc)\s*-?\s*(\d{3,5})\b", text, flags=re.IGNORECASE)
    if match:
        return f"standard:{match.group(1).lower()}-{match.group(2)}"
    return None


def _normalize_report_number(value: Any) -> str | None:
    text = re.sub(r"\s+", "-", str(value or "").strip().lower())
    text = re.sub(r"[^a-z0-9._-]+", "-", text).strip("-._")
    if not text or _is_unknown_value(text):
        return None
    return text


def _namespace_for_report(entry: dict[str, Any]) -> str | None:
    fields = ("organization", "institution", "venue", "journal", "booktitle", "series", "publisher", "school")
    values = [str(entry.get(field) or "").strip().lower() for field in fields if not _is_unknown_value(str(entry.get(field) or ""))]
    if not values:
        return None
    namespace = re.sub(r"\s+", "-", values[0])
    namespace = re.sub(r"[^a-z0-9._-]+", "-", namespace).strip("-._")
    return namespace or None


def _reference_identity_label(entry: dict[str, Any]) -> str | None:
    doi = _normalize_doi(entry.get("doi"))
    if doi:
        return f"doi:{doi}"

    url = _normalize_url_for_identity(entry.get("url"))
    if url:
        return _hash_identity("url", url)

    arxiv = _normalize_eprint(entry.get("arxiv"))
    if arxiv:
        return f"arxiv:{arxiv}"

    eprint = _normalize_eprint(entry.get("eprint"))
    if eprint:
        archive = str(entry.get("archiveprefix") or "eprint").strip().lower() or "eprint"
        archive = re.sub(r"[^a-z0-9._-]+", "-", archive).strip("-._") or "eprint"
        return f"{archive}:{eprint}"

    for field in ("number", "reportnumber", "howpublished"):
        standard = _standard_identity_from_text(entry.get(field))
        if standard:
            return standard

    namespace = _namespace_for_report(entry)
    if namespace:
        for field in ("reportnumber", "number", "howpublished"):
            report_number = _normalize_report_number(entry.get(field))
            if report_number:
                return f"report:{namespace}:{report_number}"
    return None


def _duplicate_reference_identity_groups(visible_keys: list[str], entries: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    by_identity: dict[str, list[str]] = {}
    for key in visible_keys:
        entry = entries.get(key)
        if not entry:
            continue
        identity = _reference_identity_label(entry)
        if not identity:
            continue
        by_identity.setdefault(identity, []).append(key)
    groups = [
        {"identity": identity, "keys": sorted(dict.fromkeys(keys))}
        for identity, keys in by_identity.items()
        if len(set(keys)) > 1
    ]
    return sorted(groups, key=lambda group: (str(group["identity"]), list(group["keys"])))


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

