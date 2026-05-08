#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from paperorchestra.fresh_smoke import validate_evidence_completeness


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate fresh full live smoke evidence bundle completeness and consistency.")
    parser.add_argument("evidence_root")
    parser.add_argument("--output")
    args = parser.parse_args()
    result = validate_evidence_completeness(args.evidence_root)
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
