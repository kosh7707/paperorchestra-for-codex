from __future__ import annotations

import json

from paperorchestra.core.session import set_current_session
from paperorchestra.reviews.source_support_resolution import _apply_human_resolution, _human_resolution_path


def _write_resolution(tmp_path, case_id: str, payload: dict) -> None:
    path = _human_resolution_path(tmp_path, case_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema": "citation-human-resolution/1", "case": case_id, **payload}), encoding="utf-8")


def test_apply_human_resolution_provide_source_url_replaces_locator_metadata(tmp_path) -> None:
    set_current_session(tmp_path, "po-test")
    case = {"id": "case-1", "source": {"title": "Old", "url": "https://old", "doi": "10.old", "arxiv": "old"}}
    _write_resolution(tmp_path, "case-1", {"action": "provide_source_url", "url": "https://example.test/source"})

    ignore_existing = _apply_human_resolution(tmp_path, case, {})

    assert ignore_existing is True
    assert case["source"] == {"title": "Old", "url": "https://example.test/source"}
    assert case["resolution"] == {"action": "provide_source_url", "status": "applied", "url": "https://example.test/source"}


def test_apply_human_resolution_replace_citation_uses_citation_map_source(tmp_path) -> None:
    set_current_session(tmp_path, "po-test")
    case = {"id": "case-2", "key": "oldKey", "source": {"title": "Old"}}
    _write_resolution(tmp_path, "case-2", {"action": "replace_citation", "replacement_key": "newKey"})

    ignore_existing = _apply_human_resolution(
        tmp_path,
        case,
        {"newKey": {"title": "New Source", "url": "https://example.test/new", "venue": "Conference"}},
    )

    assert ignore_existing is True
    assert case["key"] == "newKey"
    assert case["source"]["title"] == "New Source"
    assert case["resolution"]["original_key"] == "oldKey"


def test_apply_human_resolution_invalid_url_marks_case_human_needed(tmp_path) -> None:
    set_current_session(tmp_path, "po-test")
    case = {"id": "case-3", "source": {"title": "Source"}}
    _write_resolution(tmp_path, "case-3", {"action": "provide_source_url", "url": "file:///tmp/source"})

    ignore_existing = _apply_human_resolution(tmp_path, case, {})

    assert ignore_existing is False
    assert case["resolution"]["reason"] == "invalid_url"
    assert case["_skip_source_resolution"] is True
    assert case["verdict"] == "human_needed"
