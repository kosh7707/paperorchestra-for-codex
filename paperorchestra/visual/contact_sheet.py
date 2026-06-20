from __future__ import annotations

import html
import os
from pathlib import Path
from typing import Any

from paperorchestra.core.io import write_text


def write_contact_sheet_indexes(page_images: list[dict[str, Any]], output_dir: str | Path) -> dict[str, Any]:
    """Write lightweight HTML/Markdown contact sheets for rendered PDF pages.

    This intentionally avoids image-composition dependencies. The reviewer-facing
    artifact is still useful in Codex/OMX contexts because it links every rendered
    page image from a single stable file.
    """

    destination = Path(output_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    normalized = _normalized_page_images(page_images, destination)
    html_path = destination / "page-contact-sheet.html"
    markdown_path = destination / "page-contact-sheet.md"
    write_text(html_path, _contact_sheet_html(normalized))
    write_text(markdown_path, _contact_sheet_markdown(normalized))
    return {
        "html": str(html_path),
        "markdown": str(markdown_path),
        "page_count": len(normalized),
    }


def _normalized_page_images(page_images: list[dict[str, Any]], base_dir: Path) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, page in enumerate(page_images, start=1):
        image_path = Path(str(page.get("image_path") or page.get("path") or "")).resolve()
        if not str(image_path):
            continue
        normalized.append(
            {
                "page": int(page.get("page") or index),
                "image_path": str(image_path),
                "href": os.path.relpath(image_path, base_dir),
            }
        )
    return normalized


def _contact_sheet_html(pages: list[dict[str, Any]]) -> str:
    cards = "\n".join(
        f"""
        <figure class=\"page-card\">
          <figcaption>Page {page['page']}</figcaption>
          <a href=\"{html.escape(page['href'])}\"><img src=\"{html.escape(page['href'])}\" alt=\"page {page['page']}\"></a>
        </figure>
        """.strip()
        for page in pages
    )
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <title>PaperOrchestra page contact sheet</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 24px; background: #f8fafc; color: #111827; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 18px; }}
    .page-card {{ margin: 0; padding: 12px; background: #ffffff; border: 1px solid #d1d5db; border-radius: 10px; }}
    figcaption {{ font-weight: 650; margin-bottom: 8px; }}
    img {{ display: block; width: 100%; height: auto; border: 1px solid #e5e7eb; background: white; }}
  </style>
</head>
<body>
  <h1>PaperOrchestra page contact sheet</h1>
  <p>Inspect every rendered page for layout, overflow, readability, and cross-figure visual consistency.</p>
  <section class=\"grid\">
{cards}
  </section>
</body>
</html>
"""


def _contact_sheet_markdown(pages: list[dict[str, Any]]) -> str:
    lines = [
        "# PaperOrchestra page contact sheet",
        "",
        "Inspect every rendered page for layout, overflow, readability, and cross-figure visual consistency.",
        "",
    ]
    for page in pages:
        lines.extend([f"## Page {page['page']}", "", f"![page {page['page']}]({page['href']})", ""])
    return "\n".join(lines).rstrip() + "\n"
