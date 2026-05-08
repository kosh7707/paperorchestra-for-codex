#!/usr/bin/env python3
"""Validate fresh-smoke Lane-A acceptance predicates against an evidence bundle."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from paperorchestra.quality_loop_history import validate_fresh_smoke_lane_a_acceptance


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence_root", help="Fresh-smoke evidence bundle root")
    parser.add_argument("--output", help="Optional JSON output path")
    args = parser.parse_args()

    result = validate_fresh_smoke_lane_a_acceptance(args.evidence_root)
    rendered = json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0 if result.get("status") == "pass" else 30


if __name__ == "__main__":
    raise SystemExit(main())
