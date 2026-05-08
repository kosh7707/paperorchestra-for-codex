from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

from .boundary import sanitize_author_facing_text


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip())
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    return cleaned or "figure"


def _aspect_ratio_dimensions(aspect_ratio: str) -> tuple[int, int]:
    presets = {
        "1:1": (960, 960),
        "16:9": (1280, 720),
        "4:3": (1200, 900),
        "3:2": (1200, 800),
        "21:9": (1400, 600),
    }
    if aspect_ratio in presets:
        return presets[aspect_ratio]
    left, right = aspect_ratio.split(":")
    width = 1200
    height = max(500, int(width * int(right) / max(int(left), 1)))
    return width, height


def _wrap_text(text: str, width: int = 56) -> list[str]:
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    current: list[str] = []
    current_len = 0
    for word in words:
        next_len = current_len + len(word) + (1 if current else 0)
        if next_len > width and current:
            lines.append(" ".join(current))
            current = [word]
            current_len = len(word)
        else:
            current.append(word)
            current_len = next_len
    if current:
        lines.append(" ".join(current))
    return lines


def _escape_tex(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
    }
    return "".join(replacements.get(ch, ch) for ch in text)


def _render_svg_figure(figure: dict[str, Any]) -> str:
    width, height = _aspect_ratio_dimensions(figure["aspect_ratio"])
    title_text = sanitize_author_facing_text(figure.get("title"), fallback="Figure")
    title = html.escape(title_text)
    plot_type = html.escape(figure["plot_type"].upper())
    caption = sanitize_author_facing_text(figure.get("caption"), fallback="")
    caption_lines = _wrap_text(caption, width=60)
    accent = "#5B8FF9" if figure.get("plot_type") == "plot" else "#36CFC9"

    caption_tspans = "".join(
        f'<tspan x="80" dy="28">{html.escape(line)}</tspan>' for line in caption_lines[:4]
    )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
  <title id="title">{title}</title>
  <desc id="desc">{html.escape(caption or title_text)}</desc>
  <rect width="100%" height="100%" fill="#0f172a" rx="36" />
  <rect x="36" y="36" width="{width - 72}" height="{height - 72}" fill="#111827" stroke="{accent}" stroke-width="4" rx="28" />
  <rect x="64" y="64" width="220" height="46" fill="{accent}" rx="14" />
  <text x="86" y="95" fill="#f8fafc" font-size="24" font-family="Arial, sans-serif" font-weight="700">{plot_type}</text>
  <text x="80" y="160" fill="#f8fafc" font-size="40" font-family="Arial, sans-serif" font-weight="700">{title}</text>
  <line x1="80" y1="220" x2="{width - 80}" y2="220" stroke="#334155" stroke-width="2" />
  <text x="80" y="292" fill="#e5e7eb" font-size="24" font-family="Arial, sans-serif" font-weight="600">Draft visual placeholder; final artwork required</text>
  <text x="80" y="{height - 176}" fill="#cbd5e1" font-size="22" font-family="Arial, sans-serif">{caption_tspans}</text>
</svg>
'''


def _render_tex_figure_snippet(figure: dict[str, Any]) -> str:
    title = _escape_tex(sanitize_author_facing_text(figure.get("title"), fallback="Figure"))
    caption = _escape_tex(sanitize_author_facing_text(figure.get("caption"), fallback=""))
    lines = [
        r"\begingroup",
        r"\setlength{\fboxsep}{12pt}",
        r"\noindent\fbox{%",
        r"\begin{minipage}{0.88\linewidth}",
        r"\centering",
        rf"\textbf{{{title}}}\\[0.6em]",
        rf"\small {caption}\\[0.6em]",
        r"\footnotesize Draft visual placeholder; final human artwork required.",
        r"\end{minipage}%",
        r"}",
        r"\endgroup",
        "",
    ]
    return "\n".join(lines)


def render_plot_assets(manifest: dict[str, Any], output_dir: str | Path) -> tuple[Path, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    assets: list[dict[str, Any]] = []
    for figure in manifest.get("figures", []):
        display_title = sanitize_author_facing_text(figure.get("title"), fallback="Figure")
        asset_slug = _slugify(figure.get("figure_id") or display_title)
        filename = asset_slug + ".svg"
        file_path = output_path / filename
        file_path.write_text(_render_svg_figure(figure), encoding="utf-8")
        tex_filename = asset_slug + ".tex"
        tex_path = output_path / tex_filename
        tex_path.write_text(_render_tex_figure_snippet(figure), encoding="utf-8")
        assets.append(
            {
                "figure_id": figure.get("figure_id"),
                "title": display_title,
                "filename": filename,
                "latex_path": f"build/plot-assets/{filename}",
                "latex_snippet_filename": tex_filename,
                "latex_snippet_path": f"build/plot-assets/{tex_filename}",
                "path": str(file_path),
                "tex_path": str(tex_path),
                "caption": sanitize_author_facing_text(figure.get("caption"), fallback=""),
                "plot_type": figure.get("plot_type"),
                "aspect_ratio": figure.get("aspect_ratio"),
                "asset_kind": "generated_placeholder",
                "review_status": "human_final_artwork_required",
            }
        )
    index_path = output_path / "plot-assets.json"
    index_path.write_text(json.dumps({"assets": assets}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output_path, index_path
