#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKDIR="${PAPERO_SMOKE_WORKDIR:-$(mktemp -d "${TMPDIR:-/tmp}/paperorchestra-reference-smoke.XXXXXX")}" 
PDF_PATH="${PAPERO_REFERENCE_PDF:-}"
if [[ -z "$PDF_PATH" ]]; then
  echo "[reference-smoke] Set PAPERO_REFERENCE_PDF to a local copy of the PaperOrchestra reference PDF." >&2
  exit 1
fi
if [[ ! -f "$PDF_PATH" ]]; then
  echo "[reference-smoke] PAPERO_REFERENCE_PDF does not point to an existing file: $PDF_PATH" >&2
  exit 1
fi
mkdir -p "$WORKDIR/reference-materials"
EXTRACT_JSON="$WORKDIR/reference-materials/extract-summary.json"
LIVE_FLAG="${PAPERO_SMOKE_LIVE:-0}"

python3 "$ROOT/scripts/extract-paperorchestra-reference.py" \
  --pdf "$PDF_PATH" \
  --out-dir "$WORKDIR/reference-materials" > "$EXTRACT_JSON"
cat "$EXTRACT_JSON"

REQUESTED_PROVIDER="${PAPERO_SMOKE_PROVIDER:-}"
REQUESTED_RUNTIME_MODE="${PAPERO_SMOKE_RUNTIME_MODE:-}"
REQUESTED_DISCOVERY_MODE="${PAPERO_SMOKE_DISCOVERY_MODE:-}"
if [[ "$LIVE_FLAG" != "1" ]]; then
  if [[ -n "$REQUESTED_PROVIDER" && "$REQUESTED_PROVIDER" != "mock" ]]; then
    echo "[reference-smoke] Refusing non-mock provider without PAPERO_SMOKE_LIVE=1" >&2
    exit 1
  fi
  if [[ -n "$REQUESTED_RUNTIME_MODE" && "$REQUESTED_RUNTIME_MODE" != "compatibility" ]]; then
    echo "[reference-smoke] Refusing non-compatibility runtime without PAPERO_SMOKE_LIVE=1" >&2
    exit 1
  fi
fi

EFFECTIVE_PROVIDER="${REQUESTED_PROVIDER:-mock}"
EFFECTIVE_RUNTIME_MODE="${REQUESTED_RUNTIME_MODE:-compatibility}"
EFFECTIVE_DISCOVERY_MODE="${REQUESTED_DISCOVERY_MODE:-search-grounded}"
if [[ "$LIVE_FLAG" == "1" ]]; then
  EFFECTIVE_PROVIDER="${REQUESTED_PROVIDER:-shell}"
  EFFECTIVE_RUNTIME_MODE="${REQUESTED_RUNTIME_MODE:-omx_native}"
  EFFECTIVE_DISCOVERY_MODE="${REQUESTED_DISCOVERY_MODE:-search-grounded}"
fi

env \
  PAPERO_SMOKE_WORKDIR="$WORKDIR" \
  PAPERO_SMOKE_RESULTS_MARKDOWN_FILE="$WORKDIR/reference-materials/results.md" \
  PAPERO_SMOKE_SEED_ANSWERS_FILE="$WORKDIR/reference-materials/seed_answers.json" \
  PAPERO_SMOKE_REFERENCE_BENCHMARK_CASE="$WORKDIR/reference-materials/benchmark_case.json" \
  PAPERO_SMOKE_KEEP_WORKDIR="${PAPERO_SMOKE_KEEP_WORKDIR:-1}" \
  PAPERO_SMOKE_PROVIDER="$EFFECTIVE_PROVIDER" \
  PAPERO_SMOKE_RUNTIME_MODE="$EFFECTIVE_RUNTIME_MODE" \
  PAPERO_SMOKE_DISCOVERY_MODE="$EFFECTIVE_DISCOVERY_MODE" \
  PAPERO_SEARCH_GROUNDED_MODE="${PAPERO_SEARCH_GROUNDED_MODE:-$([ "$LIVE_FLAG" == "1" ] && printf live || printf mock)}" \
  PAPERO_SMOKE_REFINE_ITERATIONS="${PAPERO_SMOKE_REFINE_ITERATIONS:-$([ "$LIVE_FLAG" == "1" ] && printf 1 || printf 0)}" \
  PAPERO_SMOKE_RESEARCH_MODE="${PAPERO_SMOKE_RESEARCH_MODE:-mock}" \
  PAPERO_SMOKE_VERIFY_MODE="${PAPERO_SMOKE_VERIFY_MODE:-mock}" \
  PAPERO_SMOKE_TIMEOUT_SECONDS="${PAPERO_SMOKE_TIMEOUT_SECONDS:-900}" \
  PAPERO_SMOKE_PROVIDER_TIMEOUT_SECONDS="${PAPERO_SMOKE_PROVIDER_TIMEOUT_SECONDS:-600}" \
  PAPERO_SMOKE_OMX_EXEC_TIMEOUT_SECONDS="${PAPERO_SMOKE_OMX_EXEC_TIMEOUT_SECONDS:-600}" \
  "$ROOT/scripts/smoke-omx-native.sh"
