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

if command -v paperorchestra >/dev/null 2>&1; then
  PAPERO_CMD=(paperorchestra)
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
