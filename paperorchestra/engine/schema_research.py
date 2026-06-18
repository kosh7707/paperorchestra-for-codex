from __future__ import annotations

from paperorchestra.engine.schema_common import _closed_object_schema, _string_list_schema

_CANDIDATE_ITEM_SCHEMA = _closed_object_schema(
    {
        "title_guess": {"type": "string"},
        "why_relevant": {"type": "string"},
        "origin_query": {"type": "string"},
        "role_guess": {"type": "string"},
        "discovery_source": {"type": "string"},
        "discovery_sources": _string_list_schema(),
    }
)

CANDIDATE_SCHEMA = {
    **_closed_object_schema(
        {
            "macro_candidates": {"type": "array", "items": _CANDIDATE_ITEM_SCHEMA},
            "micro_candidates": {"type": "array", "items": _CANDIDATE_ITEM_SCHEMA},
        }
    )
}

_PRIOR_WORK_ENTRY_SCHEMA = _closed_object_schema(
    {
        "title": {"type": "string"},
        "authors": _string_list_schema(),
        "year": {"type": ["integer", "null"]},
        "venue": {"type": ["string", "null"]},
        "url": {"type": ["string", "null"]},
        "doi": {"type": ["string", "null"]},
        "source": {"type": "string"},
        "why_relevant": {"type": "string"},
        "provenance_notes": _string_list_schema(),
    }
)

PRIOR_WORK_SEED_SCHEMA = _closed_object_schema(
    {
        "references": {"type": "array", "items": _PRIOR_WORK_ENTRY_SCHEMA},
        "research_notes": _string_list_schema(),
    }
)
