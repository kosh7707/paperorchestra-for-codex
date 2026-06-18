from __future__ import annotations

from pathlib import Path
from typing import Any
import urllib.parse

from paperorchestra.core.io import read_json
from paperorchestra.core.session import artifact_path
from paperorchestra.reviews.citation_source_fields import _clean_optional_string
from paperorchestra.reviews.citation_source_lean import _lean_source_payload

_SUPPORTED_ACTIONS = {"provide_source_url", "replace_citation", "weaken_claim", "remove_claim"}


def _reference_case_dir(cwd: str | Path | None, case_id: str) -> Path:
    return artifact_path(cwd, f"references/{case_id}/source.meta.json").parent


def _human_resolution_path(cwd: str | Path | None, case_id: str) -> Path:
    return _reference_case_dir(cwd, case_id) / "human-resolution.json"


def _load_human_resolution(cwd: str | Path | None, case: dict[str, Any]) -> dict[str, Any] | None:
    path = _human_resolution_path(cwd, str(case.get("id") or ""))
    if not path.exists():
        return None
    try:
        payload = read_json(path)
    except Exception:
        return {"action": "invalid", "status": "invalid", "reason": "unreadable_resolution"}
    return _validated_resolution_payload(payload, case)


def _validated_resolution_payload(payload: Any, case: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"action": "invalid", "status": "invalid", "reason": "invalid_resolution"}
    if payload.get("schema") != "citation-human-resolution/1":
        return {"action": "invalid", "status": "invalid", "reason": "invalid_schema"}
    if str(payload.get("case") or "") != str(case.get("id") or ""):
        return {"action": "invalid", "status": "invalid", "reason": "case_mismatch"}
    action = str(payload.get("action") or "").strip()
    if action not in _SUPPORTED_ACTIONS:
        return {"action": action or "invalid", "status": "invalid", "reason": "unsupported_action"}
    return payload


def _mark_invalid_human_resolution(case: dict[str, Any], resolution: dict[str, Any]) -> None:
    case["resolution"] = resolution
    case["_skip_source_resolution"] = True
    case["evidence"] = {"status": "missing", "why": str(resolution.get("reason") or "invalid_resolution")}
    case["verdict"] = "human_needed"
    case["ask"] = "Fix artifacts/references/{}/human-resolution.json or provide source.pdf/html/txt.".format(case.get("id"))


def _apply_resolution_action(case: dict[str, Any], resolution: dict[str, Any], citation_map: dict[str, Any]) -> bool:
    action = str(resolution.get("action") or "")
    if action == "provide_source_url":
        return _apply_provide_source_url(case, resolution)
    if action == "replace_citation":
        return _apply_replace_citation(case, resolution, citation_map)
    if action == "weaken_claim":
        return _apply_weaken_claim(case, resolution)
    if action == "remove_claim":
        return _apply_remove_claim(case, resolution)
    return False


def _apply_provide_source_url(case: dict[str, Any], resolution: dict[str, Any]) -> bool:
    action = "provide_source_url"
    url = _clean_optional_string(resolution.get("url"))
    parsed = urllib.parse.urlparse(url or "")
    if not url or parsed.scheme not in {"http", "https"}:
        _mark_invalid_human_resolution(case, {"action": action, "status": "invalid", "reason": "invalid_url"})
        return False
    original_source = case.get("source") if isinstance(case.get("source"), dict) else {}
    source = {key: value for key, value in original_source.items() if key not in {"url", "doi", "arxiv"}}
    source["url"] = url
    case["source"] = source
    case["resolution"] = {"action": action, "status": "applied", "url": url}
    return True


def _apply_replace_citation(case: dict[str, Any], resolution: dict[str, Any], citation_map: dict[str, Any]) -> bool:
    action = "replace_citation"
    replacement_key = _clean_optional_string(resolution.get("replacement_key"))
    raw_map = citation_map if isinstance(citation_map, dict) else {}
    if not replacement_key or replacement_key not in raw_map:
        _mark_invalid_human_resolution(
            case,
            {"action": action, "status": "invalid", "reason": "unknown_replacement_key", "replacement_key": replacement_key or ""},
        )
        return False
    original_key = str(case.get("key") or "")
    case["key"] = replacement_key
    case["source"] = _lean_source_payload(replacement_key, raw_map)
    case["resolution"] = {
        "action": action,
        "status": "applied",
        "original_key": original_key,
        "replacement_key": replacement_key,
    }
    if resolution.get("use_provided_source") is True:
        case["resolution"]["source"] = "provided"
        return False
    return True


def _apply_weaken_claim(case: dict[str, Any], resolution: dict[str, Any]) -> bool:
    action = "weaken_claim"
    target = _clean_optional_string(resolution.get("target"))
    if not target:
        _mark_invalid_human_resolution(case, {"action": action, "status": "invalid", "reason": "missing_target"})
        return False
    original_target = str(case.get("target") or "")
    case["target"] = target
    case["resolution"] = {"action": action, "status": "applied", "original_target": original_target, "target": target}
    return False


def _apply_remove_claim(case: dict[str, Any], resolution: dict[str, Any]) -> bool:
    action = "remove_claim"
    case["resolution"] = {
        "action": action,
        "status": "requires_manuscript_edit",
        "reason": _clean_optional_string(resolution.get("reason")) or "claim_removal_requested",
    }
    case["_skip_source_resolution"] = True
    case["evidence"] = {"status": "missing", "why": "claim_removal_requested"}
    case["verdict"] = "human_needed"
    case["ask"] = "Remove the unsupported claim/citation from the manuscript, then rerun citation review."
    return False


def _apply_human_resolution(cwd: str | Path | None, case: dict[str, Any], citation_map: dict[str, Any]) -> bool:
    """Apply a per-case human citation resolution.

    Returns True when evidence resolution must ignore pre-existing case-local
    source artifacts so stale source.txt/pdf/html cannot mask a human-provided
    URL or replacement citation.
    """

    resolution = _load_human_resolution(cwd, case)
    if resolution is None:
        return False
    if resolution.get("status") == "invalid":
        _mark_invalid_human_resolution(case, resolution)
        return False
    return _apply_resolution_action(case, resolution, citation_map)


__all__ = [
    "_apply_human_resolution",
    "_human_resolution_path",
    "_load_human_resolution",
    "_mark_invalid_human_resolution",
    "_reference_case_dir",
]
