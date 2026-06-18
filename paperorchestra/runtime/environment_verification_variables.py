from __future__ import annotations

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

__all__ = ["VERIFICATION_VARIABLES"]
