from __future__ import annotations

import argparse


def add_common_provider_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--provider", default="shell", choices=["shell", "mock"])
    parser.add_argument("--provider-command", default=None)


def add_citation_provider_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--citation-provider", default=None, choices=["shell", "mock"])
    parser.add_argument("--citation-provider-command", default=None)


def add_runtime_mode_args(parser: argparse.ArgumentParser, *, strict_flag: bool = False) -> None:
    parser.add_argument("--runtime-mode", default="compatibility", choices=["compatibility", "omx_native"])
    if strict_flag:
        parser.add_argument("--strict-omx-native", action="store_true")
