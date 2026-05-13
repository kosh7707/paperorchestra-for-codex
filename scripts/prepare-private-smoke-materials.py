#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from collections import Counter
from pathlib import Path


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _safe_members(zf: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members: list[zipfile.ZipInfo] = []
    for info in zf.infolist():
        if info.is_dir():
            continue
        member_path = Path(info.filename)
        if member_path.is_absolute() or ".." in member_path.parts:
            raise ValueError("unsafe_zip_member")
        members.append(info)
    return members


def prepare(source_zip: Path, output_dir: Path, *, allow_inside_repo: bool = False) -> dict[str, object]:
    repo = _repo_root()
    source_zip = source_zip.resolve()
    output_dir = output_dir.resolve()
    if _is_within(output_dir, repo) and not allow_inside_repo:
        return {
            "status": "blocked",
            "blocker": "output_inside_repo",
            "output_label": f"redacted-output:{_sha256_text(str(output_dir))[:12]}",
            "private_safe_summary": True,
        }
    output_dir.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, object]] = []
    extensions: Counter[str] = Counter()
    total_bytes = 0
    with zipfile.ZipFile(source_zip) as zf:
        for info in _safe_members(zf):
            data = zf.read(info)
            relative = Path(info.filename)
            destination = output_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            suffix = destination.suffix.lower() or "<none>"
            extensions[suffix] += 1
            total_bytes += len(data)
            rel_label_hash = _sha256_text(str(relative))
            files.append(
                {
                    "path_label": f"redacted-member:{rel_label_hash[:12]}",
                    "path_sha256": rel_label_hash,
                    "extension": suffix,
                    "bytes": len(data),
                    "sha256": _sha256_bytes(data),
                }
            )
    manifest = {
        "private_safe_summary": True,
        "source_zip_sha256": _sha256_bytes(source_zip.read_bytes()),
        "output_label": f"redacted-output:{_sha256_text(str(output_dir))[:12]}",
        "file_count": len(files),
        "total_bytes": total_bytes,
        "extensions": dict(sorted(extensions.items())),
        "files": files,
        "checklist": [
            "Keep this directory outside the public repository unless explicitly approved.",
            "Do not commit raw private material, filenames, claims, figures, or BibTeX.",
            "Use only redacted counts/hashes in public evidence.",
        ],
    }
    (output_dir / "private-smoke-manifest.redacted.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return {"status": "ok", "manifest": manifest}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare private smoke materials outside the public repo with a redacted manifest.")
    parser.add_argument("--source-zip", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--allow-inside-repo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        payload = prepare(Path(args.source_zip), Path(args.output_dir), allow_inside_repo=args.allow_inside_repo)
    except Exception as exc:
        payload = {"status": "blocked", "blocker": exc.__class__.__name__, "private_safe_summary": True}
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload.get("status") == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
