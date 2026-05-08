#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKDIR="${PAPERO_SMOKE_WORKDIR:-$(mktemp -d "${TMPDIR:-/tmp}/paperorchestra-smoke.XXXXXX")}" 
KEEP_WORKDIR="${PAPERO_SMOKE_KEEP_WORKDIR:-1}"
RESEARCH_MODE="${PAPERO_SMOKE_RESEARCH_MODE:-mock}"
VERIFY_MODE="${PAPERO_SMOKE_VERIFY_MODE:-mock}"
RUNTIME_MODE="${PAPERO_SMOKE_RUNTIME_MODE:-omx_native}"
DISCOVERY_MODE="${PAPERO_SMOKE_DISCOVERY_MODE:-model}"
REFINE_ITERATIONS="${PAPERO_SMOKE_REFINE_ITERATIONS:-1}"
TIMEOUT_SECONDS="${PAPERO_SMOKE_TIMEOUT_SECONDS:-900}"
POLL_INTERVAL_SECONDS="${PAPERO_SMOKE_POLL_INTERVAL_SECONDS:-5}"
COMPILE_FLAG="${PAPERO_SMOKE_COMPILE:-0}"
PROVIDER="${PAPERO_SMOKE_PROVIDER:-}"
PROVIDER_TIMEOUT_SECONDS="${PAPERO_SMOKE_PROVIDER_TIMEOUT_SECONDS:-240}"
OMX_EXEC_TIMEOUT_SECONDS="${PAPERO_SMOKE_OMX_EXEC_TIMEOUT_SECONDS:-300}"
SEED_ANSWERS_FILE="${PAPERO_SMOKE_SEED_ANSWERS_FILE:-}"
RESULTS_MARKDOWN_FILE="${PAPERO_SMOKE_RESULTS_MARKDOWN_FILE:-}"
REFERENCE_BENCHMARK_CASE="${PAPERO_SMOKE_REFERENCE_BENCHMARK_CASE:-}"

cleanup() {
  if [[ "$KEEP_WORKDIR" != "1" && -d "$WORKDIR" ]]; then
    rm -rf "$WORKDIR"
  fi
}
trap cleanup EXIT

if [[ -z "$PROVIDER" ]]; then
  if [[ -n "${PAPERO_MODEL_CMD:-}" || -x "$(command -v codex || true)" ]]; then
    PROVIDER="shell"
  else
    PROVIDER="mock"
  fi
fi

if [[ "$PROVIDER" == "shell" && -z "${PAPERO_MODEL_CMD:-}" ]]; then
  if command -v codex >/dev/null 2>&1; then
    export PAPERO_MODEL_CMD='["codex","exec","--skip-git-repo-check","-m","gpt-5.5","-c","model_reasoning_effort=\"low\""]'
  else
    echo "[smoke] shell provider requested but codex/PAPERO_MODEL_CMD unavailable" >&2
    exit 1
  fi
fi
if [[ "$PROVIDER" == "shell" ]]; then
  export PAPERO_PROVIDER_TIMEOUT_SECONDS="$PROVIDER_TIMEOUT_SECONDS"
fi
export PAPERO_OMX_EXEC_TIMEOUT_SECONDS="$OMX_EXEC_TIMEOUT_SECONDS"
if [[ "$COMPILE_FLAG" == "1" && -z "${PAPERO_ALLOW_TEX_COMPILE:-}" ]]; then
  export PAPERO_ALLOW_TEX_COMPILE=1
fi

mkdir -p "$WORKDIR/assets" "$WORKDIR/.omx/state" "$WORKDIR/_smoke"
cp "$ROOT/examples/minimal/template.tex" "$WORKDIR/assets/template.tex"
rm -rf "$WORKDIR/assets/figures"
cp -R "$ROOT/examples/minimal/figures" "$WORKDIR/assets/figures"

if [[ -n "$RESULTS_MARKDOWN_FILE" ]]; then
  cp "$RESULTS_MARKDOWN_FILE" "$WORKDIR/results.md"
else
cat > "$WORKDIR/results.md" <<'MD'
# Smoke Results

We evaluated a staged multi-agent writing pipeline on a synthetic writing benchmark.
The pipeline achieved a literature review quality score of 78.3 and an overall paper quality score of 54.0.
Compared baselines were Single Agent (45.4 / 44.3) and AI Scientist-v2 (43.6 / 43.6).
The staged pipeline improved citation coverage and overall manuscript coherence.
MD
fi

