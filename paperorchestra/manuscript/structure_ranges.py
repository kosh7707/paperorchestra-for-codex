from __future__ import annotations

from paperorchestra.manuscript.structure_patterns import SECTION_COMMAND_RE
from paperorchestra.manuscript.structure_titles import _canonical_generated_section_title


def _section_range_map(latex: str) -> dict[str, tuple[int, int]]:
    matches = list(SECTION_COMMAND_RE.finditer(latex))
    ranges: dict[str, tuple[int, int]] = {}
    for idx, match in enumerate(matches):
        start = match.start()
        next_start = matches[idx + 1].start() if idx + 1 < len(matches) else latex.find("\\end{document}", match.end())
        end = next_start if next_start != -1 else len(latex)
        ranges[match.group(1).strip().lower()] = (start, end)
    return ranges


def _normalized_section_range_map(latex: str) -> dict[str, tuple[int, int]]:
    return {_canonical_generated_section_title(title): span for title, span in _section_range_map(latex).items()}
