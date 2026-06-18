from __future__ import annotations

import html


def _data_block(name: str, content: str) -> str:
    return f'<DATA_BLOCK name="{name}">\n{html.escape(content.strip())}\n</DATA_BLOCK>'


def _prompt_compact_text(
    text: str,
    *,
    head_chars: int,
    tail_chars: int = 0,
    marker: str = "[...truncated for prompt budget...]",
) -> str:
    if len(text) <= head_chars + tail_chars + len(marker):
        return text
    if tail_chars <= 0:
        return text[:head_chars].rstrip() + "\n" + marker
    return text[:head_chars].rstrip() + "\n" + marker + "\n" + text[-tail_chars:].lstrip()
