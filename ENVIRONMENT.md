# PaperOrchestra environment guide

This file is the canonical setup guide for people who just cloned the repo and want to know:

- what must be installed,
- which environment variables matter,
- which knobs are optional,
- how to tell what is still missing on the current machine.

If you only remember two commands, remember these:

```bash
paperorchestra environment --summary
paperorchestra doctor
```

- `paperorchestra environment --summary` = compact human-readable readiness and next steps
- `paperorchestra environment --json` (or `paperorchestra environment`) = the canonical inventory (docs, env vars, readiness profiles)
- `paperorchestra doctor` = what is missing on this machine right now

---

## 1. Minimal install

```bash
git clone https://github.com/kosh7707/paperorchestra-for-codex.git
cd paperorchestra-for-codex
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Prefer the `.venv` flow for fresh clones. Direct system `pip install -e .` can
be blocked by externally managed Python installs (PEP 668), and a local venv
keeps stale global `paperorchestra` commands from shadowing this checkout.

PaperOrchestra currently has **no extra Python package dependencies** beyond the standard library.

Required baseline:

- Python **3.11+**
- editable install of this repo inside a venv (`python -m pip install -e .`)

Sanity checks:

```bash
paperorchestra --help
paperorchestra --version
paperorchestra quickstart --scenario environment
paperorchestra environment --summary
paperorchestra doctor
```

---

## 2. Readiness profiles

PaperOrchestra is intentionally layered. Not every machine must be “fully live + compile + claim-safe” on day one.

### `demo_ready`
Safe local path for mock/compatibility runs.

Good for:
- `--provider mock`
- `--verify-mode mock`
- `--runtime-mode compatibility`
- reading artifacts and learning the workflow without spending model/search calls

### `shell_provider_ready`
Needed when you want real shell-provider model calls.

Usually means:
- `PAPERO_MODEL_CMD` is configured
- optional: `PAPERO_PROVIDER_TIMEOUT_SECONDS`
- optional advanced passthrough knobs: `PAPERO_PROVIDER_SEED`, `PAPERO_PROVIDER_TEMPERATURE`, `PAPERO_PROVIDER_MAX_OUTPUT_TOKENS`

### `omx_native_ready`
Needed for `--runtime-mode omx_native`.

Usually means:
- `omx` is installed and on `PATH`
- `codex` is installed and on `PATH`
- the bounded OMX control-surface probe passes
- in minimal containers, `xz-utils` is available for harness extraction
- if `bwrap` exists, it can create the namespaces required by the harness

### `live_verification_ready`
Needed when you want live literature verification and less Semantic Scholar rate-limit pain.

Usually means:
- `SEMANTIC_SCHOLAR_API_KEY` is set

### `compile_ready`
Needed for `paperorchestra compile` or any run that uses `--compile`.

Usually means:
- a supported LaTeX engine exists: `latexmk`, `pdflatex`, or `tectonic`
- a supported sandbox is installed and passes a runtime usability probe: `bwrap`, `firejail`, or `nsjail`
- `PAPERO_ALLOW_TEX_COMPILE=1`

### `full_live_run_ready`
Needed for a fully live run with shell provider + OMX-native + live verification + compile.

Usually means:
- `shell_provider_ready`
- `omx_native_ready`
- `live_verification_ready`
- `compile_ready`

### `claim_safe_full_run_ready`
The stricter posture for runs that are supposed to support reproducibility/fidelity claims.

Usually means:
- `full_live_run_ready`
- `PAPERO_STRICT_OMX_NATIVE=1`
- `PAPERO_STRICT_CONTENT_GATES=1`

Check current status any time:

```bash
paperorchestra doctor
paperorchestra audit-reproducibility
```

---

## 3. Common packages / external tools

### Always needed
- Python 3.11+

### Needed for shell-provider live runs
- whatever executable you place in `PAPERO_MODEL_CMD`
- common choice: `codex`

### Needed for OMX-native runs
- `omx`
- `codex`

### Needed for Codex CLI MCP registration
- this repo installed in a venv (`python -m pip install -e .`)
- `paperorchestra-mcp` available from that venv
- Codex CLI config path, usually `~/.codex/config.toml`

Recommended registration command:

```bash
./scripts/register-codex-mcp.sh --use-local-venv
```

Use `--dry-run` first if you want to inspect the exact TOML. The script backs up
an existing config before writing and only manages the `paperorchestra` MCP
server sections.

After registration, use the smoke script to distinguish MCP server health from
active Codex session attachment:

```bash
scripts/smoke-paperorchestra-mcp.py
```

If this passes but the current Codex chat still has no
`mcp__paperorchestra__...` tools, the server is healthy and the remaining issue
is Codex session tool injection/attachment. `codex mcp list` confirms
registration only; it does not prove that the active conversation received the
tool schema.

### Needed for compile
Supported LaTeX engines:
- `latexmk`
- `pdflatex`
- `tectonic`

Supported sandbox tools:
- `bwrap`
- `firejail`
- `nsjail`

Fastest way to inspect compile readiness:

```bash
paperorchestra check-compile-env
paperorchestra bootstrap-compile-env
```

Both commands expose the core readiness fields (`ready_for_compile`,
`latex_engine`, `sandbox_tool`, install commands/notes) at the top level for
simple scripting. `check-compile-env` also writes the report under
`.paper-orchestra/preflight/compile-environment.json` and includes that saved
copy as `report`.

On apt-based systems, the generated bootstrap guidance typically resembles:

```bash
sudo apt-get update
sudo apt-get install -y pkg-config libpng-dev texlive-latex-base texlive-latex-recommended texlive-fonts-recommended latexmk bubblewrap
```

If you are inside a root container without `sudo`, the same command is printed
without the `sudo` prefix:

```bash
apt-get update
apt-get install -y pkg-config libpng-dev texlive-latex-base texlive-latex-recommended texlive-fonts-recommended latexmk bubblewrap
```

On other package managers, use `paperorchestra bootstrap-compile-env` instead of guessing.

#### Container notes

Minimal Docker/CI containers can make `binary exists != binary usable`.
`bubblewrap` (`bwrap`) is lightweight, but it can fail at runtime when the
kernel/container policy disables unprivileged user namespaces:

```text
bwrap: No permissions to create new namespace
```

`paperorchestra check-compile-env` therefore probes sandbox tools by running a
small command through them before reporting `compile_ready`. If `bwrap` is
installed but unusable, install/configure another sandbox:

```bash
sudo apt-get install -y firejail
# or:
export PAPERO_TEX_SANDBOX_CMD='["/absolute/path/to/tex-sandbox.sh"]'
```

`firejail` can work well in locked-down containers, but it may install a larger
dependency set on Debian/Ubuntu and may print noisy systemd/resolv.conf package
messages in small images. Re-run `paperorchestra check-compile-env` after
installation and trust the runtime probe result more than package-install noise.
`nsjail` is also supported when available.

For OMX control surfaces in very small containers, `omx explore` may also need
`xz-utils` to unpack its harness archive:

```bash
apt-get install -y xz-utils        # root container
sudo apt-get install -y xz-utils   # normal sudo user
```

If `doctor` reports an `omx_control_surface_probe` warning, the `detail` and
`next_steps` fields distinguish common causes such as missing `xz-utils` and
`bwrap` namespace denial. Use compatibility mode for the mock path when OMX
native control surfaces are blocked by the container. This is a conservative
local prerequisite probe: actual `omx explore` may still work if OMX uses a
different runtime fallback, so run the suggested `omx explore` smoke when you
need to distinguish a local bwrap warning from an actual OMX runtime failure.

For a deeper but still bounded OMX check, run:

```bash
paperorchestra doctor --omx-deep
```

This probes `omx`, `codex`, `omx explore --help`, `omx ralph --help`,
`omx state list-active --json`, `omx trace summary --json`, `omx sparkshell
--help`, and team/list surfaces without requiring private credentials or a live
model run. After a QA session, preserve public-safe OMX evidence with:

```bash
paperorchestra export-omx-evidence --output ./paperorchestra-omx-evidence
```

The exporter writes state/status and sanitized trace summaries only. It does not
copy raw OMX trace timelines, prompt previews, private material, or provider
traces. For Critic/team/ultrawork review, use:

```bash
paperorchestra omx-review-handoff
```

That command writes a manual handoff artifact and intentionally does not
auto-launch long-running workers.

---

## 4. Copyable env template

The copyable commented template now lives in `README.md` under **`Copyable environment template`**.

Typical usage:

```bash
# copy the block from README.md into a local .env if you want one
set -a
source .env
set +a
```

If you use `direnv`, `mise`, or another env manager, translate the same variables there.

---

## 5. Environment variables

Below is the operator-facing inventory. Variables not listed here are either auto-managed internally or only exist as test scaffolding.

### Common runtime knobs

| Variable | Required? | Default | Why it exists |
| --- | --- | --- | --- |
| `PAPERO_OMX_MODEL` | Optional | `gpt-5.5` | Override the OMX-native model |
| `PAPERO_OMX_REASONING_EFFORT` | Optional | `low` | Trade latency/cost vs reasoning depth |
| `PAPERO_OMX_EXEC_TIMEOUT_SECONDS` | Optional | code-bounded | Give slow live runs more time |
| `PAPERO_OMX_CONTROL_TIMEOUT_SECONDS` | Optional | `60` | Bound OMX control-plane calls like `omx status` / `omx state` |
| `PAPERO_OMX_TIMEOUT_GRACE_SECONDS` | Optional | `0` | Extra wait for OMX/Codex reconnects before treating timeout as failed |
| `PAPERO_OMX_RETRY_ATTEMPTS` | Optional | `0` | Retry read-only OMX control-plane transport failures (`status`, `team status`, `state read --json`); LLM-backed `explore` and OMX exec remain grace-only and are not replayed |
| `PAPERO_OMX_RETRY_BACKOFF_SECONDS` | Optional | `2` | Backoff between retryable OMX replays |
| `PAPERO_OMX_RETRY_JITTER_SECONDS` | Optional | `0` | Optional random jitter added to OMX retry backoff |
| `PAPERO_STRICT_OMX_NATIVE` | Claim-safe only | `0` | Refuse OMX-native fallback when fidelity matters |
| `PAPERO_REFINE_AXIS_TOLERANCE` | Advanced optional | `0` | Allow bounded per-axis reviewer-score drops during refinement |
| `PAPERO_STRICT_CONTENT_GATES` | Claim-safe only | `0` | Promote unsupported comparative claims and severe figure-placement warnings to reproducibility BLOCK |
| `PAPERO_LATEX_TIMEOUT_SEC` | Optional | `30` | Timeout in seconds for each sandboxed LaTeX/BibTeX command (1-3600) |
| `PAPERO_DOMAIN` | Optional | `generic` | Select a registered deterministic writing/checking domain profile |

Quality-loop commands use explicit CLI flags rather than environment variables for loop policy: `--quality-mode draft|ralph|claim_safe`, `--max-iterations`, `--quality-eval`, `--record-history`, and `--accept-mixed-provenance`. `paperorchestra run` alone is draft generation, not a full quality gate; use `scripts/live-smoke-claim-safe.sh` for a recorded full quality-gated smoke with validate/source-obligation/compile/review/section/figure-placement/citation/quality-loop evidence. Before claim-safe `quality-eval`, run `paperorchestra audit-rendered-references --quality-mode claim_safe`, `paperorchestra audit-citation-integrity --quality-mode claim_safe`, and `paperorchestra audit-citation-integrity-critic --quality-mode claim_safe` so rendered-reference, citation-intent, source-match, integrity audit, and deterministic critic artifacts are current and hash-bound into the evaluation. The citation critic artifact is not a fabricated model approval: it fails closed if any reviewed citation evidence artifact is missing, skipped, stale, unbound, or failed. The QA loop never emits a `success` verdict; `ready_for_human_finalization` still means Tier 4 is owned by humans. Plain `quality-eval` writes a diagnostic snapshot without consuming repair-attempt budget unless `--record-history` is supplied, and even recorded diagnostics/plans are marked non-budget. `qa-loop-plan`, `qa-loop-brief`, and `ralph-start --dry-run` are planning/briefing surfaces; they may append audit history but do not spend execution attempts. `ralph-start --dry-run` also bootstraps the `.omx/prd.json` expected by the OMX Ralph CLI. `qa-loop-step` performs exactly one bounded repair iteration and is the budget-consuming event; persistent multi-agent looping is delegated to OMX Ralph via `qa-loop-brief` / `ralph-start`, not reimplemented inside PaperOrchestra. Semi-auto repair candidates are candidate-scoped: if a candidate is rejected or remains uncommitted, canonical validation/compile/citation/quality artifacts are restored or regenerated for the current manuscript before the step returns. Terminal `human_needed`, `failed`, and `ready_for_human_finalization` plans are no-ops for `qa-loop-step`; continuation past those states must be an explicit Ralph/HITL decision. Claim-safe strict gates include prompt/meta leakage across manuscript source, generated plot text assets, and compiled-PDF text when extractable. Generated placeholder figures are failed/non-reviewable until replaced by human-authored final artwork.

For private fresh-smoke material packets outside the checkout, use
`scripts/fresh-full-live-smoke-loop.sh --material-root /private/materials
--expected-material-root /private/materials`. This keeps private inputs out of
git while preserving pointer/hash/manifest validation.

`PAPERO_DOMAIN` is intentionally conservative. The public package bundles only
the domain-neutral `generic` profile. External/private material packs may call
`paperorchestra.domains.register_domain(profile)` and then set `PAPERO_DOMAIN`
to that registered name, but they must do this **before** importing modules that
cache domain fields at import time, including `pipeline`, `critics`,
`source_obligations`, and `quality_loop_source_checks`. Unknown domain names fail
closed instead of silently falling back to `generic`.

### Shell provider

| Variable | Required? | Default | Why it exists |
| --- | --- | --- | --- |
| `PAPERO_MODEL_CMD` | Yes for `--provider shell` | unset | Model command that reads prompt from stdin and writes stdout |
| `PAPERO_PROVIDER_TIMEOUT_SECONDS` | Optional | unset | Timeout for shell-provider calls |
| `PAPERO_PROVIDER_TIMEOUT_GRACE_SECONDS` | Optional | `0` | Extra wait after provider timeout for Codex reconnects that may recover without replay |
| `PAPERO_PROVIDER_RETRY_ATTEMPTS` | Optional | `0` | Replay the same prompt only after retry-safe declaration plus reconnect/disconnect-like transport evidence; plain timeouts are grace-only |
| `PAPERO_PROVIDER_RETRY_BACKOFF_SECONDS` | Optional | `2` | Backoff between retryable provider prompt replays |
| `PAPERO_PROVIDER_RETRY_JITTER_SECONDS` | Optional | `0` | Optional random jitter added to provider retry backoff |
| `PAPERO_PROVIDER_RETRY_SAFE` | Optional | `0` | Required declaration before a provider command may be replayed after transport evidence |
| `PAPERO_PROVIDER_RETRY_TRACE_DIR` | Optional | unset | Optional JSONL audit trail for provider retry/grace attempts |
| `PAPERO_CODEX_RETRY_ATTEMPTS` | Fresh smoke optional | `1` | Fresh full live smoke's single retry owner for direct Codex calls and provider-wrapper calls; the script forces provider/OMX retry layers off to avoid nesting |
| `PAPERO_CODEX_RETRY_BACKOFF_SECONDS` | Fresh smoke optional | `15` | Backoff between retryable Codex transport attempts owned by the fresh full live smoke wrapper |
| `PAPERO_CODEX_RETRY_JITTER_SECONDS` | Fresh smoke optional | `0` | Optional random jitter added to wrapper-owned Codex retry backoff |
| `PAPERO_CODEX_CLI_PREFIX` | Fresh smoke optional | `codex` | Non-interactive replacement for shell aliases; set to `omx --madmax --high --dangerously-bypass-approvals-and-sandbox` when container QA should route Codex calls through OMX |
| `PAPERO_PROVIDER_SEED` | Advanced optional | unset | Seed passthrough for shell-provider subprocesses; downstream command must honor it; not a byte-identical generation guarantee |
| `PAPERO_PROVIDER_TEMPERATURE` | Advanced optional | unset | Temperature passthrough for shell-provider subprocesses |
| `PAPERO_PROVIDER_MAX_OUTPUT_TOKENS` | Advanced optional | unset | Max-output-tokens passthrough for shell-provider subprocesses |
| `PAPERO_ALLOWED_PROVIDER_BINARIES` | Optional | `codex,openai,ollama,llm,claude,gemini` | Allowlist for provider executables |

For cited-sentence claim-support review, `paperorchestra review-citations --evidence-mode model` uses this same provider surface. `--evidence-mode web` is intended for a web-search-capable provider; when no provider command is configured, the CLI falls back to a Codex command shaped like:

```bash
codex --search exec --skip-git-repo-check -m "${PAPERO_OMX_MODEL:-gpt-5.5}"
```

This path is independent of Semantic Scholar. It checks whether cited manuscript sentences are supported by evidence; it is not the same as `verify-papers --mode live`, which only builds bibliographic metadata. If `review-citations --evidence-mode web` is requested and the active shell writing provider is a non-search `codex exec` command, PaperOrchestra uses the Codex `--search exec` default for the citation-support critic unless an explicit `--provider-command` is supplied.

### Search / verification

| Variable | Required? | Default | Why it exists |
| --- | --- | --- | --- |
| `SEMANTIC_SCHOLAR_API_KEY` | Recommended / needed for reliable live verify | unset | Reduces live verification rate-limit risk |
| `PAPERO_SEARCH_GROUNDED_MODE` | Optional | unset | Force search-grounded discovery to `live` or `mock` |

`SEMANTIC_SCHOLAR_API_KEY` is not required for `review-citations --evidence-mode web`. Semantic Scholar-backed live verification and Codex/web-backed cited-sentence support are separate evidence lanes.

Semantic Scholar usage follows the PaperOrchestra paper's two-stage pattern:

1. Codex/web search or curated human input discovers candidate paper titles/DOIs/years.
2. S2 verifies and normalizes those candidates into real bibliographic entities.

The S2 wrapper enforces one outbound request per second, applies bounded retries for 429/5xx/network/timeout failures, honors `Retry-After`, and never silently falls back unless explicit fallback mode is configured in code. Broad S2 topic search can return poor rankings; rely on it for verification, not as the sole discovery engine.

### Compile

| Variable | Required? | Default | Why it exists |
| --- | --- | --- | --- |
| `PAPERO_ALLOW_TEX_COMPILE` | Yes for compile | `0` | Explicit opt-in before TeX compilation |
| `PAPERO_TEX_SANDBOX_CMD` | Advanced optional | auto-configured when possible | Override the compile sandbox wrapper |
| `TEXINPUTS` | Advanced optional | unset | Add TeX search paths for custom classes/styles |

### Reference smoke scripts

These tune `scripts/smoke-paperorchestra-reference.sh` and `scripts/smoke-omx-native.sh`:

- `PAPERO_SMOKE_LIVE`
- `PAPERO_SMOKE_COMPILE`
- `PAPERO_SMOKE_WORKDIR`
- `PAPERO_SMOKE_KEEP_WORKDIR`
- `PAPERO_SMOKE_PROVIDER`
- `PAPERO_SMOKE_RUNTIME_MODE`
- `PAPERO_SMOKE_DISCOVERY_MODE`
- `PAPERO_SMOKE_RESEARCH_MODE`
- `PAPERO_SMOKE_VERIFY_MODE`
- `PAPERO_SMOKE_REFINE_ITERATIONS`
- `PAPERO_SMOKE_TIMEOUT_SECONDS`
- `PAPERO_SMOKE_PROVIDER_TIMEOUT_SECONDS`
- `PAPERO_SMOKE_OMX_EXEC_TIMEOUT_SECONDS`
- `PAPERO_SMOKE_POLL_INTERVAL_SECONDS`
- `PAPERO_SMOKE_SEED_ANSWERS_FILE`
- `PAPERO_SMOKE_RESULTS_MARKDOWN_FILE`
- `PAPERO_SMOKE_REFERENCE_BENCHMARK_CASE`
- `PAPERO_REFERENCE_PDF`

### Testset smoke script

These tune the optional testset smoke script:

- `PAPERO_TESTSET_SMOKE_WORKDIR`
- `PAPERO_TESTSET_SMOKE_KEEP_WORKDIR`
- `PAPERO_TESTSET_SMOKE_PROVIDER`
- `PAPERO_TESTSET_SMOKE_PROVIDER_COMMAND`
- `PAPERO_TESTSET_SMOKE_RUNTIME_MODE`
- `PAPERO_TESTSET_SMOKE_REFINE_ITERATIONS`
- `PAPERO_TESTSET_SMOKE_COMPILE`
- `PAPERO_TESTSET_SMOKE_STRICT_OMX_NATIVE`
- `PAPERO_TESTSET_SMOKE_SKIP_RESEARCH_PRIOR_WORK`
- `PAPERO_TESTSET_SMOKE_PROVIDER_TIMEOUT_SECONDS`
- `PAPERO_TESTSET_SMOKE_OMX_EXEC_TIMEOUT_SECONDS`
- `PAPERO_TESTSET_SMOKE_OMX_CONTROL_TIMEOUT_SECONDS`

---

## 6. Auto-managed environment variables

You normally do **not** need to set these yourself:

- `BIBINPUTS`
- `BSTINPUTS`

PaperOrchestra prepares them during compile runs so BibTeX can find generated `.bib` and `.bst` assets.

---

## 7. Fast start recipes

### Safest first run

Use the bundled minimal fixture so a fresh clone has a session before `run`:

```bash
paperorchestra init \
  --idea examples/minimal/idea.md \
  --experimental-log examples/minimal/experimental_log.md \
  --template examples/minimal/template.tex \
  --guidelines examples/minimal/conference_guidelines.md \
  --figures-dir examples/minimal/figures