cat > "$WORKDIR/.omx/notepad.md" <<'MD'
# OMX Working Notes

- The benchmark focuses on scientific writing quality rather than model perplexity.
- The strongest observed gain is literature review quality.
- The intended story is that explicit artifacts improve grounding and structure.
MD

if [[ -n "$SEED_ANSWERS_FILE" ]]; then
  cp "$SEED_ANSWERS_FILE" "$WORKDIR/_smoke/seed_answers.json"
else
cat > "$WORKDIR/_smoke/seed_answers.json" <<'JSON'
{
  "problem_statement": "Writing a strong AI paper from loosely structured project materials is difficult because narrative synthesis, citation coverage, and figure planning drift apart.",
  "method_summary": "We use a staged multi-agent workflow with explicit artifacts for intake, outline generation, plot planning, literature review, section drafting, and gated refinement.",
  "key_results": [
    "Literature review quality improved to 78.3 compared with 45.4 for a Single Agent baseline and 43.6 for AI Scientist-v2.",
    "Overall paper quality reached 54.0 compared with 44.3 for a Single Agent baseline and 43.6 for AI Scientist-v2."
  ],
  "baselines": ["Single Agent", "AI Scientist-v2"],
  "figure_story": "Show the staged pipeline, a baseline comparison chart, and a grounding/coherence summary.",
  "target_user_or_setting": "AI-assisted scientific writing workflows",
  "datasets_or_benchmarks": ["Synthetic writing benchmark"],
  "experiments_ran": [
    "Measured literature review quality against baseline systems",
    "Measured overall paper quality against baseline systems"
  ],
  "evidence_paths": ["results.md"],
  "template_path": "assets/template.tex",
  "figures_dir": "assets/figures",
  "venue": "ICLR",
  "page_limit": 8,
  "cutoff_date": "2024-11-01"
}
JSON
fi

run_cli() {
  (
    cd "$WORKDIR"
    PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 -m paperorchestra.cli "$@"
  )
}

json_get() {
  local file="$1"
  local expr="$2"
  python3 - "$file" "$expr" <<'PY'
import json, sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
expr = sys.argv[2]
value = eval(expr, {'payload': payload})
if isinstance(value, (dict, list)):
    print(json.dumps(value, ensure_ascii=False))
else:
    print(value)
PY
}

echo "[smoke] workdir: $WORKDIR"
echo "[smoke] provider=$PROVIDER verify_mode=$VERIFY_MODE research_mode=$RESEARCH_MODE runtime_mode=$RUNTIME_MODE discovery_mode=$DISCOVERY_MODE search_grounded_mode=${PAPERO_SEARCH_GROUNDED_MODE:-unset}"
if [[ "$PROVIDER" == "shell" ]]; then
  python3 -c 'import json, shlex, sys
raw = sys.argv[1]
try:
    parsed = json.loads(raw)
    summary = parsed[0] if isinstance(parsed, list) and parsed else "<configured>"
except json.JSONDecodeError:
    parts = shlex.split(raw)
    summary = parts[0] if parts else "<configured>"
print(f"[smoke] PAPERO_MODEL_CMD(executable-only)={summary}")' "${PAPERO_MODEL_CMD}"
  echo "[smoke] PAPERO_PROVIDER_TIMEOUT_SECONDS=${PAPERO_PROVIDER_TIMEOUT_SECONDS}"
fi
echo "[smoke] PAPERO_OMX_EXEC_TIMEOUT_SECONDS=${PAPERO_OMX_EXEC_TIMEOUT_SECONDS}"

run_cli intake-start --seed-answers "$(cat "$WORKDIR/_smoke/seed_answers.json")" > "$WORKDIR/_smoke/intake-start.json"
run_cli intake-finalize --allow-overwrite > "$WORKDIR/_smoke/intake-finalize.json"
STATUS="$(json_get "$WORKDIR/_smoke/intake-finalize.json" "payload['status']")"
if [[ "$STATUS" != "review_required" ]]; then
  echo "[smoke] expected review_required after finalize, got: $STATUS" >&2
  cat "$WORKDIR/_smoke/intake-finalize.json"
  exit 1
fi

