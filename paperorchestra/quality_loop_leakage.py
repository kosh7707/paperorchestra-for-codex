from __future__ import annotations

import subprocess
from pathlib import Path

from .quality_loop_policy import LEAKAGE_PATTERNS_ALWAYS, LEAKAGE_PATTERNS_VISUAL
from .quality_loop_utils import _read_json_if_exists

def _leakage_markers_in_text(text: str, *, source: str, visual_context: bool = False) -> list[str]:
    found: list[str] = []
    patterns = list(LEAKAGE_PATTERNS_ALWAYS)
    if visual_context:
        patterns.extend(LEAKAGE_PATTERNS_VISUAL)
    for label, pattern in patterns:
        if pattern.search(text):
            found.append(f"{label} ({source})")
    return found


def _scan_text_file_for_prompt_leakage(path: str | Path | None, *, source: str | None = None, visual_context: bool = False) -> list[str]:
    if not path:
        return []
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return []
    text = candidate.read_text(encoding="utf-8", errors="replace")
    return _leakage_markers_in_text(text, source=source or str(candidate), visual_context=visual_context)


def _plot_asset_text_paths(state) -> list[Path]:
    payload = _read_json_if_exists(state.artifacts.plot_assets_json)
    if not isinstance(payload, dict):
        return []
    result: list[Path] = []
    assets = payload.get("assets") if isinstance(payload.get("assets"), list) else []
    text_extensions = {".tex", ".svg", ".txt", ".md"}
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        for key in ("tex_path", "latex_snippet_path", "latex_path", "path"):
            value = asset.get(key)
            if not isinstance(value, str) or Path(value).suffix.lower() not in text_extensions:
                continue
            candidate = Path(value)
            if not candidate.is_absolute():
                # Generated snippets usually store either `foo.tex` or
                # `build/plot-assets/foo.tex`.  The real file lives under the
                # active run root, not relative to the manuscript artifact dir.
                index_path = Path(state.artifacts.plot_assets_json).resolve()
                run_root = index_path.parents[2] if len(index_path.parents) >= 3 else index_path.parent
                candidate = index_path.parent / value if len(candidate.parts) == 1 else run_root / value
            result.append(candidate)
    return sorted({path.resolve() for path in result})


def _pdf_text_for_prompt_leakage(path: str | Path | None) -> list[str]:
    if not path or not Path(path).exists():
        return []
    try:
        proc = subprocess.run(
            ["pdftotext", str(path), "-"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return [f"pdf_text_scan_unavailable ({path})"]
    if proc.returncode != 0:
        return [f"pdf_text_scan_unavailable ({path})"]
    return _leakage_markers_in_text(proc.stdout, source=f"{path}:pdftotext", visual_context=True)


def _manuscript_prompt_leakage(state) -> list[str]:
    found: list[str] = []
    found.extend(_scan_text_file_for_prompt_leakage(state.artifacts.paper_full_tex, source="paper_full_tex"))
    for path in _plot_asset_text_paths(state):
        found.extend(_scan_text_file_for_prompt_leakage(path, source=f"plot_asset:{path.name}", visual_context=True))
    found.extend(_pdf_text_for_prompt_leakage(state.artifacts.compiled_pdf))
    return sorted(dict.fromkeys(found))

