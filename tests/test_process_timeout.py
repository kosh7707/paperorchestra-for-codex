from __future__ import annotations

import sys

from paperorchestra.runtime.process_timeout import run_with_soft_timeout


def test_run_with_soft_timeout_captures_successful_process_output(tmp_path) -> None:
    proc, timed_out = run_with_soft_timeout(
        [sys.executable, "-c", "print('ok')"],
        cwd=tmp_path,
        timeout_seconds=5,
        grace_seconds=0,
    )

    assert timed_out is False
    assert proc.returncode == 0
    assert proc.stdout.strip() == "ok"


def test_run_with_soft_timeout_kills_after_timeout_without_grace(tmp_path) -> None:
    proc, timed_out = run_with_soft_timeout(
        [sys.executable, "-c", "import time; time.sleep(1)"],
        cwd=tmp_path,
        timeout_seconds=0.05,
        grace_seconds=0,
    )

    assert timed_out is True
    assert proc.returncode != 0
