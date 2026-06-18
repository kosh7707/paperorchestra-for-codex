from __future__ import annotations

import argparse
from collections.abc import Iterator
from contextlib import contextmanager
import os
from pathlib import Path

from paperorchestra.orchestra.omx_action_executor import OmxActionExecutor
from paperorchestra.runtime.providers import BaseProvider, get_provider


def provider_from_args(args: argparse.Namespace) -> BaseProvider:
    return get_provider(args.provider, command=args.provider_command)


@contextmanager
def strict_omx_env(enabled: bool) -> Iterator[None]:
    if not enabled:
        yield
        return
    previous = os.environ.get("PAPERO_STRICT_OMX_NATIVE")
    os.environ["PAPERO_STRICT_OMX_NATIVE"] = "1"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("PAPERO_STRICT_OMX_NATIVE", None)
        else:
            os.environ["PAPERO_STRICT_OMX_NATIVE"] = previous


def make_omx_executor(cwd: Path, *, timeout_seconds: float = 30.0) -> OmxActionExecutor:
    return OmxActionExecutor(cwd=cwd, timeout_seconds=timeout_seconds)
