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
from pathlib import Path
from typing import Pattern

SECRET_PATTERNS: dict[str, Pattern[str]] = {
    "s2_key": re.compile(r"s2k-[A-Za-z0-9]+"),
    "openai_key": re.compile(r"sk-(proj|live|test|svcacct)-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9]{32,}"),
    "bearer_token": re.compile(r"Bearer\s+[A-Za-z0-9._-]{20,}", re.I),
    "assigned_api_key": re.compile(r"""(?i)\b(?:api[_-]?key|token|secret)\b\s*[:=]\s*["']?[A-Za-z0-9_-]{16,}"""),
}

PRIVATE_MARKER = "paperorchestra-" + "private"
DOMAIN_MARKER = "c" + "ci"
N_MARKER = "non" + "ce"
AEAD_PATTERN = "|".join(
    [
        "AES" + "-?GCM",
        "SU" + "PERCOP",
        "IND" + "-CPA",
        "INT" + "-CTXT",
        "secret-" + N_MARKER,
        "hidden-" + N_MARKER,
    ]
)
RESIDUE_PATTERNS: dict[str, Pattern[str]] = {
    "private_artifact_path": re.compile(PRIVATE_MARKER, re.I),
    "domain_specific_token": re.compile(r"\b" + re.escape(DOMAIN_MARKER) + r"\b", re.I),
    "domain_nonce_token": re.compile(r"\b" + re.escape(N_MARKER) + r"\b", re.I),
    "aead_baseline": re.compile(AEAD_PATTERN, re.I),
}


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def scan_tree(root: Path, *, allow_private_residue: bool = False) -> dict[str, object]:
    findings: list[dict[str, object]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name in {".counter"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        rel = str(path.relative_to(root))
        for family, patterns in (("secret", SECRET_PATTERNS), ("private_or_domain_residue", RESIDUE_PATTERNS)):
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
    args = parser.parse_args()
    payload = scan_tree(Path(args.scan_root), allow_private_residue=args.allow_private_residue)
    out = Path(args.output)
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
