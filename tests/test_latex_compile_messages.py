from __future__ import annotations

from paperorchestra.manuscript import latex


def test_compile_opt_in_guidance_does_not_repeat_environment_summary() -> None:
    message = latex._compile_opt_in_error_message()

    assert message.count("paperorchestra environment --summary") == 1
    assert "PAPERO_ALLOW_TEX_COMPILE=1 paperorchestra compile" in message


def test_missing_compile_environment_guidance_does_not_repeat_environment_summary(monkeypatch, tmp_path) -> None:
    class _Report:
        latex_engine = None
        sandbox_wrapper_path = None
        sandbox_tool = None

    monkeypatch.setattr(latex, "inspect_compile_environment", lambda *args, **kwargs: _Report())

    message = latex._missing_compile_environment_message(tmp_path)

    assert message.count("paperorchestra environment --summary") == 1
    assert "PAPERO_ALLOW_TEX_COMPILE=1 paperorchestra compile" in message
