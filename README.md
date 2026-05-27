# PaperOrchestra

PaperOrchestra is an **independent GPT/Codex + OMX port/reconstruction** of:

> *PaperOrchestra: A Multi-Agent Framework for Automated AI Research Paper Writing*  
> arXiv:2604.05018

It reconstructs the paper's manuscript-writing contract around explicit artifacts, stage boundaries, validation, review gates, and fidelity checks. It is **not** the official authors' code and does not claim access to unpublished implementation details.

---

## TL;DR

```bash
git clone https://github.com/kosh7707/paperorchestra-for-codex.git
cd paperorchestra-for-codex
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .

# Safe self-contained demo: no live search/model calls, no reference PDF required.
./scripts/demo-mock.sh

# Keep demo outputs inside this checkout instead of /tmp:
./scripts/demo-mock.sh --in-repo

# Then enter the demo workdir before inspecting/exporting the current session:
cd .paper-orchestra/manual-demo
paperorchestra status --summary
paperorchestra export-artifacts --output "$OLDPWD/paperorchestra-output"
cd "$OLDPWD"

# Paper-derived smoke: requires your own local legal copy of the PaperOrchestra reference PDF.
PAPERO_REFERENCE_PDF=/absolute/path/to/PaperOrchestra-reference.pdf \
  ./scripts/smoke-paperorchestra-reference.sh
```

Repository evidence currently checked in:

- smoke scripts for a safe reference path and a live-ish OMX/Codex path
- test coverage evolves with the repo; verify the current suite locally instead of relying on a hard-coded count in this README

### Current v1-alpha status

The v1 orchestrator/runtime is currently treated as **v1-alpha**.  That means
the CLI/MCP/Skill/orchestration surfaces are intended to be usable and
auditable, but a generated paper is **not submission-ready** merely because the
runtime completed.

The known limitations for this alpha include:

- citation/claim quality can still block or require manual author judgment;
- figure finalization is drafting-oriented and may require human-authored final
  artwork;
- operator repair convergence is still being hardened, so repeated repair loops
  may end in `human_needed` or `not_ready`;
- quality failures must remain visible as `BLOCK`, `not_ready`, warnings, or
  explicit audit records; hiding them as success is a false readiness bug.

Current checkpoint semantics: the `v0.2.3` tag marks a loop/evidence
checkpoint where a private-material fresh live smoke verified the system loop
while the generated manuscript correctly remained `human_needed`. Treat that as
engine evidence, not as publication readiness.

### If you are using Codex

A good first prompt after opening Codex is:

> Clone `https://github.com/kosh7707/paperorchestra-for-codex.git`, read `README.md` and `ENVIRONMENT.md`, run the safe mock demo first, and only then explain what I need to configure for shell/Codex, OMX, Semantic Scholar, MCP, and the local skill. Do not start a live model/search run until the mock path works.

Codex CLI and oh-my-codex are external prerequisites for the advanced paths. This repo documents how to use them after they are installed; it does not install them for you.

## Codex-first setup path

If the first thing you do is open Codex and ask “how do I use this?”, use this
path. It keeps the first run offline, proves the local package works, registers
the optional Codex surfaces, then restarts Codex so MCP tools can actually be
attached to the next conversation.

Give Codex this prompt:

> Clone `https://github.com/kosh7707/paperorchestra-for-codex.git`, set it up in a local `.venv`, run `paperorchestra first-use --intent setup`, run the safe mock demo, then configure the local skill and MCP server. Do not run the full repository test suite as setup proof; this is first-user setup, not developer CI. After MCP registration, remind me to restart Codex completely and open a new Codex session before checking for `mcp__paperorchestra__...` tools. If MCP is registered but not attached, use the CLI fallback instead of pretending MCP is active.

Copyable command path:

```bash
git clone https://github.com/kosh7707/paperorchestra-for-codex.git
cd paperorchestra-for-codex
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .

# Compact first-user guide from the implementation itself.
paperorchestra first-use --intent setup
paperorchestra first-use --intent how_to_use

# First proof: no live model/search/OMX required.
./scripts/demo-mock.sh --in-repo
cd .paper-orchestra/manual-demo
paperorchestra status --summary
paperorchestra export-artifacts --output "$OLDPWD/paperorchestra-output"
cd "$OLDPWD"

# Optional Codex integration surfaces.
./scripts/install-skill.sh
./scripts/register-codex-mcp.sh --use-local-venv --dry-run
./scripts/register-codex-mcp.sh --use-local-venv
scripts/smoke-paperorchestra-mcp.py --transport newline --json
```

**MCP restart boundary:** after `./scripts/register-codex-mcp.sh
--use-local-venv`, **Restart Codex completely** and open a **new Codex
session**. MCP tools are injected when the client/session starts; an already-open
conversation usually will not gain `mcp__paperorchestra__...` tools just because
the config changed.

After the restart:

```bash
codex mcp list
scripts/smoke-codex-mcp-attach.sh
```

`codex mcp list` shows config registration; it does not prove active attachment in the current chat. Active attachment means the new session
actually exposes tools named like `mcp__paperorchestra__status` or
`mcp__paperorchestra__orchestrate`. If the raw MCP smoke passes but those tools
are absent, use the **CLI fallback**:

```bash
paperorchestra inspect-state --material ./my-material --json
paperorchestra orchestrate --material ./my-material --execute-local --write-evidence --json
paperorchestra first-use --intent start --material ./my-material
```

Do not start a live model/search run, claim-safe QA loop, fresh full live
smoke, or full repository test suite while proving first-user setup. Full `pytest`
is a developer/CI check and may require PATH, TeX, sandbox, or live-smoke
fixtures that are not needed for a first user to start using PaperOrchestra.

---

## First 10 minutes: get one mock manuscript

If you just cloned this repo and want to prove it works before configuring any
live model/search/OMX path:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .

paperorchestra --version
paperorchestra environment --summary
paperorchestra doctor
./scripts/demo-mock.sh
```

Expected result:

- the demo ends with `[demo] SUCCESS`
- the session reaches `draft_complete`
- the generated manuscript is `paper.full.tex`
- the final summary prints the workdir, artifact directory, review JSON, and
  next commands
- the full pipeline log is captured at `demo-mock.log`; use
  `./scripts/demo-mock.sh --verbose` or `PAPERO_DEMO_VERBOSE=1` if you want the
  old stream-everything output

For container QA, prefer a persistent workdir so the files are easy to copy from
a bind mount:

```bash
./scripts/demo-mock.sh --in-repo
# equivalent:
PAPERO_DEMO_WORKDIR="$PWD/.paper-orchestra/manual-demo" ./scripts/demo-mock.sh
```

Useful follow-up commands:

```bash
# after the default demo:
cd <Workdir printed by demo>

# after ./scripts/demo-mock.sh --in-repo:
cd .paper-orchestra/manual-demo

