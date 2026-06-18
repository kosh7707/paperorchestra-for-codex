from __future__ import annotations

import html
import json
import re

DATA_BLOCK_RE_TEMPLATE = r'<DATA_BLOCK name="{}">\n(.*?)\n</DATA_BLOCK>'


def extract_data_block(text: str, name: str) -> str | None:
    pattern = re.compile(DATA_BLOCK_RE_TEMPLATE.format(re.escape(name)), re.DOTALL)
    match = pattern.search(text)
    return html.unescape(match.group(1).strip()) if match else None


def _json_data_block(text: str, name: str) -> object | None:
    payload = extract_data_block(text, name)
    if not payload:
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


def extract_citation_keys(text: str) -> list[str]:
    checklist = _json_data_block(text, "citation_checklist")
    if isinstance(checklist, list):
        return [item for item in checklist if isinstance(item, str)]
    citation_map = _json_data_block(text, "citation_map.json")
    if isinstance(citation_map, dict):
        return [key for key in citation_map if isinstance(key, str)]
    return []


def extract_plot_ids(text: str) -> list[str]:
    manifest = _json_data_block(text, "plot_manifest.json")
    figures = manifest.get("figures", []) if isinstance(manifest, dict) else []
    return [
        figure["figure_id"]
        for figure in figures
        if isinstance(figure, dict) and isinstance(figure.get("figure_id"), str)
    ]


def extract_plot_asset_paths(text: str) -> list[str]:
    payload = _json_data_block(text, "plot_assets.json")
    assets = payload.get("assets", []) if isinstance(payload, dict) else []
    result: list[str] = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        snippet_path = asset.get("latex_snippet_path")
        latex_path = asset.get("latex_path")
        filename = asset.get("filename")
        if isinstance(snippet_path, str):
            result.append(snippet_path)
        elif isinstance(latex_path, str):
            result.append(latex_path)
        elif isinstance(filename, str):
            result.append(filename)
    return result


def extract_metric_tokens(text: str) -> list[str]:
    experimental_log = extract_data_block(text, "experimental_log.md") or extract_data_block(
        text,
        "project_experimental_log",
    )
    if not experimental_log:
        return []
    return re.findall(r"\b\d+\.\d+%?\b|\b\d+%", experimental_log)
