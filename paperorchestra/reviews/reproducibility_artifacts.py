from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json


def _read_json_if_exists(path: str | Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists():
        return None
    try:
        payload = read_json(candidate)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _read_json_payload_if_exists(path: str | Path | None) -> Any | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists():
        return None
    try:
        return read_json(candidate)
    except Exception:
        return None


def _file_sha256(path: str | Path | None) -> str | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return None
    return hashlib.sha256(candidate.read_bytes()).hexdigest()


def _has_mock_watermark(paper_path: str | Path | None) -> bool:
    if not paper_path:
        return False
    candidate = Path(paper_path)
    if not candidate.exists():
        return False
    text = candidate.read_text(encoding='utf-8', errors='replace')
    return 'DO NOT DISTRIBUTE AS A FACTUAL DRAFT.' in text


def _lane_completed(lane_summary: dict[str, Any], *stages: str) -> bool:
    stage_map = lane_summary.get("stages")
    if not isinstance(stage_map, dict):
        return False
    return any(
        isinstance(stage_map.get(stage), dict) and stage_map[stage].get("status") == "completed"
        for stage in stages
    )


def _prompt_trace_files(path: str | Path | None) -> list[Path]:
    if not path:
        return []
    directory = Path(path)
    if not directory.exists() or not directory.is_dir():
        return []
    return sorted(p for p in directory.glob('*.md') if p.is_file())


def _note_occurrence_count(notes: list[str], needle: str) -> int:
    return sum(1 for note in notes if needle in note)