paperorchestra status --summary
paperorchestra check-compile-env
PAPERO_ALLOW_TEX_COMPILE=1 paperorchestra compile
paperorchestra export-artifacts --output "$OLDPWD/paperorchestra-output"
```

`export-artifacts` copies the current session's main outputs (`paper.full.tex`,
`paper.full.pdf` when present, `references.bib`, review/audit JSON, and
`session.json`) to the directory you choose. This is the simplest way to pull a
PDF/manuscript out of a Docker/WSL bind-mounted folder.

### Orchestrated first-use check: one local step, no live calls

If you already have a material folder and want Codex/PaperOrchestra to inspect
it without starting a full paper run, use the bounded v1 orchestrator surface:

```bash
paperorchestra inspect-state --material ./my-material --json
paperorchestra orchestrate --material ./my-material --execute-local --write-evidence --json
```

`--execute-local` performs **one deterministic local step**. It is **not a full paper run** and it does not draft, revise, compile, export, invoke OMX, call a
live model, or search the web. No live model/search, OMX, compile/export, or drafting happens in this check.

Expected useful output:

- top-level `execution=bounded_local_execution`
- an `execution_record` with the local action and status
- a public-safe evidence bundle when `--write-evidence` is set
- a next action such as `start_autoresearch` / `$autoresearch` when the local
  claim graph finds machine-solvable evidence or citation gaps

If no material is supplied, the local step does not fabricate inputs. It returns
`action_taken=provide_material`, `execution_record.status=unsupported`, and
`reason=material_input_required`.

When the MCP server is actively attached, the equivalent high-level call is:

```json
{"name": "orchestrate", "arguments": {"material": "./my-material", "execute_local": true, "write_evidence": true}}
```

If `codex mcp list` shows registration but the current chat has no
`mcp__paperorchestra__...` tools, use the CLI fallback above. Registration is
not the same as active session attachment.

The evidence bundle is a diagnostic artifact, not a readiness pass. It records
state, blockers, local execution evidence, and next actions; it does not approve
drafting, citations, final quality, or submission.

---

## Choose your path: what to run first

Yes, another person can use this repo — but only if they pick the path that
matches their machine. Start with the smallest path that proves the next thing
you need, then move upward.

| Goal | Run first | Requires | What success means |
| --- | --- | --- | --- |
| See one safe manuscript draft | `./scripts/demo-mock.sh --in-repo` | Python 3.11+ | The pipeline is installed and can create mock artifacts. This is **not** citation-fidelity proof. |
| Inspect/export artifacts from a container | `paperorchestra status --summary` then `paperorchestra export-artifacts --output ./paperorchestra-output` | A current session | You can find/copy the TeX, PDF if present, review JSON, audits, and session metadata. |
| Build a PDF | `paperorchestra check-compile-env` then `PAPERO_ALLOW_TEX_COMPILE=1 paperorchestra compile` | TeX engine + usable sandbox | `complete` means a PDF was built. It does **not** mean the paper is claim-safe. |
| Draft with a real model | configure `PAPERO_MODEL_CMD`, check `paperorchestra run --help`, then use the live-run recipe below | Codex CLI or another supported shell model command | The model path works. You still need citation, review, and quality gates. |
| Run claim-safe QA/Ralph evidence | `./scripts/fresh-full-live-smoke-loop.sh --help`, then run it with explicit `--evidence-root` and `--material-root` | live provider, verification keys, strict flags, enough time/tokens | The loop can prove progress, block, or reach `ready_for_human_finalization`; it never proves “publish automatically.” |
| Use Codex MCP/skill integration | `./scripts/register-codex-mcp.sh --use-local-venv` then `./scripts/smoke-paperorchestra-mcp.py --transport newline --json` | Codex CLI config + this venv | MCP server health is OK for Codex-style newline framing. Use `scripts/smoke-codex-mcp-attach.sh` when you need proof of active Codex tool attachment. |

Keep these status meanings separate:

- `draft_complete`: a draft manuscript exists.
- `complete`: a compiled PDF exists.
- `human_needed`: automation found a boundary that needs an operator/human decision.
- `ready_for_human_finalization`: the best automated terminal state; humans still own final claims, figures, bibliography, and submission decisions.
- `BLOCK`, `not_ready`, or non-zero quality-gate exits: the system refused to overclaim. Treat this as a useful safety result, not just a failure.

The strict lifecycle is documented in
[`docs/quality-gate-state-machine.md`](docs/quality-gate-state-machine.md).
For setup knobs and missing-package fixes, use [`ENVIRONMENT.md`](ENVIRONMENT.md).

For task-focused walkthroughs, start with the tutorials below instead of reading this whole README linearly.

## Tutorials

| Tutorial | Use when |
| --- | --- |
| [`docs/tutorials/index.md`](docs/tutorials/index.md) | You want the tutorial map and document roles. |
| [`docs/tutorials/start.md`](docs/tutorials/start.md) | You are setting up from a fresh checkout and need stale CLI/MCP guidance. |
| [`docs/tutorials/mock-demo.md`](docs/tutorials/mock-demo.md) | You want the safe offline mock/demo path and export commands. |
| [`docs/tutorials/docker-container-qa.md`](docs/tutorials/docker-container-qa.md) | You need Docker/container QA, named-volume venv, PEP 668, compile, and export guidance. |
| [`docs/tutorials/rendered-pdf-human-qa.md`](docs/tutorials/rendered-pdf-human-qa.md) | You are acting as the human/operator who must inspect rendered PDF pages. |
| [`docs/tutorials/claim-safe-quality-loop.md`](docs/tutorials/claim-safe-quality-loop.md) | You need claim-safe quality gates, `qa-loop-step`, or Ralph handoff semantics. |


---

## What this project is

### Goal

This project aims to reconstruct PaperOrchestra as closely as possible while making one explicit substitution:

- original model stack: Gemini-family models
- this port: GPT/Codex via `codex` / `omx exec`

Operationally, treat PaperOrchestra as a **general-purpose paper drafting
engine**. The subject of the generated paper should come from the user's input
material, not from this repository. If a run starts writing a paper *about
PaperOrchestra itself* when the supplied material is about another topic, that
is a target-fidelity/quality-gate problem to inspect and repair.

### Must stay faithful

The project treats these as reconstruction-critical:

- prompt semantics
- stage contracts
- artifact handoff boundaries
- benchmark/eval proof surfaces
- review/refinement gate semantics

### Allowed substitutions

These are allowed to differ from the original paper as long as the substitute is explicit and evidenced:

- foundation model: Gemini → GPT/Codex
- search engine / retrieval source
- runtime surface: OMX/Codex/MCP/CLI
- bounded substitutes for unavailable components such as PaperBanana

### Explicit limitations

- This is not the official codebase.
- PaperBanana-level plotting is not fully reconstructed; this repo uses bounded SVG/LaTeX figure substitutes.
- The full 200-paper PaperWritingBench is not bundled; this repo includes paper-derived reference-case scaffolding.
- Human evaluation is not reproduced; structured review/eval artifacts are provided instead.

### Detailed limitations and non-goals

This project is intentionally positioned as a **human-supervised drafting and reconstruction scaffold**, not a paper autopilot that should be trusted to produce a submission-ready manuscript without expert review.

#### 1. Final paper responsibility stays with a human

- The repo can generate high-grade drafts, section skeletons, review artifacts, and revision suggestions.
- It does **not** remove the need for a human author to decide what is true, what is novel, what is safe to claim, and what is worth submitting.
- If you want a system that autonomously writes a venue-ready paper end-to-end and should be trusted without close review, this repo is **not** that system.

#### 2. Figures are drafting scaffolds, not camera-ready scientific figures

- The current plotting path is useful for **figure ideas, placeholders, layout reservation, and narrative scaffolding**.
- It is **not** a substitute for a carefully prepared final figure set.
- In particular, operators should expect to replace, redraw, or heavily edit figures before any serious submission workflow.
- When figure fidelity matters, the correct interpretation is: **the human owns the final figure.**

#### 3. Proofs, claims, and experiment narratives still need domain-expert review

- The system can preserve and restate a technical argument, but that is not the same as producing a proof that is publication-grade.
- Security proofs, reduction structure, benchmark methodology, fairness caveats, and threat-model assumptions may still be compressed, underexplained, or over-smoothed relative to a real paper.
- Comparative claims such as “better than”, “outperforms”, or “state of the art” should be treated as draft language unless a human has checked the underlying evidence.

#### 4. Citation and bibliography quality are not automatically publication-grade

- The literature lane can discover/import sources, build a registry, and emit BibTeX, but it does not guarantee conference/journal-quality bibliography curation.
- Live verification can be rate-limited or incomplete.
- Imported prior-work seeds are useful and often desirable, but they are **curated inputs**, not automatic proof that every citation is fully verified.
- A human should still normalize venues, remove weak references, merge duplicates, and check that each citation actually supports the surrounding claim.

#### 5. Benchmark and evaluation fidelity are partial by design

- This repo includes **reference-case scaffolding** and eval artifacts intended to make reconstruction claims inspectable.
- It does **not** reproduce the full benchmark/data/autorater stack from the original paper.
- Human evaluation is represented through structured review surfaces and artifacts, not by reproducing the original human-study pipeline.
- As a result, fidelity/eval outputs are best understood as **honest bounded substitutes**, not full parity guarantees.

#### 6. Output quality depends strongly on environment and operator choices

- The same workflow can behave very differently depending on the shell provider, model quality, prompt budget, retrieval quality, timeout settings, and compile environment.
- `mock`, `compatibility`, and fallback paths are intentionally useful for demos and debugging, but those paths should not be confused with claim-safe evidence.
- A successful local run proves the repo is operable on that machine; it does not by itself prove research-grade output quality.

#### 7. “Claim-safe” is a stricter posture than “it ran successfully”

- A run can finish and still be unsuitable for strong reproducibility or fidelity claims.
- If you care about serious evidence, use strict settings and inspect the generated proof surfaces (`runtime-parity.json`, `validation.*.json`, review artifacts, fidelity/reproducibility audits).
- The correct standard is not “did it compile?” but “did the generated artifacts justify the claim I want to make?”

#### 8. This project is a research-writing accelerator, not a substitute for authorship

- The most realistic and intended use is:
  1. use the system to accelerate synthesis, structure, and draft generation,
  2. let humans decide what to keep, revise, redraw, verify, or delete,
  3. treat the output as a serious working draft rather than an automatic final paper.
- In short: **this repo should help a human write a better paper faster, not eliminate the human author.**

#### Tracking seed: PaperBanana gap

Keep this limitation visible until a GitHub issue or replacement implementation closes it.

- **Suggested issue title:** `Implement or explicitly scope the PaperBanana plotting substitute`
- **Current state:** stage 2 emits bounded SVG/LaTeX figure substitutes instead of PaperBanana's VLM-guided closed-loop plot generation.
- **Why it matters:** the paper treats PaperBanana-style plot generation and visual critique as a core component, so this port must not claim full plotting fidelity while that loop is absent.
- **Acceptable closure paths:**
  1. integrate a real PaperBanana-compatible service,
  2. implement a local Codex/VLM + renderer feedback loop with documented parity gaps, or
  3. keep it as an explicit non-goal and ensure fidelity/eval artifacts report the substitution.
- **Do not forget:** if this remains deferred, release notes and GitHub project boards should keep it under `limitation`, `plotting`, and `paper-fidelity`.

---

## Architecture at a glance

PaperOrchestra follows the paper's five-stage pipeline:

1. **Outline Generation**
2. **Plot Generation**
3. **Literature Review**
4. **Section Writing**
5. **Iterative Content Refinement**

The intended operating model is:

- **OMX**: runtime backbone and the closest thing in this repo to the paper's staged multi-agent execution model
- **MCP server**: tool/control-plane surface for agents
- **Skill**: policy/playbook for Codex-style usage
- **CLI**: operator/debug/help/audit/CI surface

`runtime_mode=omx_native` is the multi-agent-leaning path. `runtime_mode=compatibility` and Python fallback paths still exist for debugging, safer dry runs, and partial-environment operation, so not every run should be described as a full OMX-native multi-agent execution.

---

## Install

```bash
git clone https://github.com/kosh7707/paperorchestra-for-codex.git
cd paperorchestra-for-codex
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Use a virtual environment first. Some Linux distributions mark the system
Python as externally managed, so direct `python3 -m pip install -e .` can fail
with a PEP 668 error. The `.venv` flow also prevents a stale globally installed
`paperorchestra` command from shadowing the checkout you just cloned.

