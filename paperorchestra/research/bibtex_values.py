from __future__ import annotations

_BIBTEX_ESCAPED_VALUE_CHARS = frozenset("&%_$#")


def _validate_bibtex_value(value: str, *, field: str) -> None:
    depth = 0
    trailing_backslashes = 0
    for index, ch in enumerate(value):
        if ord(ch) < 32 and ch not in "\t\n":
            raise ValueError(f"BibTeX field '{field}' contains an unsupported control character at position {index}.")
        if ch == "\\":
            trailing_backslashes += 1
            continue
        escaped = trailing_backslashes % 2 == 1
        trailing_backslashes = 0
        if ch == "{" and not escaped:
            depth += 1
        elif ch == "}" and not escaped:
            if depth == 0:
                raise ValueError(f"BibTeX field '{field}' contains an unmatched closing brace.")
            depth -= 1
    if depth:
        raise ValueError(f"BibTeX field '{field}' contains unbalanced braces.")
    if trailing_backslashes % 2 == 1:
        raise ValueError(f"BibTeX field '{field}' ends with a dangling backslash.")


def _escape_bibtex_value(value: str, *, field: str) -> str:
    _validate_bibtex_value(value, field=field)
    escaped: list[str] = []
    trailing_backslashes = 0
    for ch in value:
        if ch == "\\":
            escaped.append(ch)
            trailing_backslashes += 1
            continue
        is_escaped = trailing_backslashes % 2 == 1
        trailing_backslashes = 0
        if ch in _BIBTEX_ESCAPED_VALUE_CHARS and not is_escaped:
            escaped.append("\\")
        escaped.append(ch)
    return "".join(escaped)
