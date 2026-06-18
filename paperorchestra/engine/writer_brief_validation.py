from __future__ import annotations

import json
from typing import Any

from paperorchestra.core.boundary import assert_author_facing_payload
from paperorchestra.core.errors import ContractError
from paperorchestra.engine.prompt_context import _data_block


def _validate_author_facing_writer_brief(brief: dict[str, Any]) -> dict[str, Any]:
    try:
        assert_author_facing_payload(brief, label="author_facing_writer_brief.json")
    except ValueError as exc:
        raise ContractError(str(exc)) from exc
    return brief


def _author_facing_writer_brief_block(brief: dict[str, Any]) -> str:
    return _data_block(
        "scholarly_authoring_brief",
        json.dumps(_validate_author_facing_writer_brief(brief), indent=2, ensure_ascii=False),
    )
