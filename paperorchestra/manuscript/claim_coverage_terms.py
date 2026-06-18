from __future__ import annotations

import re


def _coverage_term_variants(term: str) -> tuple[str, ...]:
    normalized = str(term).strip().lower()
    if not normalized:
        return ()
    irregular = {
        "boundary": ("boundary", "boundaries"),
        "boundaries": ("boundary", "boundaries"),
    }
    if normalized in irregular:
        return irregular[normalized]
    variants = {normalized}
    if normalized.endswith("y") and len(normalized) > 1:
        variants.add(normalized[:-1] + "ies")
    elif normalized.endswith("ies") and len(normalized) > 3:
        variants.add(normalized[:-3] + "y")
    elif normalized.endswith("s") and len(normalized) > 3:
        variants.add(normalized[:-1])
    else:
        variants.add(normalized + "s")
    return tuple(sorted(variants))


def _coverage_term_positions(section_text: str, term: str) -> tuple[int, ...]:
    lowered = section_text.lower()
    found: set[int] = set()
    for variant in _coverage_term_variants(term):
        if not variant:
            continue
        parts = [part for part in re.split(r"[\s-]+", variant) if part]
        if not parts:
            continue
        separator = r"(?:\s+|-)"
        pattern = re.compile(r"(?<![a-z0-9])" + separator.join(re.escape(part) for part in parts) + r"(?![a-z0-9])")
        found.update(match.start() for match in pattern.finditer(lowered))
    return tuple(sorted(found))


def _terms_nearby(section_text: str, terms: list[str], *, window: int = 360) -> bool:
    positioned_terms: list[tuple[int, int]] = []
    for term_index, term in enumerate(terms):
        positions = _coverage_term_positions(section_text, str(term))
        if not positions:
            return False
        positioned_terms.extend((position, term_index) for position in positions)
    positioned_terms.sort()
    required_count = len(terms)
    counts = [0] * required_count
    covered = 0
    left = 0
    for right, (right_position, right_term) in enumerate(positioned_terms):
        if counts[right_term] == 0:
            covered += 1
        counts[right_term] += 1
        while left <= right and right_position - positioned_terms[left][0] > window:
            _, left_term = positioned_terms[left]
            counts[left_term] -= 1
            if counts[left_term] == 0:
                covered -= 1
            left += 1
        if covered == required_count:
            return True
    return False
