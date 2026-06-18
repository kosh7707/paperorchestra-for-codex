from __future__ import annotations

import re


def normalized_title(text: str | None) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def is_material_packet_section_title(title: str | None) -> bool:
    normalized = normalized_title(title)
    if not normalized:
        return False
    if normalized == "00 core macros":
        return True
    if normalized == "author notes for positioning and framing":
        return True
    if re.fullmatch(r"claim boundaries(?: for (?:the )?.+ draft)?", normalized):
        return True
    if re.fullmatch(r"author notes(?: for .+)?", normalized):
        return True
    return False


def is_material_packet_control_section_title(title: str | None) -> bool:
    normalized = normalized_title(title)
    return is_material_packet_section_title(normalized) and normalized != "00 core macros"
