from __future__ import annotations

import re

INLINE_MATH_RE = re.compile(r"(?<!\$)\$((?:\\.|[^$\n]){1,500})\$(?!\$)")


def _move_macro_definitions_to_preamble(latex: str, macro_block: str) -> str:
    macro_lines = [line for line in macro_block.splitlines() if re.match(r"\s*\\(?:re)?newcommand\b", line)]
    if not macro_lines:
        return latex
    existing_preamble = latex[: max(latex.find("\\begin{document}"), 0)]
    missing = [line for line in macro_lines if line not in existing_preamble]
    if not missing:
        return latex
    begin_index = latex.find("\\begin{document}")
    if begin_index == -1:
        return "\n".join(missing) + "\n" + latex
    return latex[:begin_index] + "\n" + "\n".join(missing) + "\n" + latex[begin_index:]


def _ensure_text_safe_math_macros(latex: str) -> str:
    def _replace_math_command_body(match: re.Match[str]) -> str:
        command = match.group(1)
        body = match.group(2)
        if body.startswith("\\ensuremath{"):
            return match.group(0)
        return f"\\newcommand{{\\{command}}}{{\\ensuremath{{{body}}}}}"

    latex = re.sub(
        r"\\newcommand\{\\([A-Za-z]+)\}\{(\\math(?:sf|rm|it|bf|cal|bb|frak|scr)\{[^{}]*\})\}",
        _replace_math_command_body,
        latex,
    )

    def _replace_simple_math_body(match: re.Match[str]) -> str:
        command = match.group(1)
        body = match.group(2)
        if body.startswith("\\ensuremath{"):
            return match.group(0)
        if not any(token in body for token in ("_", "^", "\\")):
            return match.group(0)
        return f"\\newcommand{{\\{command}}}{{\\ensuremath{{{body}}}}}"

    return re.sub(r"\\newcommand\{\\([A-Za-z]+)\}\{([^{}\n]+)\}", _replace_simple_math_body, latex)


def _unescaped_brace_delta(text: str) -> int:
    delta = 0
    backslashes = 0
    for char in text:
        if char == "\\":
            backslashes += 1
            continue
        escaped = backslashes % 2 == 1
        backslashes = 0
        if escaped:
            continue
        if char == "{":
            delta += 1
        elif char == "}":
            delta -= 1
    return delta


def _trim_one_trailing_unescaped_brace(text: str) -> str | None:
    stripped = text.rstrip()
    if not stripped.endswith("}"):
        return None
    brace_index = len(stripped) - 1
    backslashes = 0
    probe = brace_index - 1
    while probe >= 0 and stripped[probe] == "\\":
        backslashes += 1
        probe -= 1
    if backslashes % 2 == 1:
        return None
    return stripped[:brace_index] + text[len(stripped) :]


def _repair_inline_math_surplus_closing_brace(latex: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        body = match.group(1)
        if _unescaped_brace_delta(body) != -1:
            return match.group(0)
        trimmed = _trim_one_trailing_unescaped_brace(body)
        if trimmed is None or _unescaped_brace_delta(trimmed) != 0:
            return match.group(0)
        return f"${trimmed}$"

    return INLINE_MATH_RE.sub(_replace, latex)
