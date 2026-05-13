#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _read_denylist(path: Path) -> list[str]:
    tokens: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        tokens.append(stripped)
    return tokens


def _tracked_paths(root: Path) -> list[Path]:
    proc = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        return []
    return [root / item.decode("utf-8") for item in proc.stdout.split(b"\0") if item]


def _iter_paths(root: Path, explicit_paths: list[str] | None) -> tuple[str, list[Path]]:
    if explicit_paths:
        return "explicit_paths", [Path(item).resolve() for item in explicit_paths]
    return "tracked_files", _tracked_paths(root)


def scan_paths(paths: Iterable[Path], tokens: list[str]) -> list[dict[str, str]]:
    matches: list[dict[str, str]] = []
    for path in paths:
        path_text = str(path)
        path_hash = _sha256_text(path_text)
        try:
            content = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
        except OSError:
            content = ""
        for index, token in enumerate(tokens, start=1):
            sources = []
            if token in path_text:
                sources.append("path")
            if token and token in content:
                sources.append("content")
            if not sources:
                continue
            matches.append(
                {
                    "path_label": f"redacted-path:{path_hash[:12]}",
                    "path_sha256": path_hash,
                    "token_label": f"denylist-token-{index}",
                    "token_sha256": _sha256_text(token),
                    "match_sources": ",".join(sorted(sources)),
                }
            )
    return matches


def build_report(*, root: Path, denylist: Path, explicit_paths: list[str] | None) -> dict[str, object]:
    tokens = _read_denylist(denylist)
    scan_mode, paths = _iter_paths(root, explicit_paths)
    matches = scan_paths(paths, tokens)
    return {
        "status": "blocked" if matches else "ok",
        "scan_mode": scan_mode,
        "root_label": f"redacted-root:{_sha256_text(str(root.resolve()))[:12]}",
        "denylist_token_count": len(tokens),
        "scanned_file_count": len(paths),
        "match_count": len(matches),
        "matches": matches,
        "private_safe_summary": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan tracked/public files for locally supplied private denylist tokens.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--denylist", default=os.environ.get("PAPERO_PRIVATE_DENYLIST"))
    parser.add_argument("--paths", nargs="*")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if not args.denylist:
        report = {"status": "blocked", "blocker": "missing_denylist", "private_safe_summary": True}
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 2
    denylist = Path(args.denylist).resolve()
    if not denylist.exists():
        report = {"status": "blocked", "blocker": "denylist_not_found", "private_safe_summary": True}
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 2
    report = build_report(root=Path(args.root).resolve(), denylist=denylist, explicit_paths=args.paths)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 2 if report["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
