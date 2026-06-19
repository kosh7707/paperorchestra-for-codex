from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from paperorchestra.core.errors import ContractError


def validate_verify_fallback_mode(mode: str) -> None:
    if mode not in {"none", "mock"}:
        raise ContractError(f"Unsupported verify fallback mode: {mode}")


def verify_papers_with_optional_fallback(
    *,
    stage: Any,
    cwd: str | Path | None,
    outputs: dict[str, Any],
    verify_mode: str,
    verify_error_policy: str,
    verify_fallback_mode: str,
    emit: Callable[..., None],
) -> None:
    try:
        emit("verify", "started", mode=verify_mode, on_error=verify_error_policy)
        outputs["verified"] = str(stage.verify_papers(cwd, mode=verify_mode, on_error=verify_error_policy))
        emit("verify", "completed", path=outputs["verified"], mode=verify_mode)
    except ContractError as exc:
        if verify_mode == "live" and verify_fallback_mode == "mock":
            _use_mock_verification_fallback(
                stage=stage,
                cwd=cwd,
                outputs=outputs,
                verify_error_policy=verify_error_policy,
                error=exc,
                emit=emit,
            )
            return
        raise


def _use_mock_verification_fallback(
    *,
    stage: Any,
    cwd: str | Path | None,
    outputs: dict[str, Any],
    verify_error_policy: str,
    error: ContractError,
    emit: Callable[..., None],
) -> None:
    outputs["verify_live_error"] = str(error)
    emit("verify", "fallback", error=str(error), fallback_mode="mock")
    outputs["verified"] = str(stage.verify_papers(cwd, mode="mock", on_error=verify_error_policy))
    outputs["verify_fallback_used"] = "mock"
    state = stage.load_session(cwd)
    state.latest_verify_fallback_used = "mock"
    stage.save_session(cwd, state)
    emit("verify", "completed", path=outputs["verified"], mode="mock")


__all__ = ["validate_verify_fallback_mode", "verify_papers_with_optional_fallback"]
