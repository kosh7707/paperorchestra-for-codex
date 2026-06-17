from __future__ import annotations

from paperorchestra.runtime.provider_base import CompletionRequest, is_retryable_provider_stderr


def test_completion_request_combines_system_and_user_prompt() -> None:
    request = CompletionRequest(system_prompt="  system rules  ", user_prompt="  user task  ")

    assert request.combined_prompt() == "[SYSTEM]\nsystem rules\n\n[USER]\nuser task\n"


def test_completion_request_env_overrides_use_explicit_values_before_environment(monkeypatch) -> None:
    monkeypatch.setenv("PAPERO_PROVIDER_TEMPERATURE", "0.9")
    monkeypatch.setenv("PAPERO_PROVIDER_MAX_OUTPUT_TOKENS", "4096")
    monkeypatch.setenv("PAPERO_PROVIDER_SEED", "123")

    request = CompletionRequest(
        system_prompt="system",
        user_prompt="user",
        temperature=0.1,
        max_output_tokens=512,
        seed=7,
    )

    assert request.provider_env_overrides() == {
        "PAPERO_PROVIDER_TEMPERATURE": "0.1",
        "PAPERO_PROVIDER_MAX_OUTPUT_TOKENS": "512",
        "PAPERO_PROVIDER_SEED": "7",
    }
    assert request.control_summary() == {
        "seed": 7,
        "temperature": 0.1,
        "max_output_tokens": 512,
        "env_keys_forwarded": [
            "PAPERO_PROVIDER_MAX_OUTPUT_TOKENS",
            "PAPERO_PROVIDER_SEED",
            "PAPERO_PROVIDER_TEMPERATURE",
        ],
        "passthrough_only": True,
        "deterministic_generation_guaranteed": False,
    }


def test_completion_request_ignores_invalid_environment_overrides(monkeypatch) -> None:
    monkeypatch.setenv("PAPERO_PROVIDER_TEMPERATURE", "not-a-float")
    monkeypatch.setenv("PAPERO_PROVIDER_MAX_OUTPUT_TOKENS", "not-an-int")
    monkeypatch.setenv("PAPERO_PROVIDER_SEED", "not-an-int")

    request = CompletionRequest(system_prompt="system", user_prompt="user")

    assert request.provider_env_overrides() == {}


def test_retryable_provider_stderr_delegates_transport_detection() -> None:
    assert is_retryable_provider_stderr("stream disconnected before completion")
    assert not is_retryable_provider_stderr("syntax error")
