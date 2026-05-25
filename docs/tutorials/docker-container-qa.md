# Docker container QA

Scope: developer/container QA tutorial for container entry, fresh install, mock demo, export bundle, and compile/PDF dogfood. This is not a claim-safe final smoke and not publication readiness.

## Why this path exists

Minimal containers can make `binary exists != binary usable`. The repo wrapper enters through `scripts/container-entrypoint.sh`, refreshes Codex CLI and OMX, and mounts artifacts at `/artifacts`.

## First container control-plane proof

Run the updater on the first proof:

```bash
scripts/container-run.sh --privileged --with-codex-auth -- \
  omx explore --prompt 'Return exactly OK_CONTAINER_OMX'
```

If this hangs or fails, keep the failure log under `.omx/` or the artifact directory and do not claim the container QA loop complete.

## Fast repeat loop with an isolated venv

The compact command shape is `scripts/container-run.sh --privileged --with-codex-auth --docker-arg -v --docker-arg paperorchestra-qa-venv:/repo/.venv -- ...`.

Use a Docker named volume for `/repo/.venv` so container installs do not corrupt the host venv and so PEP 668 does not block system Python installs:

```bash
scripts/container-run.sh --privileged --with-codex-auth \
  --docker-arg -v \
  --docker-arg paperorchestra-qa-venv:/repo/.venv \
  -- bash -lc 'set -euo pipefail
    export PAPERO_UPDATE_CONTAINER_AI_CLIS=0
    export PAPERO_FRESH_QA_LOG_DIR=/artifacts/fresh-qa-start
    export PAPERO_FRESH_QA_WORKDIR=/artifacts/fresh-qa-start/workdir
    scripts/fresh-qa.sh --skip-tests --skip-compile
  '
```

Use `PAPERO_UPDATE_CONTAINER_AI_CLIS=0` only after an updater-on proof succeeded in the same image/workflow. Re-enable updates before release, final smoke, or any run whose purpose is to prove current Codex/OMX surfaces.

The fresh QA summary should be at:

```text
.paper-orchestra/container-artifacts/fresh-qa-start/summary.json
```

The run should include a fresh install, mock demo, and exportable artifacts. If `summary.json` is not `status: ok`, inspect the step logs before continuing.

## Compile and export bundle

Rendered-PDF QA requires a real PDF. If compile is skipped, install the compile toolchain in the container and compile explicitly:

```bash
scripts/container-run.sh --privileged --with-codex-auth \
  --docker-arg -v \
  --docker-arg paperorchestra-qa-venv:/repo/.venv \
  -- bash -lc 'set -euo pipefail
    apt-get update
    apt-get install -y pkg-config libpng-dev texlive-latex-base texlive-latex-recommended texlive-fonts-recommended latexmk bubblewrap poppler-utils
    cd /artifacts/fresh-qa-start/workdir
    /repo/.venv/bin/python -m paperorchestra.cli check-compile-env
    PAPERO_ALLOW_TEX_COMPILE=1 /repo/.venv/bin/python -m paperorchestra.cli compile
    /repo/.venv/bin/python -m paperorchestra.cli export-artifacts --output /artifacts/fresh-qa-start/export
  '
```

PDF must exist before using [`rendered-pdf-human-qa.md`](rendered-pdf-human-qa.md). If no PDF is produced, record that as the blocker and do not claim the QA loop complete.

Expected export bundle:

```text
.paper-orchestra/container-artifacts/fresh-qa-start/export/paper.full.tex
.paper-orchestra/container-artifacts/fresh-qa-start/export/paper.full.pdf
.paper-orchestra/container-artifacts/fresh-qa-start/export/review.latest.json
.paper-orchestra/container-artifacts/fresh-qa-start/export/session.json
```
