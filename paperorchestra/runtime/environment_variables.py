from __future__ import annotations

from typing import Any

from paperorchestra.runtime.environment_core_variables import CORE_RUNTIME_VARIABLES
from paperorchestra.runtime.environment_shell_provider_variables import SHELL_PROVIDER_VARIABLES
from paperorchestra.runtime.environment_spec import EnvironmentVariableSpec

VERIFICATION_VARIABLES: tuple[EnvironmentVariableSpec, ...] = (
    EnvironmentVariableSpec(
        name='SEMANTIC_SCHOLAR_API_KEY',
        category='verification',
        operator_settable=True,
        default=None,
        example='<your-key>',
        description='Improves reliability of live citation verification and search-grounded discovery.',
        required_for=('live_verification_ready', 'full_live_run_ready', 'claim_safe_full_run_ready'),
        notes=(),
    ),
    EnvironmentVariableSpec(
        name='PAPERO_SEARCH_GROUNDED_MODE',
        category='verification',
        operator_settable=True,
        default='unset',
        example='live',
        description='Force search-grounded discovery mode (`live` or `mock`) for literature runs.',
        required_for=(),
        notes=('Optional; defaults are set by CLI flags.',),
    ),
)

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

ENVIRONMENT_VARIABLE_ORDER = (
    'PAPERO_OMX_MODEL',
    'PAPERO_OMX_REASONING_EFFORT',
    'PAPERO_OMX_EXEC_TIMEOUT_SECONDS',
    'PAPERO_OMX_CONTROL_TIMEOUT_SECONDS',
    'PAPERO_STRICT_OMX_NATIVE',
    'PAPERO_REFINE_AXIS_TOLERANCE',
    'PAPERO_STRICT_CONTENT_GATES',
    'PAPERO_LATEX_TIMEOUT_SEC',
    'PAPERO_DOMAIN',
    'PAPERO_MODEL_CMD',
    'PAPERO_PROVIDER_TIMEOUT_SECONDS',
    'PAPERO_PROVIDER_TIMEOUT_GRACE_SECONDS',
    'PAPERO_PROVIDER_RETRY_ATTEMPTS',
    'PAPERO_PROVIDER_RETRY_BACKOFF_SECONDS',
    'PAPERO_PROVIDER_RETRY_JITTER_SECONDS',
    'PAPERO_PROVIDER_RETRY_SAFE',
    'PAPERO_PROVIDER_RETRY_TRACE_DIR',
    'PAPERO_OMX_TIMEOUT_GRACE_SECONDS',
    'PAPERO_OMX_RETRY_ATTEMPTS',
    'PAPERO_OMX_RETRY_BACKOFF_SECONDS',
    'PAPERO_OMX_RETRY_JITTER_SECONDS',
    'PAPERO_PROVIDER_SEED',
    'PAPERO_PROVIDER_TEMPERATURE',
    'PAPERO_PROVIDER_MAX_OUTPUT_TOKENS',
    'PAPERO_ALLOWED_PROVIDER_BINARIES',
    'SEMANTIC_SCHOLAR_API_KEY',
    'PAPERO_SEARCH_GROUNDED_MODE',
    'PAPERO_ALLOW_TEX_COMPILE',
    'PAPERO_TEX_SANDBOX_CMD',
    'TEXINPUTS',
)

_VARIABLES_BY_NAME = {
    spec.name: spec
    for spec in (
        *CORE_RUNTIME_VARIABLES,
        *SHELL_PROVIDER_VARIABLES,
        *VERIFICATION_VARIABLES,
        *COMPILE_VARIABLES,
    )
}

ENVIRONMENT_VARIABLES: tuple[EnvironmentVariableSpec, ...] = tuple(
    _VARIABLES_BY_NAME[name] for name in ENVIRONMENT_VARIABLE_ORDER
)

CATEGORY_LABELS = {
    "core_runtime": "Common runtime knobs",
    "shell_provider": "Shell provider",
    "verification": "Search / verification",
    "compile": "Compile",
}


def grouped_environment_variables() -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for category, label in CATEGORY_LABELS.items():
        entries = [spec.to_dict() for spec in ENVIRONMENT_VARIABLES if spec.category == category]
        if entries:
            groups.append({"category": category, "label": label, "variables": entries})
    return groups


def operator_environment_variable_names() -> list[str]:
    return [spec.name for spec in ENVIRONMENT_VARIABLES if spec.operator_settable]


__all__ = [
    "CATEGORY_LABELS",
    "ENVIRONMENT_VARIABLE_ORDER",
    "ENVIRONMENT_VARIABLES",
    "EnvironmentVariableSpec",
    "grouped_environment_variables",
    "operator_environment_variable_names",
]
