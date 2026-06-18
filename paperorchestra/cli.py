from __future__ import annotations

import sys
from pathlib import Path

from paperorchestra.interfaces.cli_parser import build_parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        from paperorchestra.interfaces.cli_handlers import handle_cli_command

        return handle_cli_command(args, cwd=Path.cwd(), parser=parser)
    except Exception as exc:  # pragma: no cover - CLI boundary
        print(f"error: {exc}", file=sys.stderr)
        if getattr(args, "strict_omx_native", False) and "Strict OMX-native mode forbids fallback" in str(exc):
            return 2
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
