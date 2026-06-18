from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from paperorchestra.manuscript.figure_patterns import FIGURE_ENV_RE, LABEL_RE
from paperorchestra.manuscript.structure import _insert_block_into_section, _preferred_section_name


def _normalize_plot_context_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"^fig(?:ure)?[:_\-\s]+", "", text)
    text = Path(text).stem if "/" in text or "\\" in text or "." in Path(text).name else text
    return re.sub(r"[^a-z0-9]+", "", text)


def _normalize_figure_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _escape_latex_text(text: str) -> str:
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


def _is_generated_placeholder_asset(asset: dict[str, Any]) -> bool:
    return asset.get("asset_kind") == "generated_placeholder" or asset.get("review_status") == "human_final_artwork_required"


def _reviewable_plot_assets_index(plot_assets_index: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(plot_assets_index, dict):
        return {"assets": []}
    return {
        **plot_assets_index,
        "assets": [
            asset
            for asset in plot_assets_index.get("assets", [])
            if isinstance(asset, dict) and not _is_generated_placeholder_asset(asset)
        ],
    }


def _reviewable_plot_manifest(plot_manifest: dict[str, Any] | None, plot_assets_index: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(plot_manifest, dict):
        return {"figures": []}
    placeholder_ids = {
        str(asset.get("figure_id"))
        for asset in (plot_assets_index or {}).get("assets", [])
        if isinstance(asset, dict) and _is_generated_placeholder_asset(asset) and asset.get("figure_id")
    }
    if not placeholder_ids:
        return plot_manifest
    return {
        **plot_manifest,
        "figures": [
            figure
            for figure in plot_manifest.get("figures", [])
            if not (isinstance(figure, dict) and str(figure.get("figure_id") or "") in placeholder_ids)
        ],
    }


def _filter_plot_context_for_latex(
    latex: str | None,
    plot_manifest: dict[str, Any],
    plot_assets_index: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not latex:
        return {"figures": []}, {"assets": []}
    raw_refs: set[str] = set()
    for group in re.findall(r"\\(?:ref|autoref|cref|Cref|prettyref)\*?(?:\[[^\]]*\]){0,2}\{([^}]+)\}", latex):
        raw_refs.update(part.strip() for part in group.split(",") if part.strip())
    raw_refs.update(token for token in re.findall(r"\\label\{([^}]+)\}", latex))
    referenced_tokens = {_normalize_plot_context_key(token) for token in raw_refs}
    included_raw = re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", latex)
    included_raw.extend(re.findall(r"\\input\{([^}]+)\}", latex))
    included = {_normalize_plot_context_key(token) for token in included_raw}
    asset_matches: list[dict[str, Any]] = []
    figure_ids: set[str] = set()
    for asset in plot_assets_index.get("assets", []) if isinstance(plot_assets_index, dict) else []:
        if not isinstance(asset, dict):
            continue
        asset_names = {
            _normalize_plot_context_key(asset.get(field))
            for field in ("filename", "latex_path", "latex_snippet_path")
            if asset.get(field)
        }
        fid = str(asset.get("figure_id") or "")
        fid_key = _normalize_plot_context_key(fid)
        if included & asset_names or (fid_key and fid_key in referenced_tokens):
            asset_matches.append(asset)
            if fid:
                figure_ids.add(fid_key)
    figure_matches = []
    for figure in plot_manifest.get("figures", []) if isinstance(plot_manifest, dict) else []:
        if not isinstance(figure, dict):
            continue
        fid = str(figure.get("figure_id") or "")
        fid_key = _normalize_plot_context_key(fid)
        if fid and (fid_key in figure_ids or fid_key in referenced_tokens or fid.lower() in latex.lower()):
            figure_matches.append(figure)
    return {**plot_manifest, "figures": figure_matches}, {**plot_assets_index, "assets": asset_matches}


def _ensure_generated_plot_usage(latex: str, plot_assets_index: dict[str, Any]) -> str:
    assets = plot_assets_index.get("assets", []) if isinstance(plot_assets_index, dict) else []
    rendered = latex
    for asset in assets:
        if not isinstance(asset, dict) or _is_generated_placeholder_asset(asset):
            continue
        figure_id = asset.get("figure_id", "")
        title = asset.get("title", "")
        caption = asset.get("caption", title)
        snippet_path = asset.get("latex_snippet_path") or asset.get("latex_path")
        filename = asset.get("filename", "")
        label_present = bool(figure_id and f"\\label{{{figure_id}}}" in rendered)
        asset_present = any(token and token in rendered for token in [snippet_path, filename])
        escaped_caption = _escape_latex_text(caption) if isinstance(caption, str) else ""
        caption_present = bool(
            escaped_caption and (f"\\caption{{{escaped_caption}}}" in rendered or f"\\caption{{{caption}}}" in rendered)
        )
        if label_present or asset_present or caption_present:
            continue
        include = (
            f"\\input{{{snippet_path}}}"
            if isinstance(snippet_path, str) and snippet_path.endswith(".tex")
            else f"\\includegraphics[width=0.85\\linewidth]{{{snippet_path}}}"
        )
        block = (
            f"\n% PaperOrchestra:auto-repaired figure:{figure_id}\n"
            "\\begin{figure}[!htbp]\n"
            f"{include}\n"
            f"\\caption{{{_escape_latex_text(caption)}}}\n"
            f"\\label{{{figure_id}}}\n"
            "\\end{figure}\n"
        )
        section_name = _preferred_section_name(
            rendered,
            label=figure_id,
            anchor_tokens=[title, caption, figure_id.replace("_", " ")],
        )
        rendered = _insert_block_into_section(
            rendered,
            section_name=section_name,
            block=block,
            label=figure_id,
            anchor_tokens=[title, caption, figure_id.replace("_", " ")],
        )
    return rendered


def _normalize_generated_plot_paths(latex: str, plot_assets_index: dict[str, Any]) -> str:
    assets = plot_assets_index.get("assets", []) if isinstance(plot_assets_index, dict) else []
    asset_by_label: dict[str, dict[str, Any]] = {}
    for asset in assets:
        if not isinstance(asset, dict) or _is_generated_placeholder_asset(asset):
            continue
        figure_id = asset.get("figure_id")
        if isinstance(figure_id, str) and figure_id:
            asset_by_label[_normalize_figure_token(figure_id)] = asset
        snippet_path = asset.get("latex_snippet_path")
        if not isinstance(snippet_path, str):
            continue
        filename = asset.get("filename")
        candidates: list[str] = []
        for key in ["path", "tex_path", "latex_path", "latex_snippet_path"]:
            candidate = asset.get(key)
            if isinstance(candidate, str) and candidate:
                candidates.append(candidate)
                latex = latex.replace(candidate, snippet_path)
        if snippet_path.endswith(".tex"):
            for candidate in [snippet_path, *candidates]:
                if not candidate:
                    continue
                latex = re.sub(
                    rf"\\includegraphics(?:\[[^\]]*\])?\{{{re.escape(candidate)}\}}",
                    rf"\\input{{{snippet_path}}}",
                    latex,
                )
        if isinstance(filename, str) and filename:
            latex = re.sub(
                rf"\\includegraphics(?:\[[^\]]*\])?\{{[^}}]*{re.escape(filename)}\}}",
                rf"\\input{{{snippet_path}}}",
                latex,
            )
            for candidate in [filename, f"build/plot-assets/{filename}", f"./build/plot-assets/{filename}"]:
                latex = latex.replace(candidate, snippet_path)
        figure_id = asset.get("figure_id")
        if isinstance(figure_id, str) and figure_id:
            latex = re.sub(
                rf"\\includegraphics(?:\[[^\]]*\])?\{{[^}}]*{re.escape(figure_id)}\.(?:pdf|png|svg|jpg|jpeg)\}}",
                rf"\\input{{{snippet_path}}}",
                latex,
            )

    def _rewrite_figure_block(match: re.Match[str]) -> str:
        env = match.group(1)
        placement = match.group(2) or ""
        body = match.group(3)
        label_match = LABEL_RE.search(body)
        if not label_match:
            return match.group(0)
        asset = asset_by_label.get(_normalize_figure_token(label_match.group(1)))
        if not asset:
            return match.group(0)
        snippet_path = asset.get("latex_snippet_path") or asset.get("latex_path")
        if not isinstance(snippet_path, str) or not snippet_path:
            return match.group(0)
        include = (
            f"\\input{{{snippet_path}}}"
            if snippet_path.endswith(".tex")
            else f"\\includegraphics[width=0.85\\linewidth]{{{snippet_path}}}"
        )
        replaced = re.sub(r"\\includegraphics(?:\[[^\]]*\])?\{[^}]+\}", lambda _: include, body, count=1)
        if replaced == body:
            replaced = re.sub(r"\\input\{[^}]+\}", lambda _: include, body, count=1)
        if replaced == body:
            return match.group(0)
        placement_suffix = f"[{placement}]" if placement else ""
        return f"\\begin{{{env}}}{placement_suffix}{replaced}\\end{{{env}}}"

    return FIGURE_ENV_RE.sub(_rewrite_figure_block, latex)


def _normalize_source_figure_paths(latex: str, figures_dir: str | None) -> str:
    if not figures_dir:
        return latex
    path = Path(figures_dir)
    if not path.exists():
        return latex
    for figure_path in sorted(path.iterdir()):
        if not figure_path.is_file():
            continue
        name = figure_path.name
        normalized = f"inputs/figures/{name}"
        for prefix in ["figures", "figs"]:
            latex = re.sub(rf"(?<!inputs/){re.escape(prefix)}/{re.escape(name)}", normalized, latex)
            latex = re.sub(rf"(?<!inputs\\){re.escape(prefix)}\\{re.escape(name)}", normalized, latex)
        latex = re.sub(
            rf"(\\includegraphics(?:\[[^\]]*\])?\{{)(?![^}}]*inputs/figures/){re.escape(name)}(\}})",
            rf"\1{normalized}\2",
            latex,
        )
    return latex.replace("inputs/inputs/figures/", "inputs/figures/")


def _stabilize_figure_float_placement(latex: str) -> str:
    """Avoid top-only figure floats that LaTeX can defer to the manuscript tail."""

    def replace(match: re.Match[str]) -> str:
        env = match.group(1)
        placement = match.group(2)
        if placement is not None:
            normalized = placement.replace(" ", "")
            placement_flags = set(normalized.lower())
            if placement_flags & {"h", "b", "p"} or "H" in normalized:
                return match.group(0)
        stable = "!tbp" if env == "figure*" else "!htbp"
        return f"\\begin{{{env}}}[{stable}]"

    return re.sub(r"\\begin\{(figure\*?)\}(?:\[([^\]]*)\])?", replace, latex)
