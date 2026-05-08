#!/usr/bin/env bash
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="${PAPERO_FRESH_QA_LOG_DIR:-$ROOT/.paper-orchestra/fresh-qa}"
WORKDIR="${PAPERO_FRESH_QA_WORKDIR:-$LOG_DIR/workdir}"
RUN_MOCK=1
RUN_TESTS=1
RUN_COMPILE=auto

usage() {
  cat <<'USAGE'
Usage: scripts/fresh-qa.sh [options]

Runs the fresh-clone developer QA path:
  - create/reuse .venv
  - editable install with dev extras
  - CLI help, doctor, environment, compile-env checks
  - bundled minimal mock pipeline
  - fidelity/eval artifact smoke
  - compile if the machine is ready
  - pytest

Options:
  --skip-mock        Skip the bundled minimal mock pipeline.
  --skip-tests       Skip pytest.
  --skip-compile     Never run paperorchestra compile.
  --compile-if-ready Run compile when check-compile-env reports ready (default).
  --help             Show this help.

Environment:
  PAPERO_FRESH_QA_LOG_DIR   Output directory for logs and summary JSON.
  PAPERO_FRESH_QA_WORKDIR   Working directory for the mock session.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-mock) RUN_MOCK=0 ;;
    --skip-tests) RUN_TESTS=0 ;;
    --skip-compile) RUN_COMPILE=0 ;;
    --compile-if-ready) RUN_COMPILE=auto ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

mkdir -p "$LOG_DIR"

declare -A STATUS

run_step() {
  local key="$1"
  shift
  local log="$LOG_DIR/$key.log"
  echo "[fresh-qa] $key: $*" >&2
  "$@" >"$log" 2>&1
  local rc=$?
  if [[ $rc -eq 0 ]]; then
    STATUS["$key"]="ok"
    echo "[fresh-qa] $key: ok" >&2
  else
    STATUS["$key"]="failed:$rc"
    echo "[fresh-qa] $key: failed:$rc (see $log)" >&2
  fi
  return "$rc"
}

run_in_workdir() {
  local key="$1"
  shift
  local log="$LOG_DIR/$key.log"
  echo "[fresh-qa] $key: (cd $WORKDIR && $*)" >&2
  (cd "$WORKDIR" && "$@") >"$log" 2>&1
  local rc=$?
  if [[ $rc -eq 0 ]]; then
    STATUS["$key"]="ok"
    echo "[fresh-qa] $key: ok" >&2
  else
    STATUS["$key"]="failed:$rc"
    echo "[fresh-qa] $key: failed:$rc (see $log)" >&2
  fi
  return "$rc"
}

cd "$ROOT"

run_step venv python3 -m venv .venv || true
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"
run_step install python -m pip install -e ".[dev]" || true
run_step cli_help paperorchestra --help || true
run_step doctor paperorchestra doctor || true
cp "$LOG_DIR/doctor.log" "$LOG_DIR/doctor.json" 2>/dev/null || true
run_step environment paperorchestra environment || true
cp "$LOG_DIR/environment.log" "$LOG_DIR/environment.json" 2>/dev/null || true
run_step compile_env paperorchestra check-compile-env || true
cp "$LOG_DIR/compile_env.log" "$LOG_DIR/compile_env.json" 2>/dev/null || true

