#!/usr/bin/env python3
"""Scan QA/release evidence for secrets and private-material residue.

Default mode is public-release strict: any secret or private/domain residue fails.
For private QA evidence, set ``PAPERO_RELEASE_SAFETY_ALLOW_PRIVATE_RESIDUE=1``
to keep secret findings blocking while recording private/domain residue as
allowed findings.  This lets long-running private-material QA preserve evidence
without pretending that raw evidence is publishable.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Pattern

SECRET_PATTERNS: dict[str, Pattern[str]] = {
    "s2_key": re.compile(r"s2k-[A-Za-z0-9]+"),
    "openai_key": re.compile(r"sk-(proj|live|test|svcacct)-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9]{32,}"),
    "bearer_token": re.compile(r"Bearer\s+[A-Za-z0-9._-]{20,}", re.I),
    "assigned_api_key": re.compile(r"""(?i)\b(?:api[_-]?key|token|secret)\b\s*[:=]\s*["']?[A-Za-z0-9_-]{16,}"""),
}

PRIVATE_MARKER = "paperorchestra-" + "private"
RESIDUE_PATTERNS: dict[str, Pattern[str]] = {
    "private_artifact_path": re.compile(PRIVATE_MARKER, re.I),
}


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _env_paths(name: str) -> list[Path]:
    raw = os.environ.get(name, "")
    if not raw.strip():
        return []
    return [Path(item) for item in raw.split(os.pathsep) if item.strip()]


def _parse_regex_literal(raw: str, *, path: Path, line_no: int) -> Pattern[str]:
    if not raw.startswith("regex:/") or not raw.endswith("/"):
        raise ValueError(f"{path}:{line_no}: regex entries must use regex:/.../ form")
    try:
        return re.compile(raw[len("regex:/") : -1], re.I)
    except re.error as exc:
        raise ValueError(f"{path}:{line_no}: invalid regex: {exc}") from exc


def load_external_residue_patterns(paths: list[Path]) -> dict[str, Pattern[str]]:
    patterns: dict[str, Pattern[str]] = {}
    counter = 0
    for path in paths:
        if not path.exists() or not path.is_file():
            raise ValueError(f"{path}: denylist file is not readable")
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise ValueError(f"{path}: denylist file is not readable: {exc}") from exc
        for line_no, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            counter += 1
            code = f"external_residue_{counter}"
            if stripped.startswith("regex:"):
                patterns[code] = _parse_regex_literal(stripped, path=path, line_no=line_no)
            else:
                patterns[code] = re.compile(re.escape(stripped), re.I)
    return patterns


def scan_tree(
    root: Path,
    *,
    allow_private_residue: bool = False,
    residue_patterns: dict[str, Pattern[str]] | None = None,
) -> dict[str, object]:
    findings: list[dict[str, object]] = []
    combined_residue_patterns = dict(RESIDUE_PATTERNS)
    combined_residue_patterns.update(residue_patterns or {})
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name in {".counter"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        rel = str(path.relative_to(root))
        for family, patterns in (("secret", SECRET_PATTERNS), ("private_or_domain_residue", combined_residue_patterns)):
            for code, pattern in patterns.items():
                for match in pattern.finditer(text):
                    start = max(0, match.start() - 80)
                    end = min(len(text), match.end() + 80)
                    findings.append(
                        {
                            "family": family,
                            "code": code,
                            "path": rel,
                            "offset": match.start(),
                            "blocking": family == "secret" or not allow_private_residue,
                            "excerpt": text[start:end].replace("\n", "\\n"),
                        }
                    )
    blocking = [item for item in findings if item.get("blocking")]
    allowed = [item for item in findings if not item.get("blocking")]
    return {
        "schema_version": "release-safety-scan/1",
        "status": "pass" if not blocking else "fail",
        "allow_private_residue": allow_private_residue,
        "finding_count": len(findings),
        "blocking_finding_count": len(blocking),
        "allowed_private_residue_count": len(allowed),
        "external_residue_pattern_count": len(residue_patterns or {}),
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan evidence for secrets and private/domain residue.")
    parser.add_argument("scan_root")
    parser.add_argument("output")
    parser.add_argument(
        "--allow-private-residue",
        action="store_true",
        default=_env_flag("PAPERO_RELEASE_SAFETY_ALLOW_PRIVATE_RESIDUE"),
        help="Keep secret findings blocking but allow private/domain residue in private QA evidence.",
    )
    parser.add_argument(
        "--residue-denylist",
        action="append",
        default=[],
        help="External private/domain residue denylist. Lines are literal tokens or regex:/.../ entries.",
    )
    args = parser.parse_args()
    out = Path(args.output)
    residue_denylist_paths = [Path(item) for item in args.residue_denylist] + _env_paths(
        "PAPERO_RELEASE_SAFETY_RESIDUE_DENYLIST"
    )
    try:
        external_residue_patterns = load_external_residue_patterns(residue_denylist_paths)
        payload = scan_tree(
            Path(args.scan_root),
            allow_private_residue=args.allow_private_residue,
            residue_patterns=external_residue_patterns,
        )
    except ValueError as exc:
        payload = {
            "schema_version": "release-safety-scan/1",
            "status": "fail",
            "allow_private_residue": args.allow_private_residue,
            "finding_count": 0,
            "blocking_finding_count": 1,
            "allowed_private_residue_count": 0,
            "external_residue_pattern_count": 0,
            "findings": [],
            "error": "invalid residue denylist",
            "detail": str(exc),
        }
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"invalid residue denylist: {exc}", file=sys.stderr)
        return 2
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": payload["status"],
                "finding_count": payload["finding_count"],
                "blocking_finding_count": payload["blocking_finding_count"],
                "allowed_private_residue_count": payload["allowed_private_residue_count"],
                "allow_private_residue": payload["allow_private_residue"],
            },
            sort_keys=True,
        )
    )
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
