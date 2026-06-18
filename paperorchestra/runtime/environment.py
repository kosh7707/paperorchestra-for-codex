from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import sys
from typing import Any


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PACKAGE_ROOT.parent


@dataclass(frozen=True)
class EnvironmentVariableSpec:
    name: str
    category: str
    operator_settable: bool
    default: str | None
    example: str | None
    description: str
    required_for: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


ENVIRONMENT_VARIABLES: tuple[EnvironmentVariableSpec, ...] = (
    EnvironmentVariableSpec(
        name="PAPERO_OMX_MODEL",
        category="core_runtime",
        operator_settable=True,
        default="Codex/OMX config",
        example="your-preferred-model",
        description="Optionally pass an explicit OMX-native model for PaperOrchestra stages.",
        notes=("Unset by default so Codex/OMX can use the operator's configured model.",),
    ),
    EnvironmentVariableSpec(
        name="PAPERO_OMX_REASONING_EFFORT",
        category="core_runtime",
        operator_settable=True,
        default="Codex/OMX config",
        example="xhigh",
        description="Optionally pass an explicit OMX-native reasoning effort for live runs.",
        notes=("Unset by default so Codex/OMX can use the operator's configured effort.",),
    ),
    EnvironmentVariableSpec(
        name="PAPERO_OMX_EXEC_TIMEOUT_SECONDS",
        category="core_runtime",
        operator_settable=True,
        default="bounded in code",
        example="900",
        description="Increase OMX exec timeout for slower live stages.",
        notes=("Optional; most useful for long live runs.",),
    ),
    EnvironmentVariableSpec(
        name="PAPERO_OMX_CONTROL_TIMEOUT_SECONDS",
        category="core_runtime",
        operator_settable=True,
        default="60",
        example="120",
        description="Timeout for OMX control-plane calls such as `omx status`, `omx state`, and `omx explore`.",
        notes=("Optional; protects PaperOrchestra from hanging on stalled OMX control commands.",),
    ),
    EnvironmentVariableSpec(
        name="PAPERO_STRICT_OMX_NATIVE",
        category="core_runtime",
        operator_settable=True,
        default="0",
        example="1",
        description="Fail instead of silently falling back from OMX-native stages when a claim-safe live run matters.",
        required_for=("claim_safe_full_run_ready",),
    ),
    EnvironmentVariableSpec(
        name="PAPERO_REFINE_AXIS_TOLERANCE",
        category="core_runtime",
        operator_settable=True,
        default="0",
        example="2",
        description="Maximum allowed per-axis reviewer-score drop when refinement is otherwise non-regressive.",
        notes=("Advanced review-gate knob; lower values are stricter.",),
    ),
    EnvironmentVariableSpec(
        name="PAPERO_STRICT_CONTENT_GATES",
        category="core_runtime",
        operator_settable=True,
        default="0",
        example="1",
        description="Promote selected content warnings to reproducibility BLOCK for claim-safe/review-ready runs.",
        required_for=("claim_safe_full_run_ready",),
        notes=(
            "Currently blocks unsupported comparative claims and severe figure-placement warnings such as tail_clump.",
            "Default draft mode remains warning-oriented.",
        ),
    ),
    EnvironmentVariableSpec(
        name="PAPERO_LATEX_TIMEOUT_SEC",
        category="core_runtime",
        operator_settable=True,
        default="30",
        example="120",
        description="Timeout in seconds for each sandboxed LaTeX/BibTeX command; valid range is 1-3600.",
        notes=("Useful for larger papers or slower CI/sandboxed TeX environments.",),
    ),
    EnvironmentVariableSpec(
        name="PAPERO_DOMAIN",
        category="core_runtime",
        operator_settable=True,
        default="generic",
        example="generic",
        description="Select a registered deterministic writing/checking domain profile.",
        notes=(
            "The public package bundles only the domain-neutral generic profile.",
            "External plugins must call paperorchestra.domains.register_domain() before importing modules that cache domain fields.",
            "Unknown profile names fail closed instead of silently falling back.",
        ),
    ),
    EnvironmentVariableSpec(
        name="PAPERO_MODEL_CMD",
        category="shell_provider",
        operator_settable=True,
        default=None,
        example='["codex","--search","exec","--skip-git-repo-check"]',
        description="Shell-provider command: reads prompt from stdin and writes response to stdout.",
        required_for=("shell_provider_ready", "full_live_run_ready", "claim_safe_full_run_ready"),
    ),
    EnvironmentVariableSpec(
        name="PAPERO_PROVIDER_TIMEOUT_SECONDS",
        category="shell_provider",
        operator_settable=True,
        default="unset",
        example="600",
        description="Timeout for shell-provider model calls.",
        notes=("Optional unless your provider is slow.",),
    ),
    EnvironmentVariableSpec(
        name="PAPERO_PROVIDER_TIMEOUT_GRACE_SECONDS",
        category="shell_provider",
        operator_settable=True,
        default="0",
        example="120",
        description="Additional wait after the shell provider soft timeout before killing the process; useful when Codex reconnects and may recover without replay.",
        notes=("Set with PAPERO_PROVIDER_RETRY_ATTEMPTS for unstable Codex connections.",),
    ),
    EnvironmentVariableSpec(
        name="PAPERO_PROVIDER_RETRY_ATTEMPTS",
        category="shell_provider",
        operator_settable=True,
        default="0",
        example="2",
        description="Replay the same shell-provider prompt only after retryable transport evidence such as Codex reconnect/disconnect stderr; plain timeouts are grace-only and are not replayed.",
        notes=("Requires PAPERO_PROVIDER_RETRY_SAFE=1; keep disabled when an outer wrapper already owns retries.",),
    ),
    EnvironmentVariableSpec(
        name="PAPERO_PROVIDER_RETRY_BACKOFF_SECONDS",
        category="shell_provider",
        operator_settable=True,
        default="2",
        example="15",
        description="Sleep between retryable shell-provider prompt replays.",
    ),
    EnvironmentVariableSpec(
        name="PAPERO_PROVIDER_RETRY_JITTER_SECONDS",
        category="shell_provider",
        operator_settable=True,
        default="0",
        example="3",
        description="Optional random jitter added to provider retry backoff to avoid lockstep replays.",
    ),
    EnvironmentVariableSpec(
        name="PAPERO_PROVIDER_RETRY_SAFE",
        category="shell_provider",
        operator_settable=True,
        default="0",
        example="1",
        description="Declare that the shell-provider command is safe to replay after transport evidence; required before prompt replay is attempted.",
        notes=("Do not enable for provider commands with non-idempotent side effects.",),
    ),
    EnvironmentVariableSpec(
        name="PAPERO_PROVIDER_RETRY_TRACE_DIR",
        category="shell_provider",
        operator_settable=True,
        default="unset",
        example="review/provider-retry-traces",
        description="Optional directory where shell-provider retry/grace attempt metadata is written as JSONL.",
    ),
    EnvironmentVariableSpec(
        name="PAPERO_OMX_TIMEOUT_GRACE_SECONDS",
        category="core_runtime",
        operator_settable=True,
        default="0",
        example="120",
        description="Additional wait after OMX soft timeouts before killing the process; applies to retryable read-like control calls and grace-only OMX exec calls.",
    ),
    EnvironmentVariableSpec(
        name="PAPERO_OMX_RETRY_ATTEMPTS",
        category="core_runtime",
        operator_settable=True,
        default="0",
        example="1",
        description="Replay retryable read-only OMX control calls after reconnect-like transport failures; OMX exec is grace-only and is never replayed.",
    ),
    EnvironmentVariableSpec(
        name="PAPERO_OMX_RETRY_BACKOFF_SECONDS",
        category="core_runtime",
        operator_settable=True,
        default="2",
        example="15",
        description="Sleep between retryable OMX-native call replays.",
    ),
    EnvironmentVariableSpec(
        name="PAPERO_OMX_RETRY_JITTER_SECONDS",
        category="core_runtime",
        operator_settable=True,
        default="0",
        example="3",
        description="Optional random jitter added to OMX control retry backoff to avoid lockstep replays.",
    ),
    EnvironmentVariableSpec(
        name="PAPERO_PROVIDER_SEED",
        category="shell_provider",
        operator_settable=True,
        default="unset",
        example="7",
        description="Optional seed passthrough for shell-provider subprocesses; downstream commands must explicitly honor it.",
        notes=("Advanced reproducibility knob; PaperOrchestra forwards it but cannot force the model command to obey it.",),
    ),
    EnvironmentVariableSpec(
        name="PAPERO_PROVIDER_TEMPERATURE",
        category="shell_provider",
        operator_settable=True,
        default="unset",
        example="0.2",
        description="Optional temperature passthrough for shell-provider subprocesses.",
        notes=("Advanced quality/reproducibility knob; depends on downstream command support.",),
    ),
    EnvironmentVariableSpec(
        name="PAPERO_PROVIDER_MAX_OUTPUT_TOKENS",
        category="shell_provider",
        operator_settable=True,
        default="unset",
        example="4096",
        description="Optional max-output-tokens passthrough for shell-provider subprocesses.",
        notes=("Advanced safety/latency knob; depends on downstream command support.",),
    ),
    EnvironmentVariableSpec(
        name="PAPERO_ALLOWED_PROVIDER_BINARIES",
        category="shell_provider",
        operator_settable=True,
        default="codex,openai,ollama,llm,claude,gemini",
        example="codex,openai,ollama,llm,claude,gemini",
        description="Allowlist for shell-provider executables.",
        notes=("Only needed when using a custom provider executable.",),
    ),
    EnvironmentVariableSpec(
        name="SEMANTIC_SCHOLAR_API_KEY",
        category="verification",
        operator_settable=True,
        default=None,
        example="<your-key>",
        description="Improves reliability of live citation verification and search-grounded discovery.",
        required_for=("live_verification_ready", "full_live_run_ready", "claim_safe_full_run_ready"),
    ),
    EnvironmentVariableSpec(
        name="PAPERO_SEARCH_GROUNDED_MODE",
        category="verification",
        operator_settable=True,
        default="unset",
        example="live",
        description="Force search-grounded discovery mode (`live` or `mock`) for literature runs.",
        notes=("Optional; defaults are set by CLI flags.",),
    ),
    EnvironmentVariableSpec(
        name="PAPERO_ALLOW_TEX_COMPILE",
        category="compile",
        operator_settable=True,
        default="0",
        example="1",
        description="Required opt-in before any TeX compilation can run.",
        required_for=("compile_ready", "full_live_run_ready", "claim_safe_full_run_ready"),
    ),
    EnvironmentVariableSpec(
        name="PAPERO_TEX_SANDBOX_CMD",
        category="compile",
        operator_settable=True,
        default="auto-configured when a supported sandbox exists",
        example='["/path/to/tex-sandbox.sh"]',
        description="Override the sandbox wrapper used for LaTeX compilation.",
        notes=("Advanced compile knob; usually auto-configured by `paperorchestra environment --summary`.",),
    ),
    EnvironmentVariableSpec(
        name="TEXINPUTS",
        category="compile",
        operator_settable=True,
        default="unset",
        example="/path/to/custom/texmf:",
        description="Additional TeX search paths for custom classes/styles when compiling manuscripts.",
        notes=("Advanced compile knob for venue-specific assets.",),
    ),
)


