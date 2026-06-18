from __future__ import annotations

import urllib.parse
from typing import Any

from paperorchestra.reviews.citation_source_payload import _clean_optional_string, _lean_source_payload
from paperorchestra.reviews.source_support_resolution_invalid import _mark_invalid_human_resolution


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