echo "[smoke] review packet created"
run_cli intake-research --mode "$RESEARCH_MODE" > "$WORKDIR/_smoke/intake-research.json"
run_cli intake-review > "$WORKDIR/_smoke/intake-review.json"
STORY_ID="$(json_get "$WORKDIR/_smoke/intake-review.json" "payload['story_candidates'][0]['candidate_id']")"
CLAIM_IDS="$(json_get "$WORKDIR/_smoke/intake-review.json" "','.join(item['candidate_id'] for item in payload['claim_candidates'][:2])")"
run_cli intake-approve --story-candidate-id "$STORY_ID" --claim-candidate-ids "$CLAIM_IDS" --allow-overwrite > "$WORKDIR/_smoke/intake-approve.json"

echo "[smoke] approved story=$STORY_ID claims=$CLAIM_IDS"
JOB_CMD=(job-start-run --provider "$PROVIDER" --verify-mode "$VERIFY_MODE" --runtime-mode "$RUNTIME_MODE" --discovery-mode "$DISCOVERY_MODE" --refine-iterations "$REFINE_ITERATIONS")
if [[ "$COMPILE_FLAG" == "1" ]]; then
  JOB_CMD+=(--compile)
fi
run_cli "${JOB_CMD[@]}" > "$WORKDIR/_smoke/job-start.json"
JOB_ID="$(json_get "$WORKDIR/_smoke/job-start.json" "payload['job_id']")"
echo "[smoke] started job: $JOB_ID"

elapsed=0
while true; do
  run_cli job-status --job-id "$JOB_ID" > "$WORKDIR/_smoke/job-status.json"
  JOB_STATUS="$(json_get "$WORKDIR/_smoke/job-status.json" "payload['status']")"
  SESSION_PHASE="$(json_get "$WORKDIR/_smoke/job-status.json" "payload.get('session_progress', {}).get('current_phase', 'unknown')")"
  ACTIVE_ARTIFACT="$(json_get "$WORKDIR/_smoke/job-status.json" "payload.get('session_progress', {}).get('active_artifact', 'unknown')")"
  echo "[smoke] job status: $JOB_STATUS (${elapsed}s) phase=$SESSION_PHASE artifact=$ACTIVE_ARTIFACT"
  if [[ "$JOB_STATUS" == "succeeded" || "$JOB_STATUS" == "failed" || "$JOB_STATUS" == "cancelled" ]]; then
    break
  fi
  if (( elapsed >= TIMEOUT_SECONDS )); then
    echo "[smoke] timeout waiting for job completion" >&2
    run_cli job-tail-log --job-id "$JOB_ID" > "$WORKDIR/_smoke/job-tail-log.txt" || true
    echo "[smoke] last known job status payload:" >&2
    cat "$WORKDIR/_smoke/job-status.json" >&2 || true
    exit 1
  fi
  sleep "$POLL_INTERVAL_SECONDS"
  elapsed=$((elapsed + POLL_INTERVAL_SECONDS))
done

run_cli job-tail-log --job-id "$JOB_ID" > "$WORKDIR/_smoke/job-tail-log.txt" || true
if [[ "$JOB_STATUS" != "succeeded" ]]; then
  echo "[smoke] job did not succeed; recent log:" >&2
  tail -n 80 "$WORKDIR/_smoke/job-tail-log.txt" >&2 || true
  echo "[smoke] final job status payload:" >&2
  cat "$WORKDIR/_smoke/job-status.json" >&2 || true
  exit 1
fi

run_cli status --json > "$WORKDIR/_smoke/status.json"
run_cli check-compile-env > "$WORKDIR/_smoke/compile-env.json"
run_cli build-session-eval-summary > "$WORKDIR/_smoke/session-eval-summary-path.txt"
run_cli build-review-gate-comparison > "$WORKDIR/_smoke/review-gate-comparison-path.txt"
run_cli build-generated-citation-titles > "$WORKDIR/_smoke/generated-citation-titles-path.txt"
if [[ -n "$REFERENCE_BENCHMARK_CASE" ]]; then
  run_cli compare-reference-case --reference-case "$REFERENCE_BENCHMARK_CASE" > "$WORKDIR/_smoke/reference-comparison-path.txt"
fi

SESSION_ID="$(python3 - "$WORKDIR" <<'PY'
from pathlib import Path
import sys
workdir = Path(sys.argv[1])
print((workdir / '.paper-orchestra' / 'current_session.txt').read_text(encoding='utf-8').strip())
PY
)"
RUN_DIR="$WORKDIR/.paper-orchestra/runs/$SESSION_ID"
SESSION_JSON="$RUN_DIR/session.json"

