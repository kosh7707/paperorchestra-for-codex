from __future__ import annotations

import re


CITE_COMMAND_RE = re.compile(
    r"(\\(?!nocite\b)(?:[A-Za-z]*cite[A-Za-z]*)\*?(?:\[[^\]]*\]){0,2})\{([^}]+)\}",
    re.IGNORECASE,
)


def extract_citation_keys(latex: str) -> set[str]:
    keys: set[str] = set()
    for match in CITE_COMMAND_RE.finditer(latex):
        for key in match.group(2).split(","):
            stripped = key.strip()
            if stripped:
                keys.add(stripped)
    return keys


def _citation_key_tokens(key: str) -> list[str]:
    return re.findall(r"[A-Z][a-z]*|[A-Z]+(?![a-z])|\d+|[a-z]+", key)


def _citation_key_aliases(key: str) -> set[str]:
    aliases = {key}
    tokens = _citation_key_tokens(key)
    if not tokens:
        return aliases
    digit_idx = next((idx for idx, token in enumerate(tokens) if token.isdigit()), len(tokens))
    prefix = tokens[:digit_idx]
    suffix = "".join(tokens[digit_idx:])
    acronym = "".join(token[0].upper() for token in prefix if token and not token.isdigit())
    if acronym:
        aliases.add(acronym + suffix)
    return aliases
