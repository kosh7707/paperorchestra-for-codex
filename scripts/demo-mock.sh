#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKDIR="${PAPERO_DEMO_WORKDIR:-$(mktemp -d "${TMPDIR:-/tmp}/paperorchestra-demo.XXXXXX")}"
KEEP_WORKDIR="${PAPERO_DEMO_KEEP_WORKDIR:-1}"

cleanup() {
  if [[ "$KEEP_WORKDIR" != "1" && -d "$WORKDIR" ]]; then
    rm -rf "$WORKDIR"
  fi
}
trap cleanup EXIT

mkdir -p "$WORKDIR"
cd "$WORKDIR"

# Prefer the freshly cloned repository over any stale globally installed
# `paperorchestra` command. Operators may opt in to a custom command for
# debugging with PAPERO_CMD_OVERRIDE, but the public demo path should exercise
# this checkout's code.
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
if [[ -n "${PAPERO_CMD_OVERRIDE:-}" ]]; then
  # shellcheck disable=SC2206
  PAPERO_CMD=(${PAPERO_CMD_OVERRIDE})
else
  PAPERO_CMD=(python3 -m paperorchestra.cli)
fi

"${PAPERO_CMD[@]}" init \
  --idea "$ROOT/examples/minimal/idea.md" \
  --experimental-log "$ROOT/examples/minimal/experimental_log.md" \
  --template "$ROOT/examples/minimal/template.tex" \
  --guidelines "$ROOT/examples/minimal/conference_guidelines.md" \
  --figures-dir "$ROOT/examples/minimal/figures" \
  --cutoff-date 2024-11-01 \
  --allow-outside-workspace

"${PAPERO_CMD[@]}" run --provider mock --verify-mode mock --runtime-mode compatibility --refine-iterations 1
"${PAPERO_CMD[@]}" audit-fidelity
"${PAPERO_CMD[@]}" status --json
printf '[demo] workdir=%s\n' "$WORKDIR" >&2