This installs:

- `paperorchestra`
- `paperorchestra-mcp`

It does **not** install external operator runtimes such as Codex CLI or oh-my-codex.
Install those separately when you want shell-provider or OMX-native runs, then verify
them with `codex --help`, `omx doctor`, and `omx status`.

Canonical environment/setup references:

- `ENVIRONMENT.md` — the concise operator setup sheet
- `README.md` (`Copyable environment template`) — copyable environment-variable template
- `paperorchestra environment` — canonical environment inventory + readiness profiles
- `paperorchestra doctor` — what is missing on the current machine right now

Useful sanity checks:

```bash
paperorchestra --help
paperorchestra quickstart --scenario environment
paperorchestra environment
paperorchestra quickstart --scenario new-paper
paperorchestra doctor
```

### What you must install for each use case

| Goal | Required tools | Required env | Verification |
| --- | --- | --- | --- |
| Safe local demo | Python 3.11+ | none | `paperorchestra doctor` |
| Shell-provider draft run | Python 3.11+, `codex` (or another supported shell binary) | `PAPERO_MODEL_CMD` | `codex --help`, `paperorchestra environment` |
| OMX-native multi-agent run | Python 3.11+, `codex`, `omx` | usually `PAPERO_MODEL_CMD` | `codex --help`, `omx doctor` |
| Live literature verification | above + network access | `SEMANTIC_SCHOLAR_API_KEY` recommended | `paperorchestra verify-papers --mode live --on-error skip` |
| Compile to PDF | above + TeX toolchain + sandbox wrapper | `PAPERO_ALLOW_TEX_COMPILE=1` and often `PAPERO_TEX_SANDBOX_CMD` | `paperorchestra check-compile-env` |

PaperOrchestra intentionally treats Codex CLI and oh-my-codex as external operator
tools. The repo documents how to use them after they exist on `PATH`; it does not
vendor or bootstrap them for you.

### Zero-to-first-run checklist

If you want the shortest newcomer path that proves the repo is usable:

```bash
git clone https://github.com/kosh7707/paperorchestra-for-codex.git
cd paperorchestra-for-codex
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .

# confirm the local CLI is alive; `paperorchestra doctor` reports package_context
# so stale installs are visible.
python -m paperorchestra.cli --help
paperorchestra --help
paperorchestra doctor
paperorchestra environment

# first success path: initialize the bundled minimal fixture, then run offline
paperorchestra init \
  --idea examples/minimal/idea.md \
  --experimental-log examples/minimal/experimental_log.md \
  --template examples/minimal/template.tex \
  --guidelines examples/minimal/conference_guidelines.md \
  --figures-dir examples/minimal/figures

paperorchestra run \
  --provider mock \
  --verify-mode mock \
  --runtime-mode compatibility \
  --discovery-mode model \
  --refine-iterations 0
```

If that works, the project is already usable on the current machine.

Only then move to:

- `--provider shell` after `PAPERO_MODEL_CMD` is configured
- `--runtime-mode omx_native` after `omx` + `codex` are healthy
- `--verify-mode live` after `SEMANTIC_SCHOLAR_API_KEY` is set
- `--compile` after `paperorchestra check-compile-env` passes


### Developer fresh-QA checklist

