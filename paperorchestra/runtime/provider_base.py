from __future__ import annotations

import math
import os
from dataclasses import dataclass
from textwrap import dedent

from paperorchestra.runtime.transport_retry import is_retryable_transport_text


class ProviderError(RuntimeError):
    pass


class TransientProviderError(ProviderError):
    """Provider failure that may succeed after waiting or replaying the same prompt."""


def _env_float(name: str, default: float, *, minimum: float = 0.0, maximum: float | None = None) -> float:
    raw = os.environ.get(name)
    if raw in {None, ""}:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    if not math.isfinite(value) or value < minimum:
        return default
    if maximum is not None:
        return min(value, maximum)
    return value


def _env_int(name: str, default: int, *, minimum: int = 0, maximum: int | None = None) -> int:
    raw = os.environ.get(name)
    if raw in {None, ""}:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    if value < minimum:
        return default
    if maximum is not None:
        return min(value, maximum)
    return value


def is_retryable_provider_stderr(text: str) -> bool:
    return is_retryable_transport_text(text)


@dataclass
class CompletionRequest:
    system_prompt: str
    user_prompt: str
    temperature: float | None = None
    max_output_tokens: int | None = None
    seed: int | None = None

    def combined_prompt(self) -> str:
        header = dedent(
            f"""
            [SYSTEM]
            {self.system_prompt.strip()}

            [USER]
            {self.user_prompt.strip()}
            """
        ).strip()
        return header + "\n"

    def _effective_float(self, env_name: str, explicit: float | None) -> float | None:
        if explicit is not None:
            return explicit
        raw = os.environ.get(env_name)
        if raw in {None, ""}:
            return None
        try:
            value = float(raw)
        except ValueError:
            return None
        return value if math.isfinite(value) else None

    def _effective_int(self, env_name: str, explicit: int | None) -> int | None:
        if explicit is not None:
            return explicit
        raw = os.environ.get(env_name)
        if raw in {None, ""}:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    def provider_env_overrides(self) -> dict[str, str]:
        overrides: dict[str, str] = {}
        temperature = self._effective_float("PAPERO_PROVIDER_TEMPERATURE", self.temperature)
        max_output_tokens = self._effective_int("PAPERO_PROVIDER_MAX_OUTPUT_TOKENS", self.max_output_tokens)
        seed = self._effective_int("PAPERO_PROVIDER_SEED", self.seed)
        if temperature is not None:
            overrides["PAPERO_PROVIDER_TEMPERATURE"] = str(temperature)
        if max_output_tokens is not None:
            overrides["PAPERO_PROVIDER_MAX_OUTPUT_TOKENS"] = str(max_output_tokens)
        if seed is not None:
            overrides["PAPERO_PROVIDER_SEED"] = str(seed)
        return overrides

    def control_summary(self) -> dict[str, object]:
        overrides = self.provider_env_overrides()
        return {
            "seed": int(overrides["PAPERO_PROVIDER_SEED"]) if "PAPERO_PROVIDER_SEED" in overrides else None,
            "temperature": float(overrides["PAPERO_PROVIDER_TEMPERATURE"])
            if "PAPERO_PROVIDER_TEMPERATURE" in overrides
            else None,
            "max_output_tokens": int(overrides["PAPERO_PROVIDER_MAX_OUTPUT_TOKENS"])
            if "PAPERO_PROVIDER_MAX_OUTPUT_TOKENS" in overrides
            else None,
            "env_keys_forwarded": sorted(overrides.keys()),
            "passthrough_only": True,
            "deterministic_generation_guaranteed": False,
        }


class BaseProvider:
    name = "base"

    def complete(self, request: CompletionRequest) -> str:
        raise NotImplementedError

    def fork(self) -> "BaseProvider":
        return self