CATEGORY_LABELS = {
    "core_runtime": "Common runtime knobs",
    "shell_provider": "Shell provider",
    "verification": "Search / verification",
    "compile": "Compile",
}


def environment_guide_path() -> Path:
    return PROJECT_ROOT / "README.md"


def env_example_path() -> Path:
    return PROJECT_ROOT / "README.md"


def grouped_environment_variables() -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for category, label in CATEGORY_LABELS.items():
        entries = [spec.to_dict() for spec in ENVIRONMENT_VARIABLES if spec.category == category]
        if entries:
            groups.append({"category": category, "label": label, "variables": entries})
    return groups


def operator_environment_variable_names() -> list[str]:
    return [spec.name for spec in ENVIRONMENT_VARIABLES if spec.operator_settable]


def package_context(cwd: str | Path | None = None) -> dict[str, Any]:
    """Return import/install context useful for diagnosing stale installs."""

    root = Path(cwd or ".").resolve()
    stale_warning = None
    if (root / "pyproject.toml").exists() and PROJECT_ROOT != root:
        stale_warning = (
            "The imported paperorchestra package is not from the current working "
            "tree. Activate the repo .venv or run `python -m pip install -e .` "
            "from this checkout."
        )
    return {
        "cwd": str(root),
        "project_root": str(PROJECT_ROOT),
        "package_root": str(PACKAGE_ROOT),
        "package_file": str(PACKAGE_ROOT / "__init__.py"),
        "python_executable": sys.executable,
        "stale_install_warning": stale_warning,
    }


