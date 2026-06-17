from __future__ import annotations

from paperorchestra.feedback import human_needed
from paperorchestra.feedback import operator_answer_metadata as answer


def test_human_needed_answer_schema_constants_share_metadata_source() -> None:
    assert human_needed.HUMAN_NEEDED_PUBLIC_SCHEMA_VERSION is answer.HUMAN_NEEDED_PUBLIC_SCHEMA_VERSION
    assert human_needed.HUMAN_NEEDED_METADATA_SCHEMA_VERSION is answer.HUMAN_NEEDED_METADATA_SCHEMA_VERSION
