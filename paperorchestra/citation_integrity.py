from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .io_utils import write_json
from .quality_loop_utils import _file_sha256, _read_json_if_exists
from .session import artifact_path
from .validator import extract_citation_keys

CITATION_INTEGRITY_AUDIT_FILENAME = "citation_integrity.audit.json"
CITATION_INTEGRITY_CRITIC_FILENAME = "citation_integrity.critic.json"
RENDERED_REFERENCE_AUDIT_FILENAME = "rendered_reference_audit.json"


def citation_integrity_audit_path(cwd: str | Path | None) -> Path:
    return artifact_path(cwd, CITATION_INTEGRITY_AUDIT_FILENAME)


def citation_integrity_critic_path(cwd: str | Path | None) -> Path:
    return artifact_path(cwd, CITATION_INTEGRITY_CRITIC_FILENAME)


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


def build_rendered_reference_audit(cwd: str | Path | None, *, quality_mode: str = "ralph") -> dict[str, Any]:
    from .session import load_session

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
    malformed: dict[str, list[str]] = {}
    for key in visible_keys:
        entry = entries.get(key)
        if not entry:
            continue
        fields = _entry_unknown_fields(entry)
        if fields:
            unknown.append(key)
            malformed[key] = fields
    unused = sorted(bib_keys - cited_key_set)
    failing: list[str] = []
    if missing_bib:
        failing.append("rendered_reference_missing_bib_key")
    if unknown:
        failing.append("rendered_reference_unknown_metadata")
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


