from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


_PAGE_RE = re.compile(r"-(\d+)\.png$")


def render_pdf_pages(pdf_path: str | Path, render_dir: str | Path, *, dpi: int = 144) -> dict[str, Any]:
    """Render a PDF into page PNGs using poppler's pdftoppm when available."""

    pdf = Path(pdf_path).resolve()
    destination = Path(render_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    if not pdf.exists():
        return {"status": "unavailable", "backend": "pdftoppm", "reason": "pdf_missing", "pdf_path": str(pdf), "pages": []}
    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        return {"status": "unavailable", "backend": "pdftoppm", "reason": "pdftoppm_missing", "pdf_path": str(pdf), "pages": []}
    _clear_prior_page_images(destination)
    prefix = destination / "page"
    command = [pdftoppm, "-png", "-r", str(dpi), str(pdf), str(prefix)]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        return {
            "status": "fail",
            "backend": "pdftoppm",
            "reason": "render_failed",
            "returncode": completed.returncode,
            "stderr": completed.stderr[-2000:],
            "command": command,
            "pdf_path": str(pdf),
            "pages": [],
        }
    pages = _collect_rendered_pages(destination)
    return {
        "status": "pass",
        "backend": "pdftoppm",
        "dpi": dpi,
        "command": command,
        "pdf_path": str(pdf),
        "page_count": len(pages),
        "pages": pages,
    }


def _clear_prior_page_images(render_dir: Path) -> None:
    for path in render_dir.glob("page-*.png"):
        if path.is_file():
            path.unlink()


def _collect_rendered_pages(render_dir: Path) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    for path in sorted(render_dir.glob("page-*.png"), key=_page_sort_key):
        pages.append({"page": _page_number(path) or len(pages) + 1, "image_path": str(path.resolve())})
    return pages


def _page_sort_key(path: Path) -> tuple[int, str]:
    return (_page_number(path) or 10**9, path.name)


def _page_number(path: Path) -> int | None:
    match = _PAGE_RE.search(path.name)
    return int(match.group(1)) if match else None
