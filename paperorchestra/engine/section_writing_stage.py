from __future__ import annotations

import sys
from pathlib import Path

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import extract_latex, write_text
from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.engine.authoring_common import _apply_mock_watermark
from paperorchestra.engine.completion_env import _build_completion_request
from paperorchestra.engine.completion_identity import (
    _lane_owner,
    _provider_name,
)
from paperorchestra.engine.completion_runtime import _complete_with_runtime_mode
from paperorchestra.engine.reports import (
    _blocking_issues,
    _issue_messages,
    _record_validation_report,
)
from paperorchestra.engine.section_scope import _normalize_section_selection
from paperorchestra.engine.section_writing_plan_builder import build_section_writing_plan
from paperorchestra.engine.section_writing_repair import repair_section_draft_if_possible
from paperorchestra.engine.section_writing_runner import SectionWritingRun
from paperorchestra.engine.section_writing_support import normalize_section_draft, validate_section_draft
from paperorchestra.manuscript.prompts import PROMPTS
from paperorchestra.runtime.parity import record_lane_manifest
from paperorchestra.runtime.provider_base import BaseProvider


def write_sections(
    cwd: str | Path | None,
    provider: BaseProvider,
    *,
    runtime_mode: str = "compatibility",
    only_sections: list[str] | str | None = None,
    output_path: str | Path | None = None,
    claim_safe: bool = False,
) -> Path:
    return SectionWritingRun(
        cwd=cwd,
        provider=provider,
        stage=sys.modules[__name__],
        runtime_mode=runtime_mode,
        only_sections=only_sections,
        output_path=output_path,
        claim_safe=claim_safe,
    ).run()


__all__ = ["SectionWritingRun", "write_sections"]
