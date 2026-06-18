from __future__ import annotations

import re


DANGEROUS_TEX_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\\write18",
        r"\\openout",
        r"\\readline",
        r"\\input\s*/",
        r"\\include\s*/",
        r"\\usepackage\s*\{shellesc\}",
        r"\\immediate\s*\\write",
    ]
]


def blocked_latex_pattern(source_text: str) -> str | None:
    for pattern in DANGEROUS_TEX_PATTERNS:
        if pattern.search(source_text):
            return pattern.pattern
    return None
