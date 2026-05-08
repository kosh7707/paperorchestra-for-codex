#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKDIR="${PAPERO_DEMO_WORKDIR:-}"
KEEP_WORKDIR="${PAPERO_DEMO_KEEP_WORKDIR:-1}"
VERBOSE="${PAPERO_DEMO_VERBOSE:-0}"
IN_REPO=0

usage() {
  cat >&2 <<'EOF'
usage: scripts/demo-mock.sh [--in-repo] [--workdir DIR] [--verbose]

Runs the safe mock demo. By default outputs go to a temporary directory.
Use --in-repo to keep outputs at .paper-orchestra/manual-demo in this checkout,
or --workdir DIR / PAPERO_DEMO_WORKDIR=DIR to choose an explicit location.
By default the noisy pipeline JSON is captured to demo-mock.log. Use --verbose
or PAPERO_DEMO_VERBOSE=1 to stream the full pipeline output.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --in-repo)
      IN_REPO=1
      shift
      ;;
    --workdir)
      if [[ $# -lt 2 ]]; then
        usage
        exit 2
      fi
      WORKDIR="$2"
      shift 2
      ;;
    --verbose)
      VERBOSE=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

if [[ -z "$WORKDIR" ]]; then
  if [[ "$IN_REPO" == "1" ]]; then
    WORKDIR="$ROOT/.paper-orchestra/manual-demo"
  else
    WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/paperorchestra-demo.XXXXXX")"
  fi
fi

cleanup() {
  if [[ "$KEEP_WORKDIR" != "1" && -d "$WORKDIR" ]]; then
    rm -rf "$WORKDIR"
  fi
}
trap cleanup EXIT

mkdir -p "$WORKDIR"
cd "$WORKDIR"
LOG_PATH="$WORKDIR/demo-mock.log"
: > "$LOG_PATH"

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

run_step() {
  local label="$1"
  shift
  if [[ "$VERBOSE" == "1" ]]; then
    printf '[demo] %s...\n' "$label" >&2
    "$@"
    return
  fi
  printf '[demo] %s...\n' "$label" >&2
  {
    printf '\n### %s\n' "$label"
    printf '$'
    printf ' %q' "$@"
    printf '\n'
  } >> "$LOG_PATH"
  if ! "$@" >> "$LOG_PATH" 2>&1; then
    printf '[demo] %s failed; full log: %s\n' "$label" "$LOG_PATH" >&2
    tail -80 "$LOG_PATH" >&2 || true
    return 1
  fi
}

run_step "initialize session" "${PAPERO_CMD[@]}" init \
  --idea "$ROOT/examples/minimal/idea.md" \
  --experimental-log "$ROOT/examples/minimal/experimental_log.md" \
  --template "$ROOT/examples/minimal/template.tex" \
  --guidelines "$ROOT/examples/minimal/conference_guidelines.md" \
  --figures-dir "$ROOT/examples/minimal/figures" \
  --cutoff-date 2024-11-01 \
  --allow-outside-workspace

run_step "run mock pipeline" "${PAPERO_CMD[@]}" run --provider mock --verify-mode mock --runtime-mode compatibility --refine-iterations 1
run_step "audit fidelity" "${PAPERO_CMD[@]}" audit-fidelity
run_step "record status" "${PAPERO_CMD[@]}" status --json

SESSION_ID="$(cat "$WORKDIR/.paper-orchestra/current_session.txt")"
RUN_DIR="$WORKDIR/.paper-orchestra/runs/$SESSION_ID"
ARTIFACT_DIR="$RUN_DIR/artifacts"
TEX_PATH="$ARTIFACT_DIR/paper.full.tex"
REVIEW_PATH="$RUN_DIR/reviews/review.latest.json"
PDF_PATH="$RUN_DIR/build/compiled/paper.full.pdf"

{
  printf '\n[demo] SUCCESS\n'
  printf '\nSession:\n  %s\n' "$SESSION_ID"
  printf '\nWorkdir:\n  %s\n' "$WORKDIR"
  printf '\nLog:\n  %s\n' "$LOG_PATH"
  printf '\nMain outputs:\n'
  printf '  Manuscript TeX:\n    %s\n' "$TEX_PATH"
  printf '  Artifacts:\n    %s\n' "$ARTIFACT_DIR"
  printf '  Review:\n    %s\n' "$REVIEW_PATH"
  if [[ -f "$PDF_PATH" ]]; then
    printf '  PDF:\n    %s\n' "$PDF_PATH"
  else
    printf '  PDF:\n    not compiled yet\n'
  fi
  printf '\nStatus:\n  draft_complete\n'
  printf '\nWhy reproducibility is BLOCK:\n  mock provider and mock citation verification were used.\n'
  printf '\nNext commands:\n'
  printf '  cd %q\n' "$WORKDIR"
  printf '  paperorchestra status --summary\n'
  printf '  paperorchestra check-compile-env\n'
  printf '  PAPERO_ALLOW_TEX_COMPILE=1 paperorchestra compile\n'
  printf '  paperorchestra export-artifacts --output %q\n' "$ROOT/paperorchestra-output"
  printf '\n[demo] workdir=%s\n' "$WORKDIR"
} >&2
