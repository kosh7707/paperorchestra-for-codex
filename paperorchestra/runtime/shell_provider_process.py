from __future__ import annotations

import subprocess


def run_provider_command_once(
    argv: list[str],
    prompt: bytes,
    env: dict[str, str],
    *,
    timeout_seconds: float | None,
    timeout_grace_seconds: float,
) -> tuple[int, bytes, bytes, bool]:
    timed_out = False
    with subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    ) as proc:
        try:
            stdout, stderr = proc.communicate(input=prompt, timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            if timeout_grace_seconds > 0:
                try:
                    stdout, stderr = proc.communicate(timeout=timeout_grace_seconds)
                    return proc.returncode if proc.returncode is not None else 1, stdout or b"", stderr or b"", True
                except subprocess.TimeoutExpired:
                    pass
            proc.kill()
            stdout, stderr = proc.communicate()
        except BaseException:
            proc.kill()
            proc.wait()
            raise
    return proc.returncode if proc.returncode is not None else 1, stdout or b"", stderr or b"", timed_out