if [[ -n "$REFERENCE_BENCHMARK_CASE" ]]; then
  run_cli build-reference-case-partition-scaffold \
    --reference-case "$REFERENCE_BENCHMARK_CASE" \
    --output "$RUN_DIR/artifacts/reference_case_partition_scaffold.json" > "$WORKDIR/_smoke/reference-partition-scaffold-path.txt"
  run_cli compare-reference-case-citation-coverage \
    --reference-case "$REFERENCE_BENCHMARK_CASE" \
    --output "$RUN_DIR/artifacts/reference_case_partitioned_citation_coverage.json" > "$WORKDIR/_smoke/partitioned-citation-coverage-path.txt"
fi
run_cli audit-fidelity > "$WORKDIR/_smoke/fidelity.json"
run_cli build-session-eval-summary > "$WORKDIR/_smoke/session-eval-summary-path.txt"
if [[ -n "$REFERENCE_BENCHMARK_CASE" ]]; then
  run_cli compare-reference-case --reference-case "$REFERENCE_BENCHMARK_CASE" > "$WORKDIR/_smoke/reference-comparison-path.txt"
fi

python3 - "$SESSION_JSON" "$WORKDIR/_smoke/fidelity.json" "$WORKDIR/_smoke/job-status.json" <<'PY'
import json, sys
from pathlib import Path
session = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
fidelity = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
job = json.loads(Path(sys.argv[3]).read_text(encoding='utf-8'))
artifacts = session.get('artifacts', {})
summary = {
    'session_id': session['session_id'],
    'current_phase': session['current_phase'],
    'refinement_iteration': session.get('refinement_iteration'),
    'paper_full_tex': artifacts.get('paper_full_tex'),
    'latest_validation_json': artifacts.get('latest_validation_json'),
    'latest_fidelity_json': artifacts.get('latest_fidelity_json'),
    'latest_runtime_parity_json': artifacts.get('latest_runtime_parity_json'),
    'notes_tail': session.get('notes', [])[-6:],
    'fidelity_overall_status': fidelity.get('report', {}).get('overall_status', fidelity.get('overall_status')),
    'job_result_status': job.get('result', {}).get('status'),
}
print(json.dumps(summary, ensure_ascii=False, indent=2))
PY

if [[ -f "$WORKDIR/_smoke/session-eval-summary-path.txt" ]]; then
  echo "[smoke] session eval summary path:"
  cat "$WORKDIR/_smoke/session-eval-summary-path.txt"
fi
if [[ -f "$WORKDIR/_smoke/review-gate-comparison-path.txt" ]]; then
  echo "[smoke] review gate comparison path:"
  cat "$WORKDIR/_smoke/review-gate-comparison-path.txt"
fi
if [[ -f "$WORKDIR/_smoke/generated-citation-titles-path.txt" ]]; then
  echo "[smoke] generated citation titles path:"
  cat "$WORKDIR/_smoke/generated-citation-titles-path.txt"
fi
if [[ -f "$WORKDIR/_smoke/reference-comparison-path.txt" ]]; then
  echo "[smoke] reference comparison path:"
  cat "$WORKDIR/_smoke/reference-comparison-path.txt"
fi
if [[ -f "$WORKDIR/_smoke/reference-partition-scaffold-path.txt" ]]; then
  echo "[smoke] reference partition scaffold path:"
  cat "$WORKDIR/_smoke/reference-partition-scaffold-path.txt"
fi
if [[ -f "$WORKDIR/_smoke/partitioned-citation-coverage-path.txt" ]]; then
  echo "[smoke] partitioned citation coverage path:"
  cat "$WORKDIR/_smoke/partitioned-citation-coverage-path.txt"
fi

RESULT_STATUS="$(json_get "$WORKDIR/_smoke/job-status.json" "payload.get('result', {}).get('status', '')")"
if [[ "$RESULT_STATUS" != "draft_complete" && "$RESULT_STATUS" != "complete" ]]; then
  echo "[smoke] pipeline completed with non-success result status: $RESULT_STATUS" >&2
  cat "$WORKDIR/_smoke/job-status.json" >&2 || true
  exit 1
fi

if [[ -f "$RUN_DIR/artifacts/paper.full.tex" ]]; then
  echo "[smoke] manuscript preview:"
  sed -n '1,80p' "$RUN_DIR/artifacts/paper.full.tex"
fi

echo "[smoke] done. artifacts live in: $WORKDIR"
if [[ "$KEEP_WORKDIR" != "1" ]]; then
  echo "[smoke] workdir will be removed on exit"
fi