if [[ "$RUN_MOCK" == "1" ]]; then
  rm -rf "$WORKDIR"
  mkdir -p "$WORKDIR"
  run_in_workdir init_minimal paperorchestra init \
    --idea "$ROOT/examples/minimal/idea.md" \
    --experimental-log "$ROOT/examples/minimal/experimental_log.md" \
    --template "$ROOT/examples/minimal/template.tex" \
    --guidelines "$ROOT/examples/minimal/conference_guidelines.md" \
    --figures-dir "$ROOT/examples/minimal/figures" \
    --cutoff-date 2024-11-01 \
    --allow-outside-workspace || true
  run_in_workdir mock_pipeline paperorchestra run \
    --provider mock \
    --verify-mode mock \
    --runtime-mode compatibility \
    --discovery-mode model \
    --refine-iterations 1 || true
  run_in_workdir audit_fidelity paperorchestra audit-fidelity || true
  run_in_workdir session_eval paperorchestra build-session-eval-summary || true
  run_in_workdir review_gate_comparison paperorchestra build-review-gate-comparison || true
  run_in_workdir generated_citation_titles paperorchestra build-generated-citation-titles || true

  if [[ "$RUN_COMPILE" == "auto" ]]; then
    COMPILE_READY="$(
      python - "$LOG_DIR/compile_env.json" <<'PY'
import json
import sys
try:
    payload = json.loads(open(sys.argv[1], encoding="utf-8").read())
    print("1" if payload.get("report", {}).get("ready_for_compile") else "0")
except Exception:
    print("0")
PY
    )"
    if [[ "$COMPILE_READY" == "1" ]]; then
      PAPERO_ALLOW_TEX_COMPILE=1 run_in_workdir compile paperorchestra compile || true
    else
      STATUS["compile"]="skipped:not-ready"
      echo "[fresh-qa] compile: skipped:not-ready" >&2
    fi
  else
    STATUS["compile"]="skipped:disabled"
    echo "[fresh-qa] compile: skipped:disabled" >&2
  fi
else
  STATUS["mock_pipeline"]="skipped:disabled"
  STATUS["compile"]="skipped:mock-disabled"
fi

if [[ "$RUN_TESTS" == "1" ]]; then
  run_step tests python -m pytest -q || true
else
  STATUS["tests"]="skipped:disabled"
fi

SUMMARY_PATH="$LOG_DIR/summary.json"
export SUMMARY_PATH LOG_DIR WORKDIR RUN_MOCK RUN_TESTS RUN_COMPILE
for key in "${!STATUS[@]}"; do
  export "PAPERO_FRESH_QA_STATUS_$key=${STATUS[$key]}"
done

python - <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path

summary_path = Path(os.environ["SUMMARY_PATH"])
log_dir = Path(os.environ["LOG_DIR"])
statuses = {
    key.removeprefix("PAPERO_FRESH_QA_STATUS_"): value
    for key, value in os.environ.items()
    if key.startswith("PAPERO_FRESH_QA_STATUS_")
}

def read_json(name: str) -> dict:
    path = log_dir / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

doctor = read_json("doctor.json")
compile_env = read_json("compile_env.json")
raw_readiness = doctor.get("readiness_profiles", {})
if isinstance(raw_readiness, list):
    readiness = {
        item.get("name", f"profile_{index}"): item
        for index, item in enumerate(raw_readiness)
        if isinstance(item, dict)
    }
elif isinstance(raw_readiness, dict):
    readiness = raw_readiness
else:
    readiness = {}
report = compile_env.get("report", {})
summary = {
    "status": "ok" if all(value.startswith(("ok", "skipped")) for value in statuses.values()) else "failed",
    "steps": dict(sorted(statuses.items())),
    "readiness": {
        key: value.get("ready") if isinstance(value, dict) else value
        for key, value in readiness.items()
    },
    "compile_ready": report.get("ready_for_compile"),
    "selected_sandbox": report.get("sandbox_tool"),
    "remaining": [
        note for note in report.get("notes", [])
        if "missing" in note.lower() or "not available" in note.lower() or "not configured" in note.lower()
    ],
    "workdir": os.environ["WORKDIR"],
    "logs": str(log_dir),
}
summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps(summary, indent=2, ensure_ascii=False))
PY

if python - "$SUMMARY_PATH" <<'PY'
import json
import sys
summary = json.loads(open(sys.argv[1], encoding="utf-8").read())
raise SystemExit(0 if summary["status"] == "ok" else 1)
PY
then
  exit 0
fi
exit 1
