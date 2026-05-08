#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from paperorchestra.fresh_smoke import validate_material_invariance


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate immutable material packet for fresh full live smoke.")
    parser.add_argument("material_root")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--expected-material-root", default="examples/fresh-smoke-materials")
    parser.add_argument("--pointer-path", default=".omx/state/current-fresh-smoke-materials-root")
    parser.add_argument("--output")
    args = parser.parse_args()
    result = validate_material_invariance(
        args.material_root,
        repo_root=args.repo_root,
        expected_material_root=args.expected_material_root,
        pointer_path=args.pointer_path,
    )
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
