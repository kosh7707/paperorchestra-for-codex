from __future__ import annotations

import re

FIGURE_ENV_RE = re.compile(r"\\begin\{(figure\*?)\}(?:\[([^\]]*)\])?(.*?)\\end\{\1\}", re.DOTALL)
CAPTION_RE = re.compile(r"\\caption\{([^}]*)\}")
REF_RE = re.compile(
    r"\\(?:ref|autoref|cref|Cref|prettyref)\*?(?:\[[^\]]*\]){0,2}\{([^}]+)\}",
    re.IGNORECASE,
)
LABEL_RE = re.compile(r"\\label\{([^}]+)\}")
INCLUDE_GRAPHICS_RE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")
NONTECHNICAL_VISUAL_STRONG_RE = re.compile(
    r"\b(?:headshot|author[_\s-]*photo)\b",
    re.IGNORECASE,
)
NONTECHNICAL_VISUAL_CONTEXT_RE = re.compile(
    r"\b(?:author|biograph(?:y|ical)|profile)\b.*\b(?:portrait|headshot|photo|avatar)\b|"
    r"\b(?:portrait|headshot|photo|avatar)\b.*\b(?:author|biograph(?:y|ical)|profile)\b",
    re.IGNORECASE,
)
DECORATIVE_VISUAL_RE = re.compile(
    r"\b(?:decorative|ornamental|visual\s+divider)\b",
    re.IGNORECASE,
)
PROCESS_CAPTION_RE = re.compile(
    r"\b(?:supplied\s+visual\s+asset|not\s+evidence\s+for\s+(?:any\s+)?technical\s+claim|"
    r"placeholder\s+(?:figure|image|asset|caption)|caption\s+intent|figure\s+prompt|"
    r"rendering[_\s-]*brief|source[_\s-]*fidelity|author\s+biograph(?:y|ical)|author\s+photo)\b",
    re.IGNORECASE,
)
UNRELATED_CAPTION_CUE_RE = re.compile(
    r"\b(?:author|biograph(?:y|ical)|profile|decorative|placeholder|caption\s+intent|workflow|process|orchestration)\b",
    re.IGNORECASE,
)
