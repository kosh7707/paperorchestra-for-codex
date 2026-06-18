from __future__ import annotations

from paperorchestra.runtime.environment_spec import EnvironmentVariableSpec


COMPILE_VARIABLES: tuple[EnvironmentVariableSpec, ...] = (
    EnvironmentVariableSpec(
        name='PAPERO_ALLOW_TEX_COMPILE',
        category='compile',
        operator_settable=True,
        default='0',
        example='1',
        description='Required opt-in before any TeX compilation can run.',
        required_for=('compile_ready', 'full_live_run_ready', 'claim_safe_full_run_ready'),
        notes=(),
    ),
    EnvironmentVariableSpec(
        name='PAPERO_TEX_SANDBOX_CMD',
        category='compile',
        operator_settable=True,
        default='auto-configured when a supported sandbox exists',
        example='["/path/to/tex-sandbox.sh"]',
        description='Override the sandbox wrapper used for LaTeX compilation.',
        required_for=(),
        notes=('Advanced compile knob; usually auto-configured by `paperorchestra environment --summary`.',),
    ),
    EnvironmentVariableSpec(
        name='TEXINPUTS',
        category='compile',
        operator_settable=True,
        default='unset',
        example='/path/to/custom/texmf:',
        description='Additional TeX search paths for custom classes/styles when compiling manuscripts.',
        required_for=(),
        notes=('Advanced compile knob for venue-specific assets.',),
    ),
)

__all__ = ["COMPILE_VARIABLES"]
