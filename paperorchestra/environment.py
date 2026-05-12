from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = Path(__file__).resolve().parent


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
        default="gpt-5.5",
        example="gpt-5.5",
        description="Override the default OMX-native model used by PaperOrchestra stages.",
        notes=("Optional quality/cost knob.",),
    ),
    EnvironmentVariableSpec(
        name="PAPERO_OMX_REASONING_EFFORT",
        category="core_runtime",
        operator_settable=True,
        default="low",
        example="xhigh",
        description="Override OMX-native reasoning effort for slower/higher-quality live runs.",
        notes=("Optional quality/cost knob.",),
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
        example='["codex","exec","--skip-git-repo-check","-m","gpt-5.5","-c","model_reasoning_effort=\\"low\\""]',
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
        name="PAPERO_CODEX_RETRY_ATTEMPTS",
        category="live_smoke",
        operator_settable=True,
        default="1",
        example="1",
        description="Fresh full live smoke wrapper retry count for direct Codex calls and wrapper-owned provider calls; this is the only replay layer enabled by that script.",
        notes=("fresh-full-live-smoke-loop.sh forces provider/OMX replay off to avoid nested attempts.",),
    ),
    EnvironmentVariableSpec(
        name="PAPERO_CODEX_RETRY_BACKOFF_SECONDS",
        category="live_smoke",
        operator_settable=True,
        default="15",
        example="15",
        description="Backoff between retryable Codex transport attempts owned by the fresh full live smoke wrapper.",
    ),
    EnvironmentVariableSpec(
        name="PAPERO_CODEX_RETRY_JITTER_SECONDS",
        category="live_smoke",
        operator_settable=True,
        default="0",
        example="3",
        description="Optional random jitter added to fresh full live smoke Codex retry backoff.",
    ),
    EnvironmentVariableSpec(
        name="PAPERO_SMOKE_STEP_RETRY_ATTEMPTS",
        category="live_smoke",
        operator_settable=True,
        default="1",
        example="1",
        description="Bounded fresh full live smoke replay count for selected provider-backed stages after retryable transport evidence in the stage log or matching provider trace.",
        notes=("Does not replay validators, material checks, compile, meta leakage, or quality gates.",),
    ),
    EnvironmentVariableSpec(
        name="PAPERO_SMOKE_STEP_RETRY_BACKOFF_SECONDS",
        category="live_smoke",
        operator_settable=True,
        default="15",
        example="15",
        description="Backoff between fresh full live smoke provider-backed stage replays.",
    ),
    EnvironmentVariableSpec(
        name="PAPERO_SMOKE_STEP_RETRY_JITTER_SECONDS",
        category="live_smoke",
        operator_settable=True,
        default="0",
        example="3",
        description="Optional random jitter added to fresh full live smoke provider-backed stage replay backoff.",
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
        description="Force search-grounded discovery mode (`live` or `mock`) for literature runs and smoke scripts.",
        notes=("Optional; defaults are set by CLI flags or scripts.",),
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
        notes=("Advanced compile knob; usually auto-configured by `paperorchestra check-compile-env`.",),
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
    EnvironmentVariableSpec(
        name="PAPERO_SMOKE_LIVE",
        category="reference_smoke",
        operator_settable=True,
        default="0",
        example="1",
        description="Enable the live reference smoke path instead of the safe mock path.",
        notes=("Used by scripts/smoke-paperorchestra-reference.sh.",),
    ),
    EnvironmentVariableSpec(
        name="PAPERO_SMOKE_COMPILE",
        category="reference_smoke",
        operator_settable=True,
        default="0",
        example="1",
        description="Ask the reference smoke script to compile the generated paper.",
        notes=("Used by scripts/smoke-paperorchestra-reference.sh.",),
    ),
    EnvironmentVariableSpec(
        name="PAPERO_SMOKE_WORKDIR",
        category="reference_smoke",
        operator_settable=True,
        default="mktemp dir",
        example="/tmp/paperorchestra-reference-smoke",
        description="Override the workdir used by the reference smoke scripts.",
    ),
    EnvironmentVariableSpec(
        name="PAPERO_SMOKE_KEEP_WORKDIR",
        category="reference_smoke",
        operator_settable=True,
        default="1",
        example="0",
        description="Keep or delete the smoke workdir after completion.",
    ),
    EnvironmentVariableSpec(
        name="PAPERO_SMOKE_PROVIDER",
        category="reference_smoke",
        operator_settable=True,
        default="script-dependent",
        example="shell",
        description="Override the provider used by smoke scripts.",
    ),
    EnvironmentVariableSpec(
        name="PAPERO_SMOKE_RUNTIME_MODE",
        category="reference_smoke",
        operator_settable=True,
        default="script-dependent",
        example="omx_native",
        description="Override the runtime mode used by smoke scripts.",
    ),
    EnvironmentVariableSpec(
        name="PAPERO_SMOKE_DISCOVERY_MODE",
        category="reference_smoke",
        operator_settable=True,
        default="script-dependent",
        example="search-grounded",
        description="Override the discovery mode used by smoke scripts.",
    ),
    EnvironmentVariableSpec(
        name="PAPERO_SMOKE_RESEARCH_MODE",
        category="reference_smoke",
        operator_settable=True,
        default="mock",
        example="live",
        description="Override research mode in `scripts/smoke-omx-native.sh`.",
    ),
    EnvironmentVariableSpec(
        name="PAPERO_SMOKE_VERIFY_MODE",
        category="reference_smoke",
        operator_settable=True,
        default="mock",
        example="live",
        description="Override verification mode in `scripts/smoke-omx-native.sh`.",
    ),
    EnvironmentVariableSpec(
        name="PAPERO_SMOKE_REFINE_ITERATIONS",
        category="reference_smoke",
        operator_settable=True,
        default="script-dependent",
        example="1",
        description="Override refinement iterations in smoke scripts.",
    ),
    EnvironmentVariableSpec(
        name="PAPERO_SMOKE_TIMEOUT_SECONDS",
        category="reference_smoke",
        operator_settable=True,
        default="900",
        example="1200",
        description="Overall timeout for `scripts/smoke-omx-native.sh`.",
    ),
    EnvironmentVariableSpec(
        name="PAPERO_SMOKE_PROVIDER_TIMEOUT_SECONDS",
        category="reference_smoke",
        operator_settable=True,
        default="600 or 240 depending on script",
        example="900",
        description="Shell-provider timeout used by smoke scripts.",
    ),
    EnvironmentVariableSpec(
        name="PAPERO_SMOKE_OMX_EXEC_TIMEOUT_SECONDS",
        category="reference_smoke",
        operator_settable=True,
        default="600 or 300 depending on script",
        example="900",
        description="OMX exec timeout used by smoke scripts.",
    ),
    EnvironmentVariableSpec(
        name="PAPERO_SMOKE_POLL_INTERVAL_SECONDS",
        category="reference_smoke",
        operator_settable=True,
        default="5",
        example="2",
        description="Polling interval for the OMX-native smoke script.",
    ),
    EnvironmentVariableSpec(
        name="PAPERO_SMOKE_SEED_ANSWERS_FILE",
        category="reference_smoke",
        operator_settable=True,
        default="unset",
        example="/path/to/seed_answers.json",
        description="Seed answers injected into the OMX-native smoke script.",
    ),
    EnvironmentVariableSpec(
        name="PAPERO_SMOKE_RESULTS_MARKDOWN_FILE",
        category="reference_smoke",
        operator_settable=True,
        default="unset",
        example="/path/to/results.md",
        description="Results markdown injected into the OMX-native smoke script.",
    ),
    EnvironmentVariableSpec(
        name="PAPERO_SMOKE_REFERENCE_BENCHMARK_CASE",
        category="reference_smoke",
        operator_settable=True,
        default="unset",
        example="/path/to/benchmark_case.json",
        description="Reference benchmark artifact injected into the OMX-native smoke script.",
    ),
    EnvironmentVariableSpec(
        name="PAPERO_REFERENCE_PDF",
        category="reference_smoke",
        operator_settable=True,
        default="unset",
        example="/path/to/reference.pdf",
        description="Path to the PaperOrchestra reference PDF used by the reference smoke script.",
    ),
    EnvironmentVariableSpec(
        name="PAPERO_TESTSET_SMOKE_WORKDIR",
        category="testset_smoke",
        operator_settable=True,
        default="mktemp dir",
        example="/tmp/paperorchestra-testset-smoke",
        description="Override the testset smoke workdir.",
    ),
    EnvironmentVariableSpec(
        name="PAPERO_TESTSET_SMOKE_KEEP_WORKDIR",
        category="testset_smoke",
        operator_settable=True,
        default="1",
        example="0",
        description="Keep or delete the testset smoke workdir after completion.",
    ),
    EnvironmentVariableSpec(
        name="PAPERO_TESTSET_SMOKE_PROVIDER",
        category="testset_smoke",
        operator_settable=True,
        default="mock",
        example="shell",
        description="Provider for the testset smoke script.",
    ),
    EnvironmentVariableSpec(
        name="PAPERO_TESTSET_SMOKE_PROVIDER_COMMAND",
        category="testset_smoke",
        operator_settable=True,
        default="unset",
        example='["codex","exec","--skip-git-repo-check"]',
        description="Explicit provider command for the testset smoke script.",
    ),
    EnvironmentVariableSpec(
        name="PAPERO_TESTSET_SMOKE_RUNTIME_MODE",
        category="testset_smoke",
        operator_settable=True,
        default="compatibility",
        example="omx_native",
        description="Runtime mode for the testset smoke script.",
    ),
    EnvironmentVariableSpec(
        name="PAPERO_TESTSET_SMOKE_REFINE_ITERATIONS",
        category="testset_smoke",
        operator_settable=True,
        default="1",
        example="2",
        description="Refinement iterations for the testset smoke script.",
    ),
    EnvironmentVariableSpec(
        name="PAPERO_TESTSET_SMOKE_COMPILE",
        category="testset_smoke",
        operator_settable=True,
        default="1",
        example="0",
        description="Compile toggle for the testset smoke script.",
    ),
    EnvironmentVariableSpec(
        name="PAPERO_TESTSET_SMOKE_STRICT_OMX_NATIVE",
        category="testset_smoke",
        operator_settable=True,
        default="0",
        example="1",
        description="Strict OMX-native toggle for the testset smoke script.",
    ),
    EnvironmentVariableSpec(
        name="PAPERO_TESTSET_SMOKE_SKIP_RESEARCH_PRIOR_WORK",
        category="testset_smoke",
        operator_settable=True,
        default="0",
        example="1",
        description="Skip the generated prior-work seed stage during the testset smoke run.",
    ),
    EnvironmentVariableSpec(
        name="PAPERO_TESTSET_SMOKE_PROVIDER_TIMEOUT_SECONDS",
        category="testset_smoke",
        operator_settable=True,
        default="900",
        example="1200",
        description="Provider timeout for the testset smoke script.",
    ),
    EnvironmentVariableSpec(
        name="PAPERO_TESTSET_SMOKE_OMX_EXEC_TIMEOUT_SECONDS",
        category="testset_smoke",
        operator_settable=True,
        default="900",
        example="1200",
        description="OMX exec timeout for the testset smoke script.",
    ),
    EnvironmentVariableSpec(
        name="PAPERO_TESTSET_SMOKE_OMX_CONTROL_TIMEOUT_SECONDS",
        category="testset_smoke",
        operator_settable=True,
        default="120",
        example="180",
        description="OMX control timeout for the testset smoke script.",
    ),
)