paperorchestra run --provider mock --verify-mode mock --runtime-mode compatibility
```

Or use the wrapper that creates a throwaway workdir and performs the same safe path:

```bash
scripts/demo-mock.sh
```

### Shell-provider live run

```bash
export PAPERO_MODEL_CMD='["codex","--search","exec","--skip-git-repo-check","-m","gpt-5.5","-c","model_reasoning_effort=\"high\""]'
# export PAPERO_PROVIDER_SEED=7
# export PAPERO_PROVIDER_TEMPERATURE=0.2
# export PAPERO_PROVIDER_MAX_OUTPUT_TOKENS=4096
paperorchestra run --provider shell --verify-mode mock --runtime-mode compatibility
```

### OMX-native live run

```bash
export PAPERO_MODEL_CMD='["codex","--search","exec","--skip-git-repo-check","-m","gpt-5.5","-c","model_reasoning_effort=\"high\""]'
paperorchestra run --provider shell --verify-mode mock --runtime-mode omx_native
```

### Live verification + compile

```bash
export PAPERO_MODEL_CMD='["codex","--search","exec","--skip-git-repo-check","-m","gpt-5.5","-c","model_reasoning_effort=\"high\""]'
export SEMANTIC_SCHOLAR_API_KEY='<your-key>'
export PAPERO_ALLOW_TEX_COMPILE=1
paperorchestra run \
  --provider shell \
  --provider-command "$PAPERO_MODEL_CMD" \
  --discovery-mode search-grounded \
  --verify-mode live \
  --verify-error-policy fail \
  --require-live-verification \
  --runtime-mode omx_native \
  --strict-omx-native \
  --compile