For contributor/debugging work, install the small dev extra and run the one-shot fresh QA wrapper:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
scripts/fresh-qa.sh
```

The wrapper writes logs and `summary.json` under `.paper-orchestra/fresh-qa/`. It checks CLI help, `doctor`, environment inventory, the bundled minimal mock pipeline, fidelity/eval artifact surfaces, compile readiness, optional compile when ready, and `pytest`.

Useful variants:

```bash
scripts/fresh-qa.sh --skip-tests
scripts/fresh-qa.sh --skip-compile
python -m pytest -q
```

Container entry must refresh Codex CLI and OMX before PaperOrchestra QA. Use the repo wrapper, not a raw `docker run`, unless you reproduce the same entrypoint. The full Docker runbook, including the named-volume venv fast loop and mandatory PDF dogfood path, is in [`docs/tutorials/docker-container-qa.md`](docs/tutorials/docker-container-qa.md).

Minimal package hints:

```bash
apt-get install -y xz-utils
apt-get install -y pkg-config libpng-dev texlive-latex-base texlive-latex-recommended texlive-fonts-recommended latexmk bubblewrap
```

If `bwrap` is installed but unusable, install `firejail` or set `PAPERO_TEX_SANDBOX_CMD`; `paperorchestra bootstrap-compile-env` prints the machine-specific command form.

### Beast-proof live path: Codex discovers, S2 verifies

If you want the closest practical path to the PaperOrchestra paper's literature lane, use this mental model:

```text
Codex with web search -> candidate titles/DOIs/years -> Semantic Scholar verification -> verified registry/BibTeX -> writer cites only registry keys
```

Semantic Scholar is **not** a good canonical-reference search engine by itself. Do not expect broad S2 queries such as `reliable distributed systems` to return the best source at rank 1. In this project, S2 is the anti-hallucination verifier: it checks that a candidate discovered by Codex/manual research resolves to a real S2 entity, has metadata/abstract when required, predates the cutoff, and deduplicates by `paperId`.

Recommended first live setup:

```bash
cat > .env <<'EOF'
PAPERO_MODEL_CMD='["codex","--search","exec","--skip-git-repo-check","-m","gpt-5.5","-c","model_reasoning_effort=\"high\""]'
SEMANTIC_SCHOLAR_API_KEY='<your-key>'
PAPERO_PROVIDER_TIMEOUT_SECONDS=1800
PAPERO_PROVIDER_TIMEOUT_GRACE_SECONDS=180
# Provider replay is opt-in for custom retry-safe provider wrappers.  The fresh
# full live smoke script disables this layer and uses PAPERO_CODEX_RETRY_* instead
# so a single prompt cannot be replayed by nested retry loops.
# Requires BOTH PAPERO_PROVIDER_RETRY_SAFE=1 AND PAPERO_PROVIDER_RETRY_ATTEMPTS>0.
# PAPERO_PROVIDER_RETRY_SAFE=1
# PAPERO_PROVIDER_RETRY_ATTEMPTS=1
# PAPERO_PROVIDER_RETRY_BACKOFF_SECONDS=15
# PAPERO_PROVIDER_RETRY_JITTER_SECONDS=3
PAPERO_OMX_EXEC_TIMEOUT_SECONDS=1800
PAPERO_OMX_TIMEOUT_GRACE_SECONDS=180
# OMX exec is grace-only and never replayed.  Read-only control calls
# may be retried outside fresh smoke; fresh smoke disables this layer as well.
# PAPERO_OMX_RETRY_ATTEMPTS=1
# PAPERO_OMX_RETRY_BACKOFF_SECONDS=15
# PAPERO_OMX_RETRY_JITTER_SECONDS=3
# Fresh full live smoke's single retry owner for direct Codex/provider-wrapper calls:
PAPERO_CODEX_RETRY_ATTEMPTS=1
PAPERO_CODEX_RETRY_BACKOFF_SECONDS=15
PAPERO_CODEX_RETRY_JITTER_SECONDS=3
# Optional smoke-level replay for provider-backed stages after retryable
# transport evidence from the stage log or matching provider trace:
PAPERO_SMOKE_STEP_RETRY_ATTEMPTS=1
PAPERO_SMOKE_STEP_RETRY_BACKOFF_SECONDS=15
PAPERO_SMOKE_STEP_RETRY_JITTER_SECONDS=3
# Optional for OMX/container QA where a shell alias would not be honored:
# PAPERO_CODEX_CLI_PREFIX='omx --madmax --high --dangerously-bypass-approvals-and-sandbox'
PAPERO_OMX_MODEL=gpt-5.5
PAPERO_OMX_REASONING_EFFORT=high
PAPERO_STRICT_CONTENT_GATES=1
# Enable only if you want PDF compilation in this run:
# PAPERO_ALLOW_TEX_COMPILE=1
EOF
chmod 600 .env
set -a && source .env && set +a
```

Then run the stages explicitly once, so failures are easy to understand:

```bash
paperorchestra outline --provider shell --provider-command "$PAPERO_MODEL_CMD" --runtime-mode omx_native --strict-omx-native
paperorchestra discover-papers --mode search-grounded --provider shell --provider-command "$PAPERO_MODEL_CMD" --runtime-mode omx_native --strict-omx-native
paperorchestra verify-papers --mode live --on-error fail
paperorchestra build-bib
paperorchestra plan-narrative
paperorchestra write-intro-related --provider shell --provider-command "$PAPERO_MODEL_CMD" --runtime-mode omx_native --strict-omx-native
paperorchestra write-sections --provider shell --provider-command "$PAPERO_MODEL_CMD" --runtime-mode omx_native --strict-omx-native
```

One-shot equivalent once the staged path is understood:

```bash
paperorchestra run   --provider shell   --provider-command "$PAPERO_MODEL_CMD"   --runtime-mode omx_native   --strict-omx-native   --discovery-mode search-grounded   --verify-mode live   --verify-error-policy fail   --require-live-verification   --refine-iterations 1
```

Use `--verify-error-policy skip` only when you want to keep partial S2 successes and inspect `verification_errors.json`; use `--verify-fallback-mode mock` only for draft/demo runs that must not be treated as live citation-fidelity evidence.

### Operator quick start: know these first

For a first real run, learn these commands and knobs before spending model/search calls:

```bash
# 1. Is the environment usable, and what should I do next if a session is stuck?
paperorchestra environment --summary
paperorchestra doctor
paperorchestra status

# 2. How expensive/noisy will the intended run be?
paperorchestra estimate-cost --discovery-mode search-grounded --refine-iterations 1 --compile --runtime-mode omx_native

# 3. Run safely first, then live.
paperorchestra run --provider mock --verify-mode mock --runtime-mode compatibility --discovery-mode model

# 4. Inspect the proof/audit surfaces after a run.
paperorchestra audit-fidelity
paperorchestra audit-reproducibility
paperorchestra build-session-eval-summary

# 5. Clean local OMX execution scratch files when iterating.
paperorchestra cleanup-tmp --max-age-seconds 3600
```

Most important live-run environment variables:

```bash
export PAPERO_OMX_MODEL=gpt-5.5
export PAPERO_OMX_REASONING_EFFORT=xhigh
export PAPERO_OMX_EXEC_TIMEOUT_SECONDS=900
export PAPERO_DOMAIN=generic
export SEMANTIC_SCHOLAR_API_KEY='<recommended for --verify-mode live>'
export PAPERO_ALLOW_TEX_COMPILE=1
```

Use `--strict-omx-native` or `PAPERO_STRICT_OMX_NATIVE=1` when a run is meant to support a reproducibility/fidelity claim and should fail instead of falling back to the Python provider.

`PAPERO_DOMAIN` defaults to the public domain-neutral `generic` profile. External
plugins or private material packs can register a profile with
`paperorchestra.domains.register_domain(profile)`, then set `PAPERO_DOMAIN` to
that name. Register profiles before importing modules that cache domain fields
(`pipeline`, `critics`, `source_obligations`, `quality_loop_source_checks`);
unknown names fail closed instead of silently falling back.

---


## Copyable environment template

The full environment inventory and readiness profiles live in [`ENVIRONMENT.md`](ENVIRONMENT.md) and `paperorchestra environment`. Keep local secrets out of commits; copy only the variables you need into `.env`, direnv, mise, or your shell profile.

Common operator-set variables:

```bash
# Shell provider for real model-backed runs.
export PAPERO_MODEL_CMD='["codex","--search","exec","--skip-git-repo-check","-m","gpt-5.5","-c","model_reasoning_effort=\"high\""]'

# Live citation/search verification.
export SEMANTIC_SCHOLAR_API_KEY='<your-key>'

# Compile only when intentionally building a PDF.
export PAPERO_ALLOW_TEX_COMPILE=1