CATEGORY_LABELS = {
    "core_runtime": "Common runtime knobs",
    "shell_provider": "Shell provider",
    "verification": "Search / verification",
    "compile": "Compile",
    "reference_smoke": "Reference smoke scripts",
    "testset_smoke": "Testset smoke script",
}


def environment_guide_path() -> Path:
    return PROJECT_ROOT / "ENVIRONMENT.md"


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
                    "paperorchestra check-compile-env",
                    "paperorchestra bootstrap-compile-env",
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


def _profile(name: str, description: str, ready: bool, missing: list[str], next_steps: list[str]) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "ready": ready,
        "status": "ok" if ready else "warning",
        "missing": missing,
        "next_steps": next_steps,
    }


def build_readiness_profiles(
    *,
    omx_available: bool,
    codex_available: bool,
    omx_control_surface_ready: bool = True,
    omx_control_surface_missing: list[str] | None = None,
    omx_control_surface_next_steps: list[str] | None = None,
    provider_command_configured: bool,
    semantic_scholar_api_key_set: bool,
    compile_environment_ready: bool,
    tex_compile_opt_in: bool,
    strict_omx_native: bool,
) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    strict_content_gates = os.environ.get("PAPERO_STRICT_CONTENT_GATES", "").strip().lower() in {"1", "true", "yes", "on"}

    profiles.append(
        _profile(
            "demo_ready",
            "Safe local mock/compatibility runs and most docs/CLI surfaces.",
            True,
            [],
            [
                "paperorchestra quickstart --scenario environment",
                "paperorchestra run --provider mock --verify-mode mock --runtime-mode compatibility",
            ],
        )
    )

    shell_missing: list[str] = []
    shell_steps: list[str] = []
    if not provider_command_configured:
        shell_missing.append("Set PAPERO_MODEL_CMD for shell-provider runs.")
        shell_steps.append("Use the README copyable environment template and set PAPERO_MODEL_CMD to your Codex/OpenAI/Ollama command.")
    profiles.append(
        _profile(
            "shell_provider_ready",
            "CLI runs that use `--provider shell` instead of the mock provider.",
            provider_command_configured,
            shell_missing,
            shell_steps or ["paperorchestra run --provider shell --verify-mode mock --runtime-mode compatibility"],
        )
    )

    omx_missing: list[str] = []
    omx_steps: list[str] = []
    omx_control_surface_missing = omx_control_surface_missing or []
    omx_control_surface_next_steps = omx_control_surface_next_steps or []
    if not omx_available:
        omx_missing.append("Install `omx` and ensure it is on PATH.")
        omx_steps.append("omx doctor")
    if not codex_available:
        omx_missing.append("Install `codex` and ensure it is on PATH.")
        omx_steps.append("codex --help")
    if omx_available and codex_available and not omx_control_surface_ready:
        omx_missing.extend(omx_control_surface_missing or ["OMX control surface probe did not pass."])
        omx_steps.extend(omx_control_surface_next_steps)
    omx_ready = omx_available and codex_available and omx_control_surface_ready
    profiles.append(
        _profile(
            "omx_native_ready",
            "Live OMX-native stage execution (`--runtime-mode omx_native`).",
            omx_ready,
            omx_missing,
            omx_steps or ["paperorchestra run --provider shell --runtime-mode omx_native --verify-mode mock"],
        )
    )

    verify_missing: list[str] = []
    verify_steps: list[str] = []
    if not semantic_scholar_api_key_set:
        verify_missing.append("Set SEMANTIC_SCHOLAR_API_KEY for authenticated Semantic Scholar traffic.")
        verify_steps.append("export SEMANTIC_SCHOLAR_API_KEY='<your-key>'")
    profiles.append(
        _profile(
            "live_verification_ready",
            "Live literature verification and search-grounded discovery with less rate-limit risk.",
            semantic_scholar_api_key_set,
            verify_missing,
            verify_steps or ["paperorchestra verify-papers --mode live"],
        )
    )

    compile_missing: list[str] = []
    compile_steps: list[str] = []
    if not compile_environment_ready:
        compile_missing.append("Install a supported LaTeX engine and sandbox tool, or run the compile bootstrap guidance.")
        compile_steps.extend(["paperorchestra check-compile-env", "paperorchestra bootstrap-compile-env"])
    if not tex_compile_opt_in:
        compile_missing.append("Set PAPERO_ALLOW_TEX_COMPILE=1 before running compile commands.")
        compile_steps.append("export PAPERO_ALLOW_TEX_COMPILE=1")
    profiles.append(
        _profile(
            "compile_ready",
            "Paper compilation with the guarded TeX toolchain.",
            compile_environment_ready and tex_compile_opt_in,
            compile_missing,
            compile_steps or ["paperorchestra compile"],
        )
    )

    full_missing: list[str] = []
    full_steps: list[str] = []
    if not provider_command_configured:
        full_missing.append("Shell-provider command not configured.")
    if not omx_ready:
        if not omx_available or not codex_available:
            full_missing.append("OMX/Codex toolchain not fully installed.")
        else:
            full_missing.append("OMX control surface probe did not pass.")
    if not semantic_scholar_api_key_set:
        full_missing.append("Semantic Scholar API key missing.")
    if not (compile_environment_ready and tex_compile_opt_in):
        full_missing.append("Compile environment is not fully ready.")
    if full_missing:
        full_steps.extend([
            "paperorchestra environment",
            "paperorchestra doctor",
            "paperorchestra audit-reproducibility",
        ])
    profiles.append(
        _profile(
            "full_live_run_ready",
            "Live shell-provider + OMX-native + live verification + compile runs.",
            provider_command_configured and omx_ready and semantic_scholar_api_key_set and compile_environment_ready and tex_compile_opt_in,
            full_missing,
            full_steps or ["paperorchestra run --provider shell --runtime-mode omx_native --verify-mode live --compile"],
        )
    )

    claim_missing = list(full_missing)
    claim_steps = list(full_steps)
    if not strict_omx_native:
        claim_missing.append("Enable strict OMX-native mode for claim-safe runs.")
        claim_steps.append("export PAPERO_STRICT_OMX_NATIVE=1")
    if not strict_content_gates:
        claim_missing.append("Enable strict content gates for claim-safe runs.")
        claim_steps.append("export PAPERO_STRICT_CONTENT_GATES=1")
    profiles.append(
        _profile(
            "claim_safe_full_run_ready",
            "The stricter posture for reproducibility/fidelity claims: full live run plus strict OMX-native no-fallback policy.",
            provider_command_configured
            and omx_ready
            and semantic_scholar_api_key_set
            and compile_environment_ready
            and tex_compile_opt_in
            and strict_omx_native
            and strict_content_gates,
            claim_missing,
            claim_steps or ["paperorchestra audit-reproducibility"],
        )
    )

    return profiles