def _payload_status(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    raw = payload.get("status") or payload.get("verdict") or payload.get("overall_status")
    return str(raw).strip().lower() if raw is not None else None


def _artifact_check(
    path: Path,
    *,
    expected_manuscript_sha256: str | None,
    missing_code: str,
    stale_code: str,
    failed_code: str,
    unbound_code: str | None = None,
    require_binding: bool = False,
) -> dict[str, Any]:
    payload = _read_json_if_exists(path)
    if not isinstance(payload, dict):
        return {
            "status": "fail",
            "path": str(path),
            "sha256": None,
            "failing_codes": [missing_code],
            "reason": "missing_or_unreadable",
        }
    failing: list[str] = []
    manuscript_sha = payload.get("manuscript_sha256") or payload.get("paper_full_tex_sha256")
    if require_binding and expected_manuscript_sha256 and not manuscript_sha:
        failing.append(unbound_code or stale_code)
    if expected_manuscript_sha256 and manuscript_sha and manuscript_sha != expected_manuscript_sha256:
        failing.append(stale_code)
    status = _payload_status(payload)
    if status in {"fail", "failed", "reject", "rejected", "block", "blocked"}:
        failing.append(failed_code)
    for code in payload.get("failing_codes") or []:
        if isinstance(code, str) and code:
            failing.append(code)
    return {
        "status": "fail" if failing else "pass",
        "path": str(path),
        "sha256": _file_sha256(path),
        "artifact_status": status,
        "manuscript_sha256": manuscript_sha,
        "expected_manuscript_sha256": expected_manuscript_sha256,
        "failing_codes": sorted(dict.fromkeys(failing)),
    }


def citation_integrity_check(cwd: str | Path | None, state: Any, *, quality_mode: str = "ralph") -> dict[str, Any]:
    """Return the claim-safe Citation Integrity/Critic gate status."""

    expected_manuscript_sha256 = _file_sha256(state.artifacts.paper_full_tex)
    integrity = _artifact_check(
        citation_integrity_audit_path(cwd),
        expected_manuscript_sha256=expected_manuscript_sha256,
        missing_code="citation_integrity_missing",
        stale_code="citation_integrity_stale",
        failed_code="citation_integrity_failed",
        unbound_code="citation_integrity_unbound",
        require_binding=quality_mode == "claim_safe",
    )
    critic = _artifact_check(
        citation_integrity_critic_path(cwd),
        expected_manuscript_sha256=expected_manuscript_sha256,
        missing_code="citation_critic_missing",
        stale_code="citation_critic_stale",
        failed_code="citation_critic_failed",
        unbound_code="citation_critic_unbound",
        require_binding=quality_mode == "claim_safe",
    )
    rendered = _artifact_check(
        rendered_reference_audit_path(cwd),
        expected_manuscript_sha256=expected_manuscript_sha256,
        missing_code="rendered_reference_audit_missing",
        stale_code="rendered_reference_audit_stale",
        failed_code="rendered_reference_audit_failed",
        unbound_code="rendered_reference_audit_unbound",
        require_binding=quality_mode == "claim_safe",
    )
    failing_codes: list[str] = []
    if quality_mode == "claim_safe":
        failing_codes.extend(integrity["failing_codes"])
        failing_codes.extend(critic["failing_codes"])
        failing_codes.extend(rendered["failing_codes"])
    else:
        for check in (integrity, critic, rendered):
            failing_codes.extend(code for code in check["failing_codes"] if not code.endswith("_missing"))
    return {
        "status": "fail" if failing_codes else "pass",
        "failing_codes": sorted(dict.fromkeys(failing_codes)),
        "manuscript_sha256": expected_manuscript_sha256,
        "citation_integrity_audit": integrity,
        "citation_integrity_critic": critic,
        "rendered_reference_audit": rendered,
        "mode_effect": "hard_fail_in_claim_safe" if quality_mode == "claim_safe" else "missing_artifacts_allowed_outside_claim_safe",
    }


def _citation_support_review_path(cwd: str | Path | None, state: Any) -> Path:
    if state.artifacts.paper_full_tex:
        return Path(state.artifacts.paper_full_tex).resolve().parent / "citation_support_review.json"
    return artifact_path(cwd, "citation_support_review.json")


def _sentences_with_cites(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", text) if "\\cite" in part]


def _cite_key_counts_from_text(text: str) -> tuple[list[dict[str, Any]], dict[str, int]]:
    sentences = _sentences_with_cites(text)
    records: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for idx, sentence in enumerate(sentences, start=1):
        keys = sorted(extract_citation_keys(sentence))
        records.append({"id": f"tex-sentence-{idx}", "sentence": sentence, "citation_keys": keys})
        for key in keys:
            counts[key] = counts.get(key, 0) + 1
    return records, counts


def _support_items(cwd: str | Path | None, state: Any) -> list[dict[str, Any]]:
    payload = _read_json_if_exists(_citation_support_review_path(cwd, state))
    items = payload.get("items") if isinstance(payload, dict) else None
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _role_tokens(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, list):
        return {str(item).strip() for item in value if str(item).strip()}
    return {str(value).strip()} if str(value).strip() else set()


def _placement_roles(state: Any) -> dict[str, set[str]]:
    payload = _read_json_if_exists(state.artifacts.citation_placement_plan_json)
    placements = payload.get("placements") if isinstance(payload, dict) else None
    result: dict[str, set[str]] = {}
    if not isinstance(placements, list):
        return result
    for item in placements:
        if not isinstance(item, dict):
            continue
        keys = []
        for key_field in ["citation_key", "key"]:
            if item.get(key_field):
                keys.append(str(item.get(key_field)))
        keys.extend(str(key) for key in item.get("citation_keys") or [])
        roles = set()
        for field in ["claim_id", "claim_ids", "citation_role", "citation_roles", "support_role"]:
            roles.update(_role_tokens(item.get(field)))
        for key in keys:
            result.setdefault(key, set()).update(roles)
    return result


def _duplicate_support_failures(items: list[dict[str, Any]], text_counts: dict[str, int], placement_roles: dict[str, set[str]]) -> list[str]:
    counts = dict(text_counts)
    roles_by_key: dict[str, set[str]] = {key: set(value) for key, value in placement_roles.items()}
    if items:
        counts = {}
        for item in items:
            keys = [str(key) for key in item.get("citation_keys") or []]
            item_roles = set()
            for field in ["claim_id", "claim_ids", "citation_role", "citation_roles", "support_role"]:
                item_roles.update(_role_tokens(item.get(field)))
            for key in keys:
                counts[key] = counts.get(key, 0) + 1
                roles_by_key.setdefault(key, set()).update(item_roles)
    return sorted(key for key, count in counts.items() if count > 3 and len(roles_by_key.get(key, set())) < 2)


def _claim_map_context_violations(state: Any) -> list[str]:
    payload = _read_json_if_exists(state.artifacts.claim_map_json)
    claims = payload.get("claims") if isinstance(payload, dict) else None
    if not isinstance(claims, list):
        return []
    violations: list[str] = []
    citation_required_types = {"external_literature", "standard", "benchmark_reference", "prior_work"}
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_id = str(claim.get("id") or claim.get("claim_id") or "unknown")
        claim_type = str(claim.get("claim_type") or "").strip().lower()
        keys = [key for key in claim.get("citation_keys") or [] if str(key).strip()]
        if claim_type == "own_contribution" and keys:
            violations.append(claim_id)
            continue
        required_source = str(claim.get("required_source_type") or "").strip().lower()
        explicit_required = claim.get("citation_required") is True or required_source in citation_required_types
        if explicit_required and claim.get("required", True) is not False and not keys:
            violations.append(claim_id)
    return sorted(violations)


def build_citation_integrity_audit(cwd: str | Path | None, *, quality_mode: str = "ralph") -> dict[str, Any]:
    from .session import load_session

    state = load_session(cwd)
    manuscript_sha = _file_sha256(state.artifacts.paper_full_tex)
    latex = _read_text(state.artifacts.paper_full_tex)
    sentence_records, text_counts = _cite_key_counts_from_text(latex)
    items = _support_items(cwd, state)
    placement_roles = _placement_roles(state)
    citation_bomb_sentences = [record for record in sentence_records if len(record.get("citation_keys") or []) > 3]
    paragraph_keys = [sorted(extract_citation_keys(paragraph)) for paragraph in re.split(r"\n\s*\n", latex)]
    citation_bomb_paragraphs = [keys for keys in paragraph_keys if len(keys) > 5]
    duplicate_keys = _duplicate_support_failures(items, text_counts, placement_roles)
    mismatch_statuses = {"unsupported", "contradicted"}
    if quality_mode == "claim_safe":
        mismatch_statuses.update({"metadata_only", "insufficient_evidence"})
    mismatch_items = [
        item for item in items if str(item.get("support_status") or "").strip().lower() in mismatch_statuses
    ]
    context_violations = _claim_map_context_violations(state)
    failing: list[str] = []
    if citation_bomb_sentences or citation_bomb_paragraphs:
        failing.append("citation_bomb_detected")
    if duplicate_keys:
        failing.append("citation_duplicate_support")
    if mismatch_items:
        failing.append("claim_source_mismatch")
    if context_violations:
        failing.append("citation_context_policy_violation")
    return {
        "schema_version": "citation-integrity-audit/1",
        "status": "fail" if failing else "pass",
        "manuscript_sha256": manuscript_sha,
        "paper_full_tex_sha256": manuscript_sha,
        "failing_codes": sorted(dict.fromkeys(failing)),
        "checks": {
            "citation_density": {
                "status": "fail" if citation_bomb_sentences or citation_bomb_paragraphs else "pass",
                "bomb_sentences": citation_bomb_sentences,
                "bomb_paragraph_key_sets": citation_bomb_paragraphs,
                "max_keys_per_sentence": 3,
                "max_keys_per_paragraph": 5,
            },
            "duplicate_support": {
                "status": "fail" if duplicate_keys else "pass",
                "duplicate_keys": duplicate_keys,
                "threshold_repeated_sentences": 3,
                "min_distinct_role_or_claim_count": 2,
            },
            "claim_source_match": {
                "status": "fail" if mismatch_items else "pass",
                "mismatch_item_ids": [str(item.get("id") or item.get("sentence") or "unknown") for item in mismatch_items],
                "failing_statuses": sorted(mismatch_statuses),
            },
            "context_policy": {
                "status": "fail" if context_violations else "pass",
                "violating_claim_ids": context_violations,
            },
        },
    }


def write_citation_integrity_audit(
    cwd: str | Path | None,
    *,
    quality_mode: str = "ralph",
    output_path: str | Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    payload = build_citation_integrity_audit(cwd, quality_mode=quality_mode)
    path = Path(output_path).resolve() if output_path else citation_integrity_audit_path(cwd)
    write_json(path, payload)
    return path, payload
