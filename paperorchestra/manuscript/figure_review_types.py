from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class FigurePlacementWarning:
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class FigureContext:
    idx: int
    env: str
    placement: str
    block: str
    body: str
    label: str | None
    caption: str
    start: int
    end: int
    start_line: int
    end_line: int
    section_title: str
    refs: list[re.Match[str]]
    first_ref: re.Match[str] | None
    first_ref_line: int | None
    first_ref_distance_lines: int | None
    nearby_reference_context: str
    included_assets: list[str]
    plot_match: dict[str, Any] | None
    caption_relation: str
    source_origin: str

    @property
    def payload_label(self) -> str:
        return self.label or f"unnamed_{self.idx}"


@dataclass(frozen=True)
class PlacementLocationContext:
    label: str | None
    start: int
    start_line: int
    total_lines: int
    placement: str
    refs: list[re.Match[str]]
    first_ref_distance_lines: int | None
    conclusion_start: int | None
    bibliography_start: int
    tail_ratio_threshold: float
    far_reference_line_threshold: int
