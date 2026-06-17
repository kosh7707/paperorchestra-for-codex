from __future__ import annotations

from paperorchestra.runtime import environment, readiness_profiles


def _by_name(profiles: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {str(profile["name"]): profile for profile in profiles}


def test_environment_facade_reexports_readiness_profile_builder() -> None:
    assert environment._profile is readiness_profiles._profile
    assert environment.build_readiness_profiles is readiness_profiles.build_readiness_profiles


def test_readiness_profiles_report_all_ready_when_inputs_and_strict_gates_pass(monkeypatch) -> None:
    monkeypatch.setenv("PAPERO_STRICT_CONTENT_GATES", "1")

    profiles = readiness_profiles.build_readiness_profiles(
        omx_available=True,
        codex_available=True,
        omx_control_surface_ready=True,
        provider_command_configured=True,
        semantic_scholar_api_key_set=True,
        compile_environment_ready=True,
        tex_compile_opt_in=True,
        strict_omx_native=True,
    )

    names = [profile["name"] for profile in profiles]
    assert names == [
        "local_cli_ready",
        "shell_provider_ready",
        "omx_native_ready",
        "live_verification_ready",
        "compile_ready",
        "full_live_run_ready",
        "claim_safe_full_run_ready",
    ]
    assert all(profile["ready"] is True for profile in profiles)
    assert all(profile["status"] == "ok" for profile in profiles)


def test_readiness_profiles_explain_missing_inputs_and_claim_safe_strictness(monkeypatch) -> None:
    monkeypatch.delenv("PAPERO_STRICT_CONTENT_GATES", raising=False)

    profiles = _by_name(
        readiness_profiles.build_readiness_profiles(
            omx_available=False,
            codex_available=False,
            provider_command_configured=False,
            semantic_scholar_api_key_set=False,
            compile_environment_ready=False,
            tex_compile_opt_in=False,
            strict_omx_native=False,
        )
    )

    assert profiles["local_cli_ready"]["ready"] is True
    assert profiles["shell_provider_ready"]["missing"] == ["Set PAPERO_MODEL_CMD for shell-provider runs."]
    assert profiles["omx_native_ready"]["missing"] == [
        "Install `omx` and ensure it is on PATH.",
        "Install `codex` and ensure it is on PATH.",
    ]
    assert profiles["live_verification_ready"]["missing"] == [
        "Set SEMANTIC_SCHOLAR_API_KEY for authenticated Semantic Scholar traffic."
    ]
    assert profiles["compile_ready"]["missing"] == [
        "Install a supported LaTeX engine and sandbox tool, or run the compile bootstrap guidance.",
        "Set PAPERO_ALLOW_TEX_COMPILE=1 before running compile commands.",
    ]
    assert profiles["full_live_run_ready"]["missing"] == [
        "Shell-provider command not configured.",
        "OMX/Codex toolchain not fully installed.",
        "Semantic Scholar API key missing.",
        "Compile environment is not fully ready.",
    ]
    assert profiles["claim_safe_full_run_ready"]["missing"][-2:] == [
        "Enable strict OMX-native mode for claim-safe runs.",
        "Enable strict content gates for claim-safe runs.",
    ]


def test_readiness_profiles_include_omx_control_surface_probe_failure() -> None:
    profiles = _by_name(
        readiness_profiles.build_readiness_profiles(
            omx_available=True,
            codex_available=True,
            omx_control_surface_ready=False,
            omx_control_surface_missing=["omx state probe failed"],
            omx_control_surface_next_steps=["omx doctor --deep"],
            provider_command_configured=True,
            semantic_scholar_api_key_set=True,
            compile_environment_ready=True,
            tex_compile_opt_in=True,
            strict_omx_native=True,
        )
    )

    assert profiles["omx_native_ready"]["ready"] is False
    assert profiles["omx_native_ready"]["missing"] == ["omx state probe failed"]
    assert profiles["omx_native_ready"]["next_steps"] == ["omx doctor --deep"]
    assert "OMX control surface probe did not pass." in profiles["full_live_run_ready"]["missing"]
