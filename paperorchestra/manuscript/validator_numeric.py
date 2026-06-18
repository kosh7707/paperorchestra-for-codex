from __future__ import annotations

import re

from paperorchestra.manuscript.validation_types import ValidationIssue

COMPARATIVE_CLAIM_PATTERNS = [
    "state-of-the-art",
    "sota",
    "outperform",
    "outperforms",
    "outperformed",
    "beats",
    "better than",
    "superior to",
]


def extract_decimal_like_tokens(text: str) -> set[str]:
    tokens = set()
    for match in re.finditer(r"\b\d+\.\d+(?:%|x|×)?\b|\b\d+\.\d+\\times\b|\b\d+%", text):
        token = match.group(0)
        token = token.removesuffix(r"\times").removesuffix("×").removesuffix("x")
        tokens.add(token)
    return tokens


def sanitize_layout_numbers(latex: str) -> str:
    sanitized = re.sub(r"\\begin\{thebibliography\}.*?\\end\{thebibliography\}", "<bibliography>", latex, flags=re.S)
    sanitized = re.sub(r"width\s*=\s*\d+\.\d+\\[A-Za-z]+", "width=<layout>", sanitized)
    sanitized = re.sub(r"scale\s*=\s*\d+\.\d+", "scale=<layout>", sanitized)
    sanitized = re.sub(r"p\{\d+\.\d+\\[A-Za-z]+\}", "p{<layout>}", sanitized)
    sanitized = re.sub(r"\\begin\{minipage\}\{\d+\.\d+\\[A-Za-z]+\}", r"\\begin{minipage}{<layout>}", sanitized)
    sanitized = re.sub(r"\\renewcommand\{\\arraystretch\}\{\d+\.\d+\}", r"\\renewcommand{\\arraystretch}{<layout>}", sanitized)
    sanitized = re.sub(r"\\setlength\{[^}]+\}\{\d+\.\d+\\[A-Za-z]+\}", r"\\setlength{<layout>}{<layout>}", sanitized)
    return sanitized


def check_numeric_grounding(latex: str, experimental_log_text: str | None) -> list[ValidationIssue]:
    if not experimental_log_text:
        return []
    allowed_numeric_tokens = extract_decimal_like_tokens(experimental_log_text)
    manuscript_numeric_tokens = extract_decimal_like_tokens(sanitize_layout_numbers(latex))
    unsupported_numeric_tokens = sorted(manuscript_numeric_tokens - allowed_numeric_tokens)
    if not unsupported_numeric_tokens:
        return []
    return [
        ValidationIssue(
            code="numeric_grounding_mismatch",
            severity="error",
            message="Manuscript contains decimal/percent values not grounded in the experimental log: "
            + ", ".join(unsupported_numeric_tokens),
        )
    ]


def check_comparative_claims(latex: str, experimental_log_text: str | None) -> list[ValidationIssue]:
    if not experimental_log_text:
        return []
    lowered_log = experimental_log_text.lower()
    lowered_latex = latex.lower()
    unsupported_claim_patterns = [
        pattern for pattern in COMPARATIVE_CLAIM_PATTERNS if pattern in lowered_latex and pattern not in lowered_log
    ]
    if not unsupported_claim_patterns:
        return []
    return [
        ValidationIssue(
            code="unsupported_comparative_claim",
            severity="warning",
            message="Manuscript contains comparative claims not evidenced in the experimental log: "
            + ", ".join(sorted(set(unsupported_claim_patterns))),
        )
    ]
