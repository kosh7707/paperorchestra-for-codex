from __future__ import annotations

from typing import Any

from paperorchestra.domains import get_domain


def _source_grounding_text(inputs: dict[str, str]) -> str:
    return "\n\n".join(
        part
        for part in (
            inputs.get("experimental_log", ""),
            inputs.get("idea", ""),
            inputs.get("template", ""),
        )
        if part
    )


def _source_critical_context_for_prompt(
    inputs: dict[str, str],
    *,
    window_chars: int = 1400,
    max_blocks_per_kind: int = 3,
) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int, int]] = set()
    patterns = get_domain().source_critical_patterns
    for source_name in ("idea", "experimental_log", "template"):
        text = inputs.get(source_name) or ""
        if not text:
            continue
        for kind, pattern in patterns:
            count_for_kind = sum(1 for block in blocks if block["source"] == source_name and block["kind"] == kind)
            if count_for_kind >= max_blocks_per_kind:
                continue
            for match in pattern.finditer(text):
                count_for_kind = sum(1 for block in blocks if block["source"] == source_name and block["kind"] == kind)
                if count_for_kind >= max_blocks_per_kind:
                    break
                start = max(0, match.start() - window_chars // 2)
                end = min(len(text), match.end() + window_chars // 2)
                excerpt = text[start:end].strip()
                key = (source_name, kind, start, end)
                if not excerpt or key in seen:
                    continue
                seen.add(key)
                blocks.append(
                    {
                        "source": source_name,
                        "kind": kind,
                        "anchor": match.group(0),
                        "start_char": start,
                        "end_char": end,
                        "excerpt": excerpt,
                    }
                )
    return {
        "schema_version": "source-critical-context/1",
        "description": "Exact source spans selected to prevent prompt truncation from hiding critical material.",
        "blocks": blocks[:30],
    }