```

### Claim-safe live posture

```bash
export PAPERO_STRICT_OMX_NATIVE=1
export PAPERO_STRICT_CONTENT_GATES=1
paperorchestra audit-reproducibility --require-live-verification
paperorchestra quality-eval --quality-mode claim_safe --require-live-verification --output quality-eval.json
paperorchestra qa-loop-plan --quality-mode claim_safe --require-live-verification --quality-eval quality-eval.json
paperorchestra quality-gate --profile claim_safe --quality-mode claim_safe --require-live-verification
paperorchestra qa-loop-brief --quality-mode claim_safe --max-iterations 5
paperorchestra ralph-start --quality-mode claim_safe --max-iterations 5 --dry-run
```

---

## 8. What to do when something is missing

### `paperorchestra doctor` says `shell_provider_ready` is missing
Set `PAPERO_MODEL_CMD`.

### `paperorchestra doctor` says `omx_native_ready` is missing
Install `omx` and `codex`, then re-run `paperorchestra doctor`. If both binaries
exist but the bounded control-surface probe still fails, inspect the
`omx_control_surface_probe` check:

- missing `xz` / `xz-utils`: install `xz-utils`
- `bwrap: No permissions to create new namespace`: this container blocks the
  OMX harness sandbox; use `--runtime-mode compatibility` for local mock QA or
  run OMX-native outside the restricted container

### `paperorchestra doctor` says `live_verification_ready` is missing
Set `SEMANTIC_SCHOLAR_API_KEY` or accept that live verification may rate-limit.

### `paperorchestra doctor` says `compile_ready` is missing
Run:

```bash
paperorchestra check-compile-env
paperorchestra bootstrap-compile-env
```

Then set:

```bash
export PAPERO_ALLOW_TEX_COMPILE=1
```

### The README feels too long
That's intentional now: the README is the broad product/operator map, and this file is the canonical environment/setup sheet.