# Domain remains generic unless you register an external domain profile in code.
export PAPERO_DOMAIN=generic
```

For smoke-specific knobs such as `PAPERO_SMOKE_WORKDIR`, `PAPERO_TESTSET_SMOKE_WORKDIR`, provider retry policy, and OMX timeouts, use [`ENVIRONMENT.md`](ENVIRONMENT.md). For Docker/container QA, use [`docs/tutorials/docker-container-qa.md`](docs/tutorials/docker-container-qa.md).

## Prerequisites

The short version:

- basic CLI/demo: Python 3.11+, `.venv`, and `python -m pip install -e .`
- shell-provider live runs: set `PAPERO_MODEL_CMD`
- OMX-native runs: install `omx` and `codex`
- live verification: set `SEMANTIC_SCHOLAR_API_KEY`
- compile: install a supported LaTeX engine + sandbox tool, then set `PAPERO_ALLOW_TEX_COMPILE=1`; use `PAPERO_LATEX_TIMEOUT_SEC` for slower builds

Fast inspection/remediation commands:

```bash
paperorchestra environment
paperorchestra doctor
paperorchestra check-compile-env
paperorchestra bootstrap-compile-env
```

Full install/package/env details now live in **`ENVIRONMENT.md`** so this README can stay focused on product/workflow usage.

---

## Environment variables

The full inventory is in **`ENVIRONMENT.md`**. The short template above is for the variables most operators actually set. The following compact index intentionally names every operator-facing variable so README, `ENVIRONMENT.md`, and generated environment inventory stay in sync:

- `PAPERO_OMX_MODEL`
- `PAPERO_OMX_REASONING_EFFORT`
- `PAPERO_OMX_EXEC_TIMEOUT_SECONDS`
- `PAPERO_OMX_CONTROL_TIMEOUT_SECONDS`
- `PAPERO_STRICT_OMX_NATIVE`
- `PAPERO_REFINE_AXIS_TOLERANCE`
- `PAPERO_STRICT_CONTENT_GATES`
- `PAPERO_LATEX_TIMEOUT_SEC`
- `PAPERO_DOMAIN`
- `PAPERO_MODEL_CMD`
- `PAPERO_PROVIDER_TIMEOUT_SECONDS`
- `PAPERO_PROVIDER_TIMEOUT_GRACE_SECONDS`
- `PAPERO_PROVIDER_RETRY_ATTEMPTS`
- `PAPERO_PROVIDER_RETRY_BACKOFF_SECONDS`
- `PAPERO_PROVIDER_RETRY_JITTER_SECONDS`
- `PAPERO_PROVIDER_RETRY_SAFE`
- `PAPERO_PROVIDER_RETRY_TRACE_DIR`
- `PAPERO_OMX_TIMEOUT_GRACE_SECONDS`
- `PAPERO_OMX_RETRY_ATTEMPTS`
- `PAPERO_OMX_RETRY_BACKOFF_SECONDS`
- `PAPERO_OMX_RETRY_JITTER_SECONDS`
- `PAPERO_PROVIDER_SEED`
- `PAPERO_PROVIDER_TEMPERATURE`
- `PAPERO_PROVIDER_MAX_OUTPUT_TOKENS`
- `PAPERO_ALLOWED_PROVIDER_BINARIES`
- `PAPERO_CODEX_RETRY_ATTEMPTS`
- `PAPERO_CODEX_RETRY_BACKOFF_SECONDS`
- `PAPERO_CODEX_RETRY_JITTER_SECONDS`
- `PAPERO_SMOKE_STEP_RETRY_ATTEMPTS`
- `PAPERO_SMOKE_STEP_RETRY_BACKOFF_SECONDS`
- `PAPERO_SMOKE_STEP_RETRY_JITTER_SECONDS`
- `SEMANTIC_SCHOLAR_API_KEY`
- `PAPERO_SEARCH_GROUNDED_MODE`
- `PAPERO_ALLOW_TEX_COMPILE`
- `PAPERO_TEX_SANDBOX_CMD`
- `TEXINPUTS`
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

Useful helper commands:

```bash
paperorchestra environment
paperorchestra doctor
paperorchestra quickstart --scenario environment
```

Live verification skips individual candidate lookup failures by default and records them in `verification_errors.json`. Use `--on-error fail` on `verify-papers` or `--verify-error-policy fail` on `run` when you want the first Semantic Scholar/API error to stop the run.

Important distinction:

- `verify-papers --mode live` is a **bibliographic metadata lookup** lane. It asks Semantic Scholar whether candidate papers exist and writes `citation_registry.json`, `citation_map.json`, and `references.bib`.
- `review-citations` is the **cited-sentence claim-support** lane. It asks whether a manuscript sentence with `\cite{...}` is actually supported by the cited source or independently found public evidence.

These are intentionally separate. A Semantic Scholar title match, DOI, abstract, or citation-key/title overlap is not proof that a cited sentence is supported. Conversely, lack of a Semantic Scholar API key must not prevent claim-support review when a Codex/web-capable critic or human-curated evidence is available.

#### How the S2 wrapper behaves

The live verification path uses `paperorchestra.s2_api.SemanticScholarClient`:

- sends `x-api-key` when `SEMANTIC_SCHOLAR_API_KEY` is set
- enforces a conservative process-local 1 request/second limiter
- retries 429 and transient 5xx responses with bounded exponential backoff
- honors `Retry-After` up to a cap
- retries network/timeouts by policy
- defaults to `fallback_mode="raise"`; empty fallback must be requested explicitly and is not cached
- redacts the key from errors/loggable request records

If S2 returns results for a candidate, `verify_candidate_title()` still rejects unsafe entries: fuzzy title match must pass, an abstract must exist, the paper must pass cutoff checks, and duplicates collapse by S2 `paperId`.

Semantic Scholar is optional, not a hard dependency. If the goal is to finish a local draft even when live verification is rate-limited or unavailable, opt in explicitly:

```bash
--verify-mode live --verify-error-policy skip --verify-fallback-mode mock
```

Runs that use mock fallback are useful for drafting and QA, but they must not be treated as live citation-fidelity evidence.

### Curated prior-work seeds

Semantic Scholar is not the only way to ground the literature lane. If Codex web research, a human reviewer, or an existing BibTeX file has already produced a curated source list, import it directly:

```bash
paperorchestra research-prior-work --provider mock --output prior_work_seed.json --import
paperorchestra import-prior-work --seed-file prior_work.json --source codex_web_seed
paperorchestra import-prior-work --seed-file references.bib --source manual_bibtex
paperorchestra import-prior-work --seed-file prior_work.md --source manual_seed
```

Supported seed formats:

- JSON list, or an object with `references`, `papers`, `prior_work`, or `entries`
- BibTeX entries with `title`, `author`, `year`, `journal`/`booktitle`, `doi`, and `url` fields
- simple Markdown bullet lists, including `[Title](https://example.com/source) — 2024` style entries

The import writes `candidate_papers.json`, `citation_registry.json`, `citation_map.json`, and `references.bib`. Imported entries are marked with provenance such as `codex_web_seed` or `manual_seed`; they are curated metadata, not live Semantic Scholar verification unless separately checked.

---

## Fast paths

### 1. Safe paper-derived smoke

This uses an operator-supplied copy of the PaperOrchestra reference PDF, extracts paper-derived materials, and runs a safe mock/compatibility path.

Before running this, download or otherwise provide a **local legal copy** of the PaperOrchestra reference PDF and point `PAPERO_REFERENCE_PDF` at it.

```bash
PAPERO_REFERENCE_PDF=/absolute/path/to/PaperOrchestra-reference.pdf \
  ./scripts/smoke-paperorchestra-reference.sh
```

Expected result:

- `draft_complete`
- benchmark/eval artifacts
- generated LaTeX draft

### 2. Live paper-derived smoke

```bash
PAPERO_REFERENCE_PDF=/absolute/path/to/PaperOrchestra-reference.pdf \
  PAPERO_SMOKE_LIVE=1 ./scripts/smoke-paperorchestra-reference.sh
```

This enables:

- shell provider
- `omx_native`
- search-grounded live mode

### 3. Live + compile smoke

```bash
PAPERO_REFERENCE_PDF=/absolute/path/to/PaperOrchestra-reference.pdf \
  PAPERO_SMOKE_LIVE=1 PAPERO_SMOKE_COMPILE=1 ./scripts/smoke-paperorchestra-reference.sh
```

Expected on a healthy environment:

- `complete`
- clean compiled PDF
- runtime/fidelity proof artifacts

---


## Start here: paper teacher workflow

If you already have a manuscript and artifact repository, start with `teach` instead of manually assembling `idea.md` and `experimental_log.md`:

```bash
paperorchestra teach \
  --paper examples/minimal/template.tex \
  --artifact-repo examples/minimal \
  --figures-dir examples/minimal/figures

# Option A: ask the model to draft a prior-work seed from the manuscript/artifacts.
paperorchestra research-prior-work \
  --provider mock \
  --output prior_work_seed.json \
  --import

# Option B: seed the citation lane from curated references instead of waiting for Semantic Scholar.
paperorchestra import-prior-work \
  --seed-file prior_work.json \
  --source manual_bibtex

paperorchestra run \
  --provider mock \
  --verify-mode mock \
  --runtime-mode compatibility \
  --compile \
  --full-fidelity
```

Need a reminder from the CLI?

```bash
paperorchestra quickstart --scenario testset
paperorchestra quickstart --scenario curated-prior-work
```

For a self-contained regression/demo using the bundled minimal fixture, run:

```bash
scripts/demo-mock.sh
```

For manual container QA, keep the outputs in the checkout and export the main
files to a single directory:

```bash
scripts/demo-mock.sh --in-repo
cd .paper-orchestra/manual-demo
paperorchestra status --summary
paperorchestra export-artifacts --output "$OLDPWD/paperorchestra-output"
```

By default this uses the mock provider and compatibility runtime so it can run without external model/search credentials. Set `PAPERO_TESTSET_SMOKE_PROVIDER=shell` and related timeout/model environment variables when you want to exercise live Codex/OMX surfaces.

For private material QA without copying under the public checkout, pass both
`--material-root /path/to/materials` and `--expected-material-root
/path/to/materials` to `scripts/fresh-full-live-smoke-loop.sh`; the hash
manifest is still validated, but the public repository stays clean.

After a review is produced, convert review feedback into prioritized, section-targeted patch planning:

```bash
paperorchestra suggest-revisions \
  --source-paper examples/minimal/template.tex \
  --review .paper-orchestra/runs/<session-id>/reviews/review.latest.json \
  --output revision_suggestions.json
```

The suggestion artifact groups actions by target section, assigns priority/severity, records which review field produced each action, and includes done criteria. It is a planning artifact; apply patches manually or in a later editing lane.
Each suggested action now also includes a `suggested_patch_hunk` with an anchor and patch-style template so the next editing pass has a concrete starting point instead of only a TODO sentence.

For deeper critic coverage, use the one-shot critic stack:

```bash
paperorchestra critique \
  --source-paper examples/minimal/template.tex \
  --provider mock
```

This runs the paper-level reviewer, section-level critic, citation-support critic, and revision suggestion builder. To run the pieces manually:

```bash
paperorchestra review-sections --output section_review.json
paperorchestra review-citations --output citation_support_review.json
paperorchestra review-citations --evidence-mode web --output citation_support_review.json
paperorchestra suggest-revisions \
  --source-paper examples/minimal/template.tex \
  --review .paper-orchestra/runs/<session-id>/reviews/review.latest.json \
  --section-review section_review.json \
  --citation-review citation_support_review.json \
  --output revision_suggestions.json
```

`review-sections` scores each section for substance, citation density, quantitative grounding, and TODO markers. `review-citations` inspects cited claim sentences and flags unknown, weakly supported, metadata-only, insufficient-evidence, or manually-check-needed citation uses. Its default `--evidence-mode heuristic` is offline and conservative: title/metadata overlap is recorded as `metadata_only`, not claim-safe support. Use `--evidence-mode model` with a configured provider, or `--evidence-mode web` to use a web-search-capable provider. If neither `PAPERO_MODEL_CMD` nor `--provider-command` is set, `--evidence-mode web` uses a Codex shell command with `codex --search exec`.

Use `paperorchestra audit-reproducibility` after a run when you need a single verdict about mock/fallback/prompt-trace signals instead of manually reading multiple artifacts. Add `--require-live-verification` when a claim-safe run must fail if no live citation verification was actually invoked.

If you want to keep most of a manuscript stable and only rewrite a subset of sections, `write-sections` now supports section-scoped regeneration and an explicit output path:

```bash
paperorchestra write-sections \
  --provider mock \
  --only-sections Method,Experiments \
  --output-tex revised-paper.tex
```

---

## A-Z CLI usage

Use tutorials for command-heavy walkthroughs:

- first setup: [`docs/tutorials/start.md`](docs/tutorials/start.md)
- safe mock/demo: [`docs/tutorials/mock-demo.md`](docs/tutorials/mock-demo.md)
- Docker QA and export: [`docs/tutorials/docker-container-qa.md`](docs/tutorials/docker-container-qa.md)
- rendered PDF human QA: [`docs/tutorials/rendered-pdf-human-qa.md`](docs/tutorials/rendered-pdf-human-qa.md)
- claim-safe loop: [`docs/tutorials/claim-safe-quality-loop.md`](docs/tutorials/claim-safe-quality-loop.md)

Minimum manual session shape:

```bash
paperorchestra init   --idea ./idea.md   --experimental-log ./experimental_log.md   --template ./template.tex   --guidelines ./conference_guidelines.md

paperorchestra run --provider mock --verify-mode mock --runtime-mode compatibility
paperorchestra status --summary
paperorchestra export-artifacts --output ./paperorchestra-output
```

`paperorchestra run` is draft generation, not full quality approval. For existing manuscripts, start with `paperorchestra teach`; for ambiguous inputs, use the guided intake commands (`intake-start`, `intake-answer`, `intake-review`, `intake-research`, `intake-finalize`, `intake-approve`).

## Validation and review honesty

The validator is intentionally useful but not magical. Treat these checks as **syntactic/contract checks** unless an explicit LLM-judge or human review artifact says otherwise.

Plain-English quality model:

- Generation statuses (`draft_complete`, `complete`) describe artifact
  availability, not publication readiness.
- Claim-safe mode is a conservative gate/posture. It can block, ask for
  `human_needed`, or reach `ready_for_human_finalization`; none of those states
  means “submit without human authorship.”
- Citation gates now check more than “does this BibTeX key exist?”: the system
  plans citation intent, reviews cited-sentence support when web evidence is
  available, audits the references visible in the rendered manuscript/PDF, and
  fails closed when citation evidence artifacts are missing, stale, skipped, or
  unbound.
- Mock, fallback, and full-fidelity workflow artifacts are audit evidence about
  what the pipeline did. They are not automatic proof that every claim is true
  or every citation is semantically appropriate.
- Ralph/OMX handoff is the persistence owner for long claim-safe repair loops;
  Critic artifacts are review packets/gates, not a replacement for final human
  review.

For the full state-machine contract, read
[`docs/quality-gate-state-machine.md`](docs/quality-gate-state-machine.md).

- Citation coverage checks ensure cited keys are known and enough discovered references are used; they do not prove that every citation semantically supports every sentence.
- `verify-papers --mode live` proves at most citation metadata lookup; it does not prove cited-sentence support. For cited-sentence support, inspect `citation_support_review.json` from `paperorchestra review-citations`, preferably with `--evidence-mode web` for claim-safe review loops.
- `review-citations --evidence-mode web` uses a web-search-capable Codex shell provider (`codex --search exec ...`). If the active writing provider is plain `codex exec`, PaperOrchestra switches the citation-support critic to the Codex search default unless an explicit `--provider-command` is supplied.
- Fidelity/reproducibility audits now treat empty `citation_registry.json` / `citation_map.json` as degraded citation-lane output even if the files exist. Do not trust a run whose citation artifacts are empty or malformed.
- Numeric grounding checks are regex/token checks against the experimental log; they catch obvious hallucinated numbers but do not verify scientific meaning.
- Comparative-claim checks are warning-oriented surface checks; they do not replace human review of claims like "outperforms" or "state of the art".
- Refinement uses the paper-style non-regression gate plus a documented small-drop reviewer retry heuristic. If a candidate score drops by at most 1.0, the system may ask for a second review before final rejection/acceptance to reduce judge noise.
- `PAPERO_PROVIDER_SEED`, `PAPERO_PROVIDER_TEMPERATURE`, and `PAPERO_PROVIDER_MAX_OUTPUT_TOKENS` are passthrough knobs for shell-provider subprocesses only. PaperOrchestra forwards them, but the downstream model command must choose to honor them.
- Reproducibility here means **auditability**: inputs, prompt traces, provider identity, runtime mode, validation results, and artifact health are recorded. It does **not** mean the LLM will produce byte-identical prose on rerun.
- Set `PAPERO_STRICT_CONTENT_GATES=1` for claim-safe/review-ready runs. This keeps draft artifacts available, but promotes unsupported comparative claims, prompt/meta leakage, and severe figure-placement warnings such as `tail_clump` to hard-gate failures. Prompt/meta leakage is checked beyond `paper.full.tex`: generated plot snippets and extracted compiled-PDF text are also scanned when available.
- For strict reproducibility claims, combine `--strict-omx-native`, `--full-fidelity`, `audit-fidelity`, and manual inspection of `runtime-parity.json`, `validation.*.json`, and review artifacts.
- Use `paperorchestra quality-eval --quality-mode claim_safe` to write a diagnostic `quality-eval.json` before asking Ralph to continue. It records the 5-tier status: Tier 0 preconditions, Tier 1 structural integrity, Tier 2 claim safety, Tier 3 advisory scholarly scorecard, and Tier 4 human-only finalization. If an upstream tier fails, downstream automated tiers are marked `skipped_due_to_upstream_fail` instead of producing misleading scores. By default this diagnostic does **not** consume QA-loop history/budget; add `--record-history` only when you intentionally want a diagnostic-only entry in `.paper-orchestra/qa-loop-history.jsonl`.
- Before claim-safe `quality-eval`, refresh the citation evidence surfaces with `paperorchestra audit-rendered-references --quality-mode claim_safe`, `paperorchestra audit-citation-integrity --quality-mode claim_safe`, and `paperorchestra audit-citation-integrity-critic --quality-mode claim_safe`. These commands write session-default `rendered_reference_audit.json`, `citation_intent_plan.json`, `citation_source_match.json`, `citation_integrity.audit.json`, and `citation_integrity.critic.json`; the critic packet is deterministic and fails closed when any reviewed citation evidence artifact is missing, skipped, stale, unbound, or failed.
- Use `paperorchestra qa-loop-plan --quality-mode claim_safe` when an automated loop such as Ralph needs the next repair target. It consumes the tiered evaluation and writes `qa-loop.plan.json` with `continue` / `human_needed` / `ready_for_human_finalization` / `failed` plus suggested repair commands. Pass `--quality-eval path/to/quality-eval.json` to make the prescription consume a previously reviewed diagnostic snapshot instead of regenerating it. Plan/brief/dry-run history is audit evidence and does **not** consume the repair-attempt budget; only bounded `qa-loop-step` attempts do. There is intentionally no `success` verdict: the best automated state is “ready for a human to finalize.”
- Use `paperorchestra quality-gate` when you want a single strict pass/block surface for draft quality. It writes `quality-gate.report.json`, regenerates `quality-eval.json` and `qa-loop.plan.json`, and summarizes six dimensions: narrative logic, citation/claim safety, reproducibility/provenance, LaTeX/structure, reviewer acceptability, and human-owned finalization. The command exits non-zero when the gate blocks unless `--no-fail-on-block` is supplied. `--profile mock` is intentionally loose for mock demos: structural/non-reviewable issues still block, while claim/reviewer/provenance issues warn. `--profile claim_safe --quality-mode claim_safe --require-live-verification` is strict: any failed/skipped/warned Tier 0-3 dimension blocks until repaired or explicitly accepted where supported. Add `--auto-refine --refine-iterations 1` to attempt one bounded refinement pass before the report is finalized.
- Use `paperorchestra qa-loop-step --quality-mode claim_safe --max-iterations 5 --provider shell --runtime-mode omx_native --require-compile --citation-evidence-mode web` for one bounded repair iteration. It is intentionally one-step: PaperOrchestra records the candidate repair, validation, compile, citation-support review, refreshed quality eval, refreshed plan, `qa-loop-execution.iter-N.json`, and a budget-consuming `qa_loop_step` history entry, but it does not implement its own persistent multi-agent scheduler. When a semi-auto repair candidate is rejected or left uncommitted, canonical current-manuscript artifacts are restored/regenerated so later quality evaluations do not accidentally point at the candidate draft. A terminal `human_needed`, `failed`, or `ready_for_human_finalization` plan is a no-op for `qa-loop-step`; Ralph/HITL must explicitly decide any later continuation.
- Generated plot assets are draft placeholders unless replaced by human-authored final figures. Placeholder figures force a non-reviewable failed verdict (`final_figure_assets_non_reviewable`) rather than allowing a review packet to be treated as final paper evidence.
- Use `paperorchestra qa-loop-brief --quality-mode claim_safe --max-iterations 5` and then `paperorchestra ralph-start --dry-run --max-iterations 5` when you want real persistence. The dry run writes a Ralph brief, bootstraps the `.omx/prd.json` expected by the OMX Ralph CLI, and prints the `omx ralph --prd ...` handoff without consuming repair budget. `paperorchestra ralph-start --launch` is explicit opt-in because it starts an OMX Ralph/Codex process that may consume significant tokens/time.
- `unsupported_comparative_claim`, numeric-grounding changes, and figure-placement rewrites are `semi_auto`: the writer may propose candidate edits, but a citation/claim/figure critic or human must approve before committing substantive content changes. Writer-facing repair actions do not expose reviewer numeric scores.
- Each quality-loop plan appends `.paper-orchestra/qa-loop-history.jsonl` so Ralph can detect repeated hard-gate failures, regression, and simple oscillation instead of looping forever.
- Use `paperorchestra validate-current` to refresh validation metadata for the current `paper.full.tex` without asking the writer to rewrite the manuscript.
- `paperorchestra run` alone is **draft generation, not a full quality-gated smoke**. A full quality gate must run the strict critic stack: `validate-current`, `build-source-obligations`, `compile`, `review`, `review-sections`, `review-figure-placement`, `review-citations --evidence-mode web`, `audit-rendered-references --quality-mode claim_safe`, `audit-citation-integrity --quality-mode claim_safe`, `audit-citation-integrity-critic --quality-mode claim_safe`, `quality-eval --quality-mode claim_safe --require-live-verification`, `qa-loop-plan`, and a bounded `qa-loop-step` under OMX-native strict mode. Use `scripts/live-smoke-claim-safe.sh` or `scripts/fresh-full-live-smoke-loop.sh` to record command/stdout/stderr/exit-code evidence and the final verdict.
- Claim-safe Tier 3 now treats reviewer artifacts as evidence, not mere scores: review JSON must be current, schema-valid, six-axis, justified, provenance-backed, and either independently reviewed or explicitly accepted by a hash-bound human/operator artifact before `ready_for_human_finalization` is possible.
- Source-material fidelity is obligation-based in claim-safe runs. Build `source_obligations.json` with `paperorchestra build-source-obligations`; stale/missing obligations, unsatisfied method/proof/benchmark/limitation anchors, and high-risk uncited claims route to `human_needed` or repair rather than readiness.

---

## Background runs

Start:

```bash
paperorchestra job-start-run \
  --provider mock \
  --verify-mode mock \
  --runtime-mode compatibility \
  --discovery-mode model \
  --refine-iterations 1
```

Check:

```bash
paperorchestra job-status --job-id <job-id>
paperorchestra run-status --job-id <job-id>      # alias
```

Tail logs:

```bash
paperorchestra job-tail-log --job-id <job-id>
paperorchestra run-tail-log --job-id <job-id>   # alias
```

Cancel:

```bash
paperorchestra job-cancel --job-id <job-id>
```

---

## Individual stage commands

```bash
paperorchestra outline --provider shell
paperorchestra generate-plots --provider shell
paperorchestra discover-papers --mode search-grounded
# Or import curated sources produced by Codex web research/manual review:
paperorchestra import-prior-work --seed-file prior_work.json --source codex_web_seed
paperorchestra verify-papers --mode live --on-error skip
paperorchestra build-bib
paperorchestra write-intro-related --provider shell
paperorchestra write-sections --provider shell
paperorchestra compile
paperorchestra review --provider shell
paperorchestra refine --provider shell --iterations 1 --require-compile-for-accept
```

---

## Benchmark / eval commands

Build a reference case:

```bash
paperorchestra build-reference-benchmark-case \
  --reference-dir reference-materials \
  --output reference-materials/benchmark_case.json
```

Compare a session against it:

```bash
paperorchestra build-session-eval-summary
paperorchestra build-review-gate-comparison
paperorchestra build-generated-citation-titles
paperorchestra compare-reference-case --reference-case reference-materials/benchmark_case.json
paperorchestra build-reference-case-partition-scaffold --reference-case reference-materials/benchmark_case.json
paperorchestra compare-reference-case-citation-coverage --reference-case reference-materials/benchmark_case.json
```

Citation partition prompt/eval helpers:

```bash
paperorchestra build-citation-partition-request \
  --paper-text-file paper.txt \
  --references-json references.json

paperorchestra compare-partitioned-citation-coverage \
  --references-json references.json \
  --partition-json partition.json \
  --generated-titles-json generated_citation_titles.json
```

---


## MCP server

`python -m pip install -e .` inside your repo `.venv` installs the `paperorchestra-mcp` binary, but it does **not** automatically register that server with Codex, Claude, or any other MCP client.

Recommended path:

```bash
./scripts/register-codex-mcp.sh --use-local-venv --dry-run
./scripts/register-codex-mcp.sh --use-local-venv
scripts/smoke-paperorchestra-mcp.py --transport newline --json
```

Then restart the MCP client/session. `codex mcp list` proves config registration; `scripts/smoke-codex-mcp-attach.sh` or visible `mcp__paperorchestra__...` tools prove active attachment. If attachment is absent but raw smoke passes, use the CLI fallback from [`docs/tutorials/start.md`](docs/tutorials/start.md) and report a client/session attachment issue.

For current setup commands and stale CLI checks, use [`docs/tutorials/start.md`](docs/tutorials/start.md). For environment details, run `paperorchestra environment --summary` and read [`ENVIRONMENT.md`](ENVIRONMENT.md).

## Skill installation

`python -m pip install -e .` does not install Codex local skills. Install the repo
skill explicitly after cloning:

```bash
./scripts/install-skill.sh
test -f ~/.codex/skills/paperorchestra/SKILL.md
```

Equivalent manual install:

```bash
mkdir -p ~/.codex/skills/paperorchestra
cp skills/paperorchestra/SKILL.md ~/.codex/skills/paperorchestra/SKILL.md
```

Then restart or refresh the Codex environment that supports local skills and use the
`paperorchestra` skill for MCP-first operation. The skill expects the package and,
preferably, the `paperorchestra-mcp` server to be installed/configured.

### OMX / oh-my-codex note

OMX-native execution requires an existing oh-my-codex installation. Install and
configure `omx` outside this repo, then run:

```bash
omx doctor
omx status
```

PaperOrchestra's OMX-facing commands and MCP tools assume those checks already pass.
If they do not, use `--runtime-mode compatibility` or `--provider mock` until the
external OMX/Codex runtime is healthy.

Additional public-safe OMX diagnostics and handoff surfaces:

```bash
# Bounded probes for omx/codex/explore/ralph/state/trace/sparkshell/team.
paperorchestra doctor --omx-deep

# Export sanitized OMX state/trace summaries; raw trace timelines and prompt
# previews are intentionally not copied.
paperorchestra export-omx-evidence --output ./paperorchestra-omx-evidence

# Write a manual Critic/team/ultrawork review handoff without auto-launching
# long-running OMX workflows.
paperorchestra omx-review-handoff
```

The integration contract is intentionally conservative:

| OMX surface | PaperOrchestra behavior |
| --- | --- |
| Ralph | Claim-safe handoff artifacts require Ralph ownership. |
| Critic | Citation integrity uses hash-bound `citation_integrity.critic.json`; native session tool attachment is not assumed. |
| Trace | `export-omx-evidence` writes summary/count metadata only, not raw prompt previews. |
| State | State/status export is non-secret summary data and degrades explicitly if unavailable. |
| sparkshell | Long-smoke commands are emitted as handoff text, never auto-launched. |
| `doctor --omx-deep` | Runs bounded local probes without private credentials/model calls. |
| Team/Ultrawork | Multi-review is a manual handoff; PaperOrchestra does not auto-spawn unbounded workers. |

---

## Runtime artifacts

Per session:

```text
.paper-orchestra/current_session.txt
.paper-orchestra/runs/<session-id>/session.json
.paper-orchestra/runs/<session-id>/inputs/*
.paper-orchestra/runs/<session-id>/artifacts/*
.paper-orchestra/runs/<session-id>/build/*
.paper-orchestra/runs/<session-id>/reviews/*
```

Important artifacts:

- `outline.json`
- `plot_manifest.json`
- `plot_captions.json`
- `candidate_papers.json`
- `citation_registry.json`
- `citation_map.json`
- `references.bib`
- `introduction_related_work.tex`
- `paper.full.tex`
- `compiled/paper.full.pdf`
- `validation.*.json`
- `review.latest.json`
- `compile-environment.json`
- `compile-report.json`
- `runtime-parity.json`
- `fidelity.audit.json`

---

## Understanding statuses

- `draft_complete`: LaTeX manuscript exists, but there is no clean compiled PDF yet.
- `complete`: manuscript and clean compiled PDF exist.
- `blocked`: refinement or validation rejected the candidate and no acceptable path completed.

---

## Troubleshooting

### `doctor` reports warning

Read the `checks` and `session_recovery` blocks. A missing `SEMANTIC_SCHOLAR_API_KEY` is acceptable for mock/offline demos, but it is a real risk for `--verify-mode live` because Semantic Scholar can rate-limit unauthenticated traffic.

`doctor` and `status` also include next-command hints for partial sessions, for example a run that stopped after `candidate_papers.json` but before `citation_registry.json`.

### OMX-native fallback warning

If you see a warning like:

```text
WARNING: stage ... fell back to Python provider after OMX-native failure: ...
```

then that stage did not complete via OMX-native execution. Inspect lane manifests and `.paper-orchestra/tmp/omx-*` artifacts. For CI or fidelity-sensitive runs, rerun with `--strict-omx-native` so the first fallback fails the run instead of producing a mixed OMX/Python session.

### `bwrap` is installed but PDF compile still fails in a container

Some Docker/CI environments install `bubblewrap` but block unprivileged user
namespace creation. In that case `paperorchestra check-compile-env` should mark
`bwrap` unusable and either select another sandbox or explain why no sandbox is
ready. Install `firejail`/`nsjail`, or provide a custom wrapper:

```bash
sudo apt-get install -y firejail
export PAPERO_TEX_SANDBOX_CMD='["/absolute/path/to/tex-sandbox.sh"]'
```

### Semantic Scholar rate limits or bad-looking search results

Use an API key and keep it local:

```bash
cat >> .env <<'EOF'
SEMANTIC_SCHOLAR_API_KEY='<key>'
EOF
chmod 600 .env
set -a && source .env && set +a
```

S2 has a strict throughput profile. PaperOrchestra's wrapper intentionally sends one request per second and retries 429/5xx/network/timeout failures according to a bounded policy. If live verification still fails, inspect `verification_errors.json`.

Do not judge S2 by broad topic search quality. S2 is used as a candidate verifier/resolver, not as the primary literature-discovery brain. Codex/web search or human hints should find candidate titles first; S2 then verifies entity metadata.

For demos, use mock verification explicitly:

```bash
--verify-mode mock
```

By default, live verification skips individual failed candidates and writes `verification_errors.json`; if every candidate fails, the session is marked `blocked` with recovery hints. Use `--on-error fail` / `--verify-error-policy fail` for fail-fast behavior.

### Compile blocked

Check:

```bash
paperorchestra check-compile-env
cat .paper-orchestra/runs/<session-id>/artifacts/compile-report.json
```

Make sure:

```bash
export PAPERO_ALLOW_TEX_COMPILE=1
```

### Temporary OMX files are piling up

```bash
paperorchestra cleanup-tmp
```

---

## Maintainer map

Key modules:

- `paperorchestra/pipeline.py` — stage orchestration and validation gates
- `paperorchestra/prompts.py` — prompt asset loading/binding
- `paperorchestra/prompt_assets/` — Appendix-F-derived prompt assets and autorater prompts
- `paperorchestra/literature.py` — Semantic Scholar/OpenAlex/search-grounded substitute logic
- `paperorchestra/validator.py` — manuscript contract validation
- `paperorchestra/eval.py` — benchmark/eval/proof artifacts
- `paperorchestra/fidelity.py` — reconstruction fidelity audit
- `paperorchestra/runtime_parity.py` — OMX lane/parity reporting
- `paperorchestra/compile_env.py` / `paperorchestra/latex.py` — sandboxed compile path
- `paperorchestra/mcp_server.py` — stdio MCP server
- `paperorchestra/cli.py` — operator CLI

---

## Provenance and rights notice

This repository is an independent reconstruction based on the public PaperOrchestra paper and the work present in this repo.

Important:

- this repository does **not** contain the original authors' private or unpublished implementation
- rights to the original paper, project name, branding, and any third-party material remain with their respective owners
- this repository's MIT license applies to this reconstruction code only
- if a rightsholder asks for correction or removal, the request should be reviewed promptly

See `NOTICE.md` and `LICENSE`.