def build_environment_inventory() -> dict[str, Any]:
    return {
        "package_context": package_context(),
        "docs": {
            "environment_guide": str(environment_guide_path()),
            "env_example": str(env_example_path()),
        },
        "python": {
            "requires_python": ">=3.11",
            "python_dependencies": [],
            "install_command": "python3 -m venv .venv && . .venv/bin/activate && python -m pip install -e .",
            "direct_pip_note": "On externally managed Python installs, use a virtual environment instead of system pip.",
        },
        "prerequisites": {
            "basic_operation": ["Python 3.11+", "venv-local editable install of this checkout"],
            "shell_provider": ["Set PAPERO_MODEL_CMD to a compatible executable (for example Codex CLI)."],
            "omx_native": ["omx", "codex"],
            "compile": {
                "latex_engines": ["latexmk", "pdflatex", "tectonic"],
                "sandbox_tools": ["bwrap", "firejail", "nsjail"],
                "inspection_commands": [
                    "paperorchestra environment --summary",
                ],
            },
        },
        "groups": grouped_environment_variables(),
        "auto_managed_env": [
            {
                "name": "BIBINPUTS",
                "description": "Set automatically during compile runs so BibTeX can find the generated bibliography.",
            },
            {
                "name": "BSTINPUTS",
                "description": "Set automatically during compile runs so BibTeX can find custom .bst files.",
            },
        ],
    }
