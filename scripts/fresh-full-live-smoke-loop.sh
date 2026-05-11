#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/fresh-full-live-smoke-loop.sh --evidence-root DIR --material-root DIR [--max-operator-cycles N] [--max-iterations N] [--dry-run-contract]

Top-level fail-fast fresh full live smoke wrapper. This owns immutable material
validation, fresh workdir/session setup, evidence bundle shape, bounded
human_needed operator cycles, Lane-A/evidence/meta/Critic gates, and smoke-level
verdict synthesis. The inner scripts/live-smoke-claim-safe.sh remains an inner
claim-safe gate only and is not a replacement for this wrapper.
EOF
}

EVIDENCE_ROOT=""
MATERIAL_ROOT="examples/fresh-smoke-materials"
MAX_OPERATOR_CYCLES=3
MAX_ITER=8
DRY_RUN_CONTRACT=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --evidence-root) EVIDENCE_ROOT="$2"; shift 2 ;;
    --material-root) MATERIAL_ROOT="$2"; shift 2 ;;
    --max-operator-cycles) MAX_OPERATOR_CYCLES="$2"; shift 2 ;;
    --max-iterations) MAX_ITER="$2"; shift 2 ;;
    --dry-run-contract) DRY_RUN_CONTRACT=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
EVIDENCE_ROOT="${EVIDENCE_ROOT:-review/fresh-full-live-smoke-loop-${TS}}"
EVIDENCE_ROOT="$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$EVIDENCE_ROOT")"
WORKDIR="$EVIDENCE_ROOT/workdir"
LOGS="$EVIDENCE_ROOT/logs"
ARTIFACTS="$EVIDENCE_ROOT/artifacts"
OPFB="$EVIDENCE_ROOT/operator-feedback"
READABLE="$EVIDENCE_ROOT/readable"
CRITIC="$EVIDENCE_ROOT/critic"
mkdir -p "$LOGS" "$ARTIFACTS" "$OPFB" "$READABLE" "$CRITIC" "$WORKDIR" "$WORKDIR/inputs" "$EVIDENCE_ROOT/inputs-materials" "$EVIDENCE_ROOT/evidence-only" "$ARTIFACTS/prompts" "$EVIDENCE_ROOT/provider-traces"

if [[ -f "$REPO_ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$REPO_ROOT/.env"
  set +a
fi

export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"
export PAPERO_SMOKE_EVIDENCE_ROOT="$EVIDENCE_ROOT"
export PAPERO_ALLOW_TEX_COMPILE=1
export PAPERO_STRICT_CONTENT_GATES=1
export PAPERO_STRICT_OMX_NATIVE=1
export PAPERO_ALLOWED_PROVIDER_BINARIES="${PAPERO_ALLOWED_PROVIDER_BINARIES:-codex,bash,python3}"
export PAPERO_GEN_MODEL="${PAPERO_GEN_MODEL:-gpt-5.5}"
export PAPERO_GEN_REASONING_EFFORT="${PAPERO_GEN_REASONING_EFFORT:-medium}"
export PAPERO_WEB_MODEL="${PAPERO_WEB_MODEL:-gpt-5.5}"
export PAPERO_WEB_REASONING_EFFORT="${PAPERO_WEB_REASONING_EFFORT:-low}"
export PAPERO_OMX_MODEL="${PAPERO_OMX_MODEL:-gpt-5.5}"
export PAPERO_OMX_REASONING_EFFORT="${PAPERO_OMX_REASONING_EFFORT:-medium}"
export PAPERO_OMX_EXEC_TIMEOUT_SECONDS="${PAPERO_OMX_EXEC_TIMEOUT_SECONDS:-2400}"
export PAPERO_OMX_CONTROL_TIMEOUT_SECONDS="${PAPERO_OMX_CONTROL_TIMEOUT_SECONDS:-240}"
export PAPERO_PROVIDER_TIMEOUT_SECONDS="${PAPERO_PROVIDER_TIMEOUT_SECONDS:-2400}"
export PAPERO_PROVIDER_TIMEOUT_GRACE_SECONDS="${PAPERO_PROVIDER_TIMEOUT_GRACE_SECONDS:-180}"
# Fresh live smoke owns Codex replay at the wrapper layer so every prompt has a
# single auditable retry ledger.  Do not inherit provider/OMX replay knobs from
# .env here: ShellProvider would otherwise replay this wrapper, multiplying one
# smoke-stage prompt into nested attempts.
export PAPERO_PROVIDER_RETRY_ATTEMPTS=0
export PAPERO_PROVIDER_RETRY_BACKOFF_SECONDS=0
export PAPERO_PROVIDER_RETRY_SAFE=0
export PAPERO_OMX_TIMEOUT_GRACE_SECONDS="${PAPERO_OMX_TIMEOUT_GRACE_SECONDS:-180}"
export PAPERO_OMX_RETRY_ATTEMPTS=0
export PAPERO_OMX_RETRY_BACKOFF_SECONDS=0
export PAPERO_CODEX_RETRY_ATTEMPTS="${PAPERO_CODEX_RETRY_ATTEMPTS:-1}"
export PAPERO_CODEX_RETRY_BACKOFF_SECONDS="${PAPERO_CODEX_RETRY_BACKOFF_SECONDS:-15}"
SMOKE_CODEX_HOME="$(mktemp -d /tmp/paperorchestra-smoke-codex-home.XXXXXX)"
SOURCE_CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
cleanup_sensitive_codex_home() {
  rm -rf "$SMOKE_CODEX_HOME"
}
trap cleanup_sensitive_codex_home EXIT
prepare_smoke_codex_home() {
  mkdir -p "$SMOKE_CODEX_HOME"
  for file in auth.json config.toml version.json installation_id models_cache.json; do
    if [[ -f "$SOURCE_CODEX_HOME/$file" ]]; then
      cp "$SOURCE_CODEX_HOME/$file" "$SMOKE_CODEX_HOME/$file"
      chmod 600 "$SMOKE_CODEX_HOME/$file" 2>/dev/null || true
    fi
  done
  rm -f "$SMOKE_CODEX_HOME/hooks.json"
  chmod 700 "$SMOKE_CODEX_HOME" || true
}
prepare_smoke_codex_home
export PAPERO_SMOKE_CODEX_HOME="$SMOKE_CODEX_HOME"
CLI=(python3 -m paperorchestra.cli)
WRAPPER_PATH="$EVIDENCE_ROOT/provider-wrap.sh"
GEN_CMD="$(python3 -c 'import json, sys; print(json.dumps(["bash", sys.argv[1], "gen"]))' "$WRAPPER_PATH")"
WEB_CMD="$(python3 -c 'import json, sys; print(json.dumps(["bash", sys.argv[1], "web"]))' "$WRAPPER_PATH")"
export PAPERO_MODEL_CMD="$GEN_CMD"
export PAPERO_GEN_PROVIDER_CMD="$GEN_CMD"
export PAPERO_WEB_PROVIDER_CMD="$WEB_CMD"
PROVIDER=(--provider shell --provider-command "$GEN_CMD")
WEB_PROVIDER=(--provider shell --provider-command "$WEB_CMD")
CITATION_PROVIDER=(--citation-provider shell --citation-provider-command "$WEB_CMD")
RUNTIME=(--runtime-mode omx_native --strict-omx-native)

COMMAND_ROWS=()
FINAL_SMOKE_VERDICT="fail_execution_error"
QA_LOOP_TERMINAL_VERDICT="null"
QA_LOOP_TERMINAL_EXIT_CODE="null"
FIRST_FAILING_PREDICATE="preflight_not_completed"
FIRST_FAILING_ARTIFACT="null"
OPERATOR_FEEDBACK_CYCLES=0
OPERATOR_FEEDBACK_CYCLES_PROMOTED=0
OPERATOR_FEEDBACK_CYCLES_ROLLED_BACK=0
OPERATOR_FEEDBACK_CYCLES_FAILED=0
MATERIAL_INVARIANCE_STATUS="fail"
EVIDENCE_COMPLETENESS_STATUS="fail"
LANE_A_STATUS="not_run"
CRITIC_VERDICT="not_run"
QUALITY_GATE_STATUS="unknown"
MANUSCRIPT_READINESS="unknown"
LOOP_STOP_REASON="not_started"

redact() {
  local private_artifact_marker="paperorchestra-""private"
  sed -E "s#(/home/kosh/temp/|\.\./)?${private_artifact_marker}[^[:space:]]*#[REDACTED_PRIVATE_ARTIFACT_PATH]#g; s/s2k-[A-Za-z0-9]+/[REDACTED_S2_KEY]/g; s/sk-(proj|live|test|svcacct)-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9]{32,}/[REDACTED_OPENAI_KEY]/g; s/Bearer[[:space:]]+[A-Za-z0-9._-]{20,}/Bearer [REDACTED_TOKEN]/g"
}

run_release_safety_scan() {
  local scan_root="$1"
  local output="$2"
  python3 "$REPO_ROOT/scripts/release-safety-scan.py" "$scan_root" "$output"
}
record_command_markdown() {
  {
    echo "# Command exit codes"
    echo
    for row in "${COMMAND_ROWS[@]:-}"; do
      IFS='|' read -r name rc <<<"$row"
      echo "- \`$name\`: \`$rc\`"
    done
  } > "$READABLE/commands.md"
}

write_timeline() {
  echo "$1" >> "$READABLE/timeline.md"
}

run_step() {
  local caller_errexit=0
  [[ $- == *e* ]] && caller_errexit=1
  local name="$1"; shift
  echo "==> $name"
  write_timeline "- $(date -u +%Y-%m-%dT%H:%M:%SZ) start $name"
  printf '%q ' "$@" > "$LOGS/${name}.command"
  printf '\n' >> "$LOGS/${name}.command"
  local had_smoke_command_name=0
  local old_smoke_command_name="${PAPERO_SMOKE_COMMAND_NAME:-}"
  if [[ ${PAPERO_SMOKE_COMMAND_NAME+x} ]]; then had_smoke_command_name=1; fi
  export PAPERO_SMOKE_COMMAND_NAME="$name"
  set +e
  "$@" > >(redact > "$LOGS/${name}.stdout.log") 2> >(redact > "$LOGS/${name}.stderr.log")
  local rc=$?
  set -e
  if [[ "$had_smoke_command_name" == "1" ]]; then
    export PAPERO_SMOKE_COMMAND_NAME="$old_smoke_command_name"
  else
    unset PAPERO_SMOKE_COMMAND_NAME
  fi
  printf '%s\n' "$rc" > "$LOGS/${name}.exitcode"
  COMMAND_ROWS+=("${name}|${rc}")
  record_command_markdown
  write_timeline "- $(date -u +%Y-%m-%dT%H:%M:%SZ) end $name rc=$rc"
  if [[ "$caller_errexit" == "1" ]]; then
    set -e
  else
    set +e
  fi
  return "$rc"
}

run_without_papero_env() {
  local repo="$1"; shift
  for key in $(env | sed -n 's/=.*//p' | grep '^PAPERO_' || true); do
    unset "$key"
  done
  export PYTHONPATH="$repo${PYTHONPATH:+:$PYTHONPATH}"
  exec "$@"
}
export -f run_without_papero_env


retryable_transport_file() {
  local file="$1"
  [[ -f "$file" ]] || return 1
  python3 -m paperorchestra.transport_retry --file "$file"
}

run_codex_last_message() {
  local label="$1"; local prompt="$2"; local response="$3"; local stdout_log="$4"; local stderr_log="$5"; local exitcode_file="$6"; local model="$7"; local effort="$8"
  local attempts=$(( ${PAPERO_CODEX_RETRY_ATTEMPTS:-0} + 1 ))
  local backoff="${PAPERO_CODEX_RETRY_BACKOFF_SECONDS:-0}"
  local rc=1
  for attempt in $(seq 1 "$attempts"); do
    local attempt_response="${response}.attempt-${attempt}"
    local attempt_stdout="${stdout_log}.attempt-${attempt}"
    local attempt_stderr="${stderr_log}.attempt-${attempt}"
    local raw_attempt_response="${attempt_response}.raw"
    local raw_attempt_stdout="${attempt_stdout}.raw"
    local raw_attempt_stderr="${attempt_stderr}.raw"
    set +e
    CODEX_HOME="$SMOKE_CODEX_HOME" codex exec --skip-git-repo-check -C "$REPO_ROOT" -m "$model" -c "model_reasoning_effort=\"${effort}\"" --output-last-message "$raw_attempt_response" - < "$prompt" > "$raw_attempt_stdout" 2> "$raw_attempt_stderr"
    rc=$?
    set -e
    printf '%s\n' "$rc" > "${exitcode_file}.attempt-${attempt}"
    local retryable="false"
    if retryable_transport_file "$raw_attempt_stderr"; then retryable="true"; fi
    printf '{"label":"%s","attempt":%s,"exit_code":%s,"retryable_transport":%s,"replayed":%s}\n' "$label" "$attempt" "$rc" "$retryable" "$([[ "$attempt" -gt 1 ]] && echo true || echo false)" >> "${exitcode_file}.retry.jsonl"
    redact < "$raw_attempt_stdout" > "$attempt_stdout"
    redact < "$raw_attempt_stderr" > "$attempt_stderr"
    if [[ -f "$raw_attempt_response" ]]; then redact < "$raw_attempt_response" > "$attempt_response"; fi
    cp "$attempt_stdout" "$stdout_log"
    cp "$attempt_stderr" "$stderr_log"
    if [[ -f "$attempt_response" ]]; then cp "$attempt_response" "$response"; fi
    rm -f "$raw_attempt_response" "$raw_attempt_stdout" "$raw_attempt_stderr"
    printf '%s\n' "$rc" > "$exitcode_file"
    if [[ "$rc" == "0" ]]; then
      return 0
    fi
    if [[ "$attempt" -lt "$attempts" ]] && [[ "$retryable" == "true" ]]; then
      write_timeline "- $(date -u +%Y-%m-%dT%H:%M:%SZ) retry $label attempt=$attempt rc=$rc reason=codex_transport"
      python3 - "$backoff" "${PAPERO_CODEX_RETRY_JITTER_SECONDS:-0}" <<'PY_SLEEP'
import random, sys, time
base=float(sys.argv[1] or 0)
spread=float(sys.argv[2] or 0)
time.sleep(max(0.0, base) + (random.uniform(0.0, max(0.0, spread)) if spread > 0 else 0.0))
PY_SLEEP
      continue
    fi
    return "$rc"
  done
  return "$rc"
}

make_manifest() {
  python3 - "$EVIDENCE_ROOT" "$REPO_ROOT" <<'PY'
import json, re, sys
from pathlib import Path
from paperorchestra.fresh_smoke import build_fresh_smoke_artifact_manifest
root=Path(sys.argv[1]).resolve()
repo=Path(sys.argv[2]).resolve()
(root/'artifact-manifest.json').write_text(json.dumps(build_fresh_smoke_artifact_manifest(root, repo), indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
PY
}

write_verdict() {
  local verdict="$1"; local predicate="$2"; local artifact="$3"
  FINAL_SMOKE_VERDICT="$verdict"
  FIRST_FAILING_PREDICATE="$predicate"
  FIRST_FAILING_ARTIFACT="$artifact"
  cat > "$READABLE/verdict.json" <<EOF
{
  "schema_version": "fresh-smoke-verdict/1",
  "smoke_verdict": "${FINAL_SMOKE_VERDICT}",
  "qa_loop_terminal_verdict": ${QA_LOOP_TERMINAL_VERDICT},
  "qa_loop_terminal_exit_code": ${QA_LOOP_TERMINAL_EXIT_CODE},
  "first_failing_predicate": ${FIRST_FAILING_PREDICATE},
  "first_failing_artifact": ${FIRST_FAILING_ARTIFACT},
  "operator_feedback_cycles": ${OPERATOR_FEEDBACK_CYCLES},
  "operator_feedback_cycles_attempted": ${OPERATOR_FEEDBACK_CYCLES},
  "operator_feedback_cycles_promoted": ${OPERATOR_FEEDBACK_CYCLES_PROMOTED},
  "operator_feedback_cycles_rolled_back": ${OPERATOR_FEEDBACK_CYCLES_ROLLED_BACK},
  "operator_feedback_cycles_failed": ${OPERATOR_FEEDBACK_CYCLES_FAILED},
  "material_invariance_status": "${MATERIAL_INVARIANCE_STATUS}",
  "evidence_completeness_status": "${EVIDENCE_COMPLETENESS_STATUS}",
  "lane_a_status": "${LANE_A_STATUS}",
  "critic_verdict": "${CRITIC_VERDICT}",
  "quality_gate_status": "${QUALITY_GATE_STATUS}",
  "manuscript_readiness": "${MANUSCRIPT_READINESS}",
  "orchestration_stop_reason": "${LOOP_STOP_REASON}"
}
EOF
  cat > "$EVIDENCE_ROOT/README.md" <<EOF
# Fresh full live smoke loop evidence

- started_at_utc: ${TS}
- updated_at_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)
- repo_root: ${REPO_ROOT}
- head: $(git rev-parse HEAD 2>/dev/null || echo unknown)
- material_root: ${MATERIAL_ROOT}
- smoke_verdict: ${FINAL_SMOKE_VERDICT}
- qa_loop_terminal_verdict: ${QA_LOOP_TERMINAL_VERDICT}
- operator_feedback_cycles: ${OPERATOR_FEEDBACK_CYCLES}
- operator_feedback_cycles_attempted: ${OPERATOR_FEEDBACK_CYCLES}
- operator_feedback_cycles_promoted: ${OPERATOR_FEEDBACK_CYCLES_PROMOTED}
- operator_feedback_cycles_rolled_back: ${OPERATOR_FEEDBACK_CYCLES_ROLLED_BACK}
- operator_feedback_cycles_failed: ${OPERATOR_FEEDBACK_CYCLES_FAILED}
- first_failing_predicate: ${FIRST_FAILING_PREDICATE}
- first_failing_artifact: ${FIRST_FAILING_ARTIFACT}
- quality_gate_status: ${QUALITY_GATE_STATUS}
- manuscript_readiness: ${MANUSCRIPT_READINESS}
- orchestration_stop_reason: ${LOOP_STOP_REASON}

## Non-submission warning

This run verifies PaperOrchestra loop mechanics, evidence capture, no-meta behavior,
and feedback incorporation. Any generated manuscript is a draft and must not be
represented as camera-ready or submission-ready.

## Verdict transition protocol

Before the terminal Q1 Critic runs, this wrapper writes a capture-time holding
verdict with \`smoke_verdict=fail_critic_reject\` and
\`first_failing_predicate=critic_not_run_yet\`. The Critic may cite that
capture-time verdict because it is the only truthful persisted state before the
Critic has approved the bundle. If the Critic returns \`SYSTEM_TEST_VERDICT:
PASS\` and the post-Critic evidence validator passes, the wrapper rewrites the
persisted verdict to \`pass_loop_verified\`. Treat the Critic response as a
time-stamped review of the pre-terminal state, and treat
\`readable/verdict.json\` as the final machine-readable state.

## How to review

- Commands: readable/commands.md and logs/*.command/stdout/stderr/exitcode
- Prompts/responses: artifacts/prompts/, provider-traces/, operator-feedback/, critic/
- Manuscript artifacts: artifacts/paper.full.tex, artifacts/paper.full.pdf, artifacts/paper.full.txt when produced
- Feedback cycles: operator-feedback/
- Lane A validation: artifacts/fresh-smoke-lane-a-acceptance.json
- Material invariance: artifacts/material-invariance.json
- Evidence completeness: artifacts/evidence-completeness.json
EOF
}

fail_now() {
  local verdict="$1"; local predicate_json="$2"; local artifact_json="$3"; local exit_code="${4:-1}"
  write_verdict "$verdict" "$predicate_json" "$artifact_json"
  python3 "$REPO_ROOT/scripts/validate-fresh-smoke-evidence.py" "$EVIDENCE_ROOT" --output "$ARTIFACTS/evidence-completeness.json" >/dev/null 2>&1 || true
  if [[ -f "$ARTIFACTS/evidence-completeness.json" ]]; then
    EVIDENCE_COMPLETENESS_STATUS="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("status","fail"))' "$ARTIFACTS/evidence-completeness.json")"
    write_verdict "$verdict" "$predicate_json" "$artifact_json"
  fi
  echo "Fresh full live smoke FAIL: $verdict"
  echo "Evidence: $EVIDENCE_ROOT"
  exit "$exit_code"
}

derive_final_quality_status() {
  if [[ ! -f "$ARTIFACTS/quality-eval.final.json" ]]; then
    QUALITY_GATE_STATUS="unknown"
    MANUSCRIPT_READINESS="unknown"
    return 0
  fi
  local derived
  derived="$(python3 - "$ARTIFACTS/quality-eval.final.json" "$FINAL" <<'PY'
import json, sys
from pathlib import Path

quality_path = Path(sys.argv[1])
terminal = sys.argv[2]
try:
    payload = json.loads(quality_path.read_text(encoding="utf-8"))
except Exception:
    print("unknown unknown")
    raise SystemExit(0)
tiers = payload.get("tiers") if isinstance(payload.get("tiers"), dict) else {}
tier_status = {
    name: (value.get("status") if isinstance(value, dict) else None)
    for name, value in tiers.items()
}
if tier_status.get("tier_0_preconditions") != "pass":
    quality_gate = "fail_tier0"
elif tier_status.get("tier_1_structural") != "pass":
    quality_gate = "fail_tier1"
elif tier_status.get("tier_2_claim_safety") != "pass":
    quality_gate = "fail_tier2"
elif tier_status.get("tier_3_scholarly_quality") != "pass":
    quality_gate = "fail_tier3"
elif (payload.get("provenance_trust") or {}).get("level") != "live":
    quality_gate = "fail_provenance"
else:
    quality_gate = "pass"
readiness = "ready_for_human_finalization" if terminal == "ready_for_human_finalization" and quality_gate == "pass" else "not_ready"
print(quality_gate, readiness)
PY
)"
  QUALITY_GATE_STATUS="${derived%% *}"
  MANUSCRIPT_READINESS="${derived#* }"
}

reconcile_final_qa_plan_with_terminal_state() {
  [[ -f "$ARTIFACTS/qa-loop.plan.final.json" ]] || return 0
  python3 - "$ARTIFACTS/qa-loop.plan.final.json" "$ARTIFACTS/qa-loop.plan.json" "$FINAL" "$STEP_RC" "$LOOP_STOP_REASON" "$MAX_OPERATOR_CYCLES" "$OPERATOR_FEEDBACK_CYCLES" "$OPERATOR_FEEDBACK_CYCLES_PROMOTED" "$OPERATOR_FEEDBACK_CYCLES_ROLLED_BACK" "$OPERATOR_FEEDBACK_CYCLES_FAILED" "$QUALITY_GATE_STATUS" "$MANUSCRIPT_READINESS" <<'PY'
import json, sys
from pathlib import Path

final_path = Path(sys.argv[1])
canonical_path = Path(sys.argv[2])
terminal_verdict = sys.argv[3]
terminal_exit_code = int(sys.argv[4])
stop_reason = sys.argv[5]
max_operator_cycles = int(sys.argv[6])
operator_feedback_cycles = int(sys.argv[7])
operator_feedback_cycles_promoted = int(sys.argv[8])
operator_feedback_cycles_rolled_back = int(sys.argv[9])
operator_feedback_cycles_failed = int(sys.argv[10])
quality_gate_status = sys.argv[11]
manuscript_readiness = sys.argv[12]

payload = json.loads(final_path.read_text(encoding="utf-8"))
original = payload.get("verdict")
payload["orchestration_terminal"] = {
    "verdict": terminal_verdict,
    "exit_code": terminal_exit_code,
    "stop_reason": stop_reason,
    "operator_feedback_cycles": operator_feedback_cycles,
    "operator_feedback_cycles_attempted": operator_feedback_cycles,
    "operator_feedback_cycles_promoted": operator_feedback_cycles_promoted,
    "operator_feedback_cycles_rolled_back": operator_feedback_cycles_rolled_back,
    "operator_feedback_cycles_failed": operator_feedback_cycles_failed,
    "max_operator_cycles": max_operator_cycles,
    "quality_gate_status": quality_gate_status,
    "manuscript_readiness": manuscript_readiness,
    "smoke_verdict_semantics": "system_loop_only_not_manuscript_readiness",
}
if terminal_verdict in {"human_needed", "failed", "execution_error"} and original != terminal_verdict:
    payload["planner_verdict_before_orchestration_reconciliation"] = original
    payload["verdict"] = terminal_verdict
    rationale = str(payload.get("verdict_rationale") or "").strip()
    prefix = (
        f"orchestration terminal state is {terminal_verdict} "
        f"({stop_reason}; operator_feedback_cycles={operator_feedback_cycles}/{max_operator_cycles})"
    )
    payload["verdict_rationale"] = f"{prefix}; planner said {original}. {rationale}".strip()
for path in {final_path, canonical_path}:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
PY
}

copy_session_artifacts() {
  mkdir -p "$ARTIFACTS" "$ARTIFACTS/prompts"
  if [[ -f "$WORKDIR/.paper-orchestra/current_session.txt" ]]; then
    local sid run_dir run_artifacts
    sid="$(cat "$WORKDIR/.paper-orchestra/current_session.txt")"
    run_dir="$WORKDIR/.paper-orchestra/runs/$sid"
    run_artifacts="$run_dir/artifacts"
    mkdir -p "$ARTIFACTS/session-snapshot-final"
    cp -R "$run_dir/." "$ARTIFACTS/session-snapshot-final/" 2>/dev/null || true
    cp -R "$run_artifacts/prompts/." "$ARTIFACTS/prompts/" 2>/dev/null || true
    cp -R "$run_artifacts/lane-manifests" "$ARTIFACTS/" 2>/dev/null || true
    for p in \
      "$run_dir"/build/compiled/*.pdf \
      "$run_artifacts"/paper.full.tex \
      "$run_artifacts"/references.bib \
      "$run_artifacts"/quality-eval.json \
      "$run_artifacts"/qa-loop.plan.json \
      "$run_artifacts"/qa-loop-history.jsonl \
      "$run_artifacts"/qa-loop-execution*.json \
      "$run_artifacts"/citation_support_review.json \
      "$run_artifacts"/citation_support_review.trace.json \
      "$run_artifacts"/section_review.json \
      "$run_artifacts"/figure_placement_review.json \
      "$run_artifacts"/review.latest.json \
      "$run_artifacts"/source_obligations.json \
      "$run_artifacts"/ralph-brief.md \
      "$run_artifacts"/ralph-handoff.json; do
      [[ -f "$p" ]] && cp "$p" "$ARTIFACTS/$(basename "$p")" || true
    done
    shopt -s nullglob
    for exec_json in "$run_dir"/qa-loop-execution.iter-*.json; do
      cp "$exec_json" "$ARTIFACTS/$(basename "$exec_json")" || true
    done
    shopt -u nullglob
  fi
  if [[ -f "$ARTIFACTS/paper.full.pdf" ]]; then
    pdftotext "$ARTIFACTS/paper.full.pdf" "$ARTIFACTS/paper.full.txt" 2>/dev/null || true
  fi
}

preserve_operator_feedback_execution_cycle() {
  local cycle="$1"
  local apply_rc="${2:-0}"
  local src=""
  if [[ -f "$WORKDIR/.paper-orchestra/current_session.txt" ]]; then
    local sid
    sid="$(cat "$WORKDIR/.paper-orchestra/current_session.txt")"
    src="$WORKDIR/.paper-orchestra/runs/$sid/artifacts/operator_feedback.execution.json"
  fi
  local dest="$ARTIFACTS/operator_feedback.execution.cycle-${cycle}.json"
  local readable_dest="$OPFB/operator_feedback.execution.cycle-${cycle}.json"
  if [[ -n "$src" && -f "$src" ]]; then
    cp "$src" "$dest" || true
    cp "$src" "$readable_dest" || true
  fi
  local classification
  classification="$(python3 - "$dest" "$apply_rc" <<'PY_CLASSIFY'
import json, sys
from pathlib import Path

path = Path(sys.argv[1])
apply_rc = int(sys.argv[2])
if not path.exists():
    print("failed")
    raise SystemExit(0)
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    print("failed")
    raise SystemExit(0)

promotion = str(payload.get("promotion_status") or payload.get("status") or "").lower()
candidate = payload.get("candidate_result") if isinstance(payload.get("candidate_result"), dict) else {}
accepted = candidate.get("accepted")
candidate_only = candidate.get("candidate_only")
has_rollback = isinstance(payload.get("candidate_rollback"), dict)
attempt_failures = []
for attempt in payload.get("attempts") or []:
    if isinstance(attempt, dict):
        attempt_failures.append(str(attempt.get("executor_failure_category") or "none").lower())

if promotion in {"promoted", "accepted", "canonical_updated"} or (accepted is True and candidate_only is False):
    print("promoted")
elif promotion == "rolled_back" or has_rollback or accepted is False:
    print("rolled_back")
elif apply_rc != 0 or any(value not in {"", "none"} for value in attempt_failures):
    print("failed")
else:
    print("failed")
PY_CLASSIFY
)"
  case "$classification" in
    promoted) OPERATOR_FEEDBACK_CYCLES_PROMOTED=$((OPERATOR_FEEDBACK_CYCLES_PROMOTED + 1)) ;;
    rolled_back) OPERATOR_FEEDBACK_CYCLES_ROLLED_BACK=$((OPERATOR_FEEDBACK_CYCLES_ROLLED_BACK + 1)) ;;
    *) OPERATOR_FEEDBACK_CYCLES_FAILED=$((OPERATOR_FEEDBACK_CYCLES_FAILED + 1)) ;;
  esac
  printf '%s\n' "$classification" > "$OPFB/operator-feedback-cycle-${cycle}.classification"
}


current_qa_plan_verdict() {
  local plan="$ARTIFACTS/qa-loop.plan.json"
  if [[ ! -f "$plan" ]]; then
    echo "unknown"
    return 0
  fi
  python3 - "$plan" <<'PY_VERDICT'
import json, sys
from pathlib import Path
try:
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
except Exception:
    print("unknown")
else:
    print(payload.get("verdict") or "unknown")
PY_VERDICT
}

scan_meta_leakage() {
  copy_session_artifacts || true
  python3 - "$ARTIFACTS" <<'PY'
import json, re, sys
from pathlib import Path
root=Path(sys.argv[1])
patterns=[
 r"caption intent", r"fidelity:", r"concept-grounded", r"mixed fidelity", r"source[_\s-]*fidelity",
 r"claim_map", r"narrative_plan", r"quality gate", r"qa-loop", r"human_needed", r"operator feedback",
 r"codex_operator", r"paperorchestra", r"\b(?:prompt\s*/\s*meta|prompt\s+meta|prompt instructions?|internal prompt|figure prompt|plot prompt)\b", r"TODO", r"TBD", r"\bmust preserve (?:paper-specific|exact|method|proof|benchmark)",
 r"((supplied|provided) (material|source|file|analysis|analyses|log|evidence|theorem statements?)|available (material|source|file|log))",
 r"((supplied|provided) )?(method|construction|proof|benchmark|empirical|review|source|material) packet",
 r"(following|specified in|as specified in) the packet", r"manuscript plan",
 r"reviewable (material|source|file|analysis|log|figure)", r"no reviewable figure", r"no figures because",
]
findings=[]
for name in ["paper.full.tex","paper.full.txt"]:
    path=root/name
    if not path.exists():
        continue
    text=path.read_text(encoding='utf-8', errors='replace')
    for pat in patterns:
        for m in re.finditer(pat, text, re.I):
            findings.append({"file":name,"pattern":pat,"offset":m.start(),"excerpt":text[max(0,m.start()-120):m.end()+120]})
(root/'meta-leakage-scan.json').write_text(json.dumps({"schema_version":"meta-leakage-scan/1","status":"pass" if not findings else "fail","finding_count":len(findings),"findings":findings}, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
print(len(findings))
raise SystemExit(0 if not findings else 1)
PY
}

write_provider_wrapper() {
  cat > "$WRAPPER_PATH" <<'WRAP'
#!/usr/bin/env bash
set -euo pipefail
mode="${1:-gen}"
root="${PAPERO_SMOKE_EVIDENCE_ROOT:?PAPERO_SMOKE_EVIDENCE_ROOT missing}"
mkdir -p "$root/provider-traces"
idx_file="$root/provider-traces/.counter"
idx=0
if [[ -f "$idx_file" ]]; then idx="$(cat "$idx_file")"; fi
idx=$((idx+1)); printf '%s\n' "$idx" > "$idx_file"
prefix="$root/provider-traces/$(printf '%04d' "$idx")-${mode}"
cat > "${prefix}.prompt.md"
python3 - "$prefix.meta.json" "$mode" "${PAPERO_SMOKE_COMMAND_NAME:-unknown}" <<'PY_TRACE_META'
import json, sys
from pathlib import Path
meta_path = Path(sys.argv[1])
stem = meta_path.name[:-len(".meta.json")] if meta_path.name.endswith(".meta.json") else meta_path.stem
payload = {
    "schema_version": "provider-trace-meta/1",
    "mode": sys.argv[2],
    "command_name": sys.argv[3],
    "prompt": f"{stem}.prompt.md",
    "response": f"{stem}.response.md",
    "stderr": f"{stem}.stderr.log",
    "exitcode": f"{stem}.exitcode",
    "retry_ledger": f"{stem}.retry.jsonl",
}
meta_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
PY_TRACE_META
if [[ "$mode" == "web" ]]; then
  cmd=(codex --search exec --skip-git-repo-check -m "${PAPERO_WEB_MODEL:-gpt-5.5}" -c "model_reasoning_effort=\"${PAPERO_WEB_REASONING_EFFORT:-low}\"")
else
  cmd=(codex exec --skip-git-repo-check -m "${PAPERO_GEN_MODEL:-gpt-5.5}" -c "model_reasoning_effort=\"${PAPERO_GEN_REASONING_EFFORT:-medium}\"")
fi
attempts=$(( ${PAPERO_CODEX_RETRY_ATTEMPTS:-0} + 1 ))
backoff="${PAPERO_CODEX_RETRY_BACKOFF_SECONDS:-0}"
jitter="${PAPERO_CODEX_RETRY_JITTER_SECONDS:-0}"
retryable_transport_file() {
  local file="$1"
  [[ -f "$file" ]] || return 1
  python3 -m paperorchestra.transport_retry --file "$file"
}
retry_sleep() {
  local base="$1"; local spread="$2"
  python3 - "$base" "$spread" <<'PY_SLEEP'
import random, sys, time
base=float(sys.argv[1] or 0)
spread=float(sys.argv[2] or 0)
time.sleep(max(0.0, base) + (random.uniform(0.0, max(0.0, spread)) if spread > 0 else 0.0))
PY_SLEEP
}
rc=1
for attempt in $(seq 1 "$attempts"); do
  set +e
  CODEX_HOME="${PAPERO_SMOKE_CODEX_HOME:?PAPERO_SMOKE_CODEX_HOME missing}" "${cmd[@]}" < "${prefix}.prompt.md" > "${prefix}.attempt-${attempt}.response.md.raw" 2> "${prefix}.attempt-${attempt}.stderr.log.raw"
  rc=$?
  set -e
  printf '%s\n' "$rc" > "${prefix}.attempt-${attempt}.exitcode"
  retryable=false
  if retryable_transport_file "${prefix}.attempt-${attempt}.stderr.log.raw"; then retryable=true; fi
  printf '{"mode":"%s","attempt":%s,"exit_code":%s,"retryable_transport":%s,"replayed":%s}\n' "$mode" "$attempt" "$rc" "$retryable" "$([[ "$attempt" -gt 1 ]] && echo true || echo false)" >> "${prefix}.retry.jsonl"
  private_artifact_marker="paperorchestra-""private"
  sed -E "s#(/home/kosh/temp/|\\.\\./)?${private_artifact_marker}[^[:space:]]*#[REDACTED_PRIVATE_ARTIFACT_PATH]#g; s/s2k-[A-Za-z0-9]+/[REDACTED_S2_KEY]/g; s/sk-(proj|live|test|svcacct)-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9]{32,}/[REDACTED_OPENAI_KEY]/g; s/Bearer[[:space:]]+[A-Za-z0-9._-]{20,}/Bearer [REDACTED_TOKEN]/g" < "${prefix}.attempt-${attempt}.response.md.raw" > "${prefix}.attempt-${attempt}.response.md"
  sed -E "s#(/home/kosh/temp/|\\.\\./)?${private_artifact_marker}[^[:space:]]*#[REDACTED_PRIVATE_ARTIFACT_PATH]#g; s/s2k-[A-Za-z0-9]+/[REDACTED_S2_KEY]/g; s/sk-(proj|live|test|svcacct)-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9]{32,}/[REDACTED_OPENAI_KEY]/g; s/Bearer[[:space:]]+[A-Za-z0-9._-]{20,}/Bearer [REDACTED_TOKEN]/g" < "${prefix}.attempt-${attempt}.stderr.log.raw" > "${prefix}.attempt-${attempt}.stderr.log"
  rm -f "${prefix}.attempt-${attempt}.response.md.raw" "${prefix}.attempt-${attempt}.stderr.log.raw"
  cp "${prefix}.attempt-${attempt}.response.md" "${prefix}.response.md"
  cp "${prefix}.attempt-${attempt}.stderr.log" "${prefix}.stderr.log"
  printf '%s\n' "$rc" > "${prefix}.exitcode"
  if [[ "$rc" == "0" ]]; then
    cat "${prefix}.response.md"
    exit 0
  fi
  if [[ "$attempt" -lt "$attempts" ]] && [[ "$retryable" == "true" ]]; then
    retry_sleep "$backoff" "$jitter"
    continue
  fi
  cat "${prefix}.response.md"
  exit "$rc"
done
cat "${prefix}.response.md"
exit "$rc"
WRAP
  chmod +x "$WRAPPER_PATH"
  python3 - "$WRAPPER_PATH" <<'PY_CONTRACT'
import hashlib, json, sys
from pathlib import Path
wrapper = Path(sys.argv[1]).resolve()
contract = {
    "schema_version": "provider-wrapper-contract/1",
    "wrapper_path": str(wrapper),
    "wrapper_sha256": hashlib.sha256(wrapper.read_bytes()).hexdigest(),
    "modes": {
        "gen": {
            "trace_wrapped": True,
            "web_search_capable": False,
            "exec_argv_prefix": ["codex", "exec"],
        },
        "web": {
            "trace_wrapped": True,
            "web_search_capable": True,
            "exec_argv_prefix": ["codex", "--search", "exec"],
        },
    },
}
(wrapper.with_name("provider-wrap.contract.json")).write_text(json.dumps(contract, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
PY_CONTRACT
}

emit_dry_run_contract() {
  write_provider_wrapper
  python3 - "$EVIDENCE_ROOT" "$WRAPPER_PATH" "$GEN_CMD" "$WEB_CMD" <<'PY_DRY'
import json, sys
from pathlib import Path
root=Path(sys.argv[1]); wrapper=Path(sys.argv[2])
sidecar=json.loads(wrapper.with_name("provider-wrap.contract.json").read_text(encoding="utf-8"))
print(json.dumps({
  "schema_version":"fresh-full-live-smoke-contract/1",
  "evidence_root":str(root),
  "provider_commands":{"gen":json.loads(sys.argv[3]),"web":json.loads(sys.argv[4])},
  "provider_wrapper_contract":sidecar,
  "stage_contracts":[
    {"name":"compile_initial","class":"mandatory","fail_policy":"fail_now"},
    {"name":"review_citations_web_initial","class":"mandatory","fail_policy":"fail_now"},
    {"name":"meta_leakage","class":"mandatory","fail_policy":"fail_now"},
  ],
  "evidence_contracts":{"provider_prompt_response_required":True,"meta_leakage_scan_after_write_sections":True,"live_verification_provenance_required":True},
}, indent=2, ensure_ascii=False))
PY_DRY
}


write_live_verification_summary() {
  PYTHONPATH="$REPO_ROOT:${PYTHONPATH:-}" python3 - "$WORKDIR" "$ARTIFACTS/live-verification-provenance.json" <<'PY_LIVE'
import json, sys
from pathlib import Path
from paperorchestra.fidelity import _citation_registry_live_provenance
workdir=Path(sys.argv[1]); out=Path(sys.argv[2])
sid_path=workdir/'.paper-orchestra'/'current_session.txt'
payload={
    "schema_version":"live-verification-provenance/1",
    "status":"missing_session",
    "mode":"live",
    "on_error":"skip",
    "live_verified_count":0,
    "registry_count":0,
    "skipped_count":0,
    "seed_only_count":0,
    "live_coverage_ratio":0.0,
    "mixed":False,
    "provenance_level":"missing_session",
}
if sid_path.exists():
    sid=sid_path.read_text(encoding='utf-8').strip()
    artifacts=workdir/'.paper-orchestra'/'runs'/sid/'artifacts'
    registry=artifacts/'citation_registry.json'
    errors=artifacts/'verification_errors.json'
    err_payload={}
    if errors.exists():
        try: err_payload=json.loads(errors.read_text(encoding='utf-8'))
        except Exception: err_payload={}
    skipped=int(err_payload.get('error_count') or 0) if isinstance(err_payload, dict) else 0
    provenance=_citation_registry_live_provenance(registry)
    registry_count=int(provenance.get('registry_count') or 0)
    live_verified=int(provenance.get('live_verified_count') or 0)
    seed_only=int(provenance.get('seed_only_count') or 0)
    mixed=bool(skipped or seed_only)
    live_coverage=(live_verified / registry_count) if registry_count else 0.0
    payload={
        "schema_version":"live-verification-provenance/1",
        "status":"mixed" if mixed else "pass",
        "mode":"live",
        "on_error":"skip",
        "live_verified_count":live_verified,
        "registry_count":registry_count,
        "skipped_count":skipped,
        "seed_only_count":seed_only,
        "live_coverage_ratio":live_coverage,
        "mixed":mixed,
        "provenance_level":"live" if registry_count and not mixed and live_verified == registry_count else ("mixed" if registry_count else "empty_registry"),
        "coverage_policy":"provenance_level=live only when every registry entry is live-verified and no skipped or seed-only entries remain; any seed-only or skipped entry makes this mixed",
        "registry_path":str(registry) if registry.exists() else None,
        "verification_errors_path":str(errors) if errors.exists() else None,
        "warning":"live verification is mixed; do not treat seed-only or skipped entries as clean live verification" if mixed else None,
    }
out.write_text(json.dumps(payload, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
print(json.dumps(payload, sort_keys=True))
PY_LIVE
}

write_operator_feedback() {
  local cycle="$1"
  local packet="$OPFB/operator-review-packet.cycle-${cycle}.json"
  local feedback="$OPFB/operator-feedback.cycle-${cycle}.json"
  local prompt="$OPFB/operator-feedback-author.cycle-${cycle}.prompt.md"
  local response="$OPFB/operator-feedback-author.cycle-${cycle}.response.md"
  if [[ -f "$ARTIFACTS/paper.full.pdf" ]]; then
    run_step "operator_packet_cycle_${cycle}" "${CLI[@]}" build-operator-review-packet --output "$packet" --review-scope pdf_and_tex --require-pdf || return 1
  else
    run_step "operator_packet_cycle_${cycle}" "${CLI[@]}" build-operator-review-packet --output "$packet" --review-scope tex_only || return 1
  fi
  cat > "$prompt" <<PROMPT
You are bounded Codex-as-operator feedback for a PaperOrchestra fresh smoke. Use only the packet and unchanged source-material context. Do not add new facts beyond the supplied material. Return strict JSON only.

Packet JSON: $packet
Current TeX: $ARTIFACTS/paper.full.tex
Quality eval: $ARTIFACTS/quality-eval.json
QA-loop plan: $ARTIFACTS/qa-loop.plan.json
Citation critic: $ARTIFACTS/citation_support_review.json
Meta leakage scan: $ARTIFACTS/meta-leakage-scan.json

Schema: {"intent":"approve_existing_candidate|generate_new_operator_candidate|reject_candidate_with_reason","issues":[{"source_artifact_role":"paper_full_tex|quality_eval|qa_loop_plan|qa_loop_execution|operator_feedback_execution|section_review|citation_support_review|compiled_pdf","source_item_key":"short locator","target_section":"Abstract|Introduction|Background and Related Work|Construction|Security Model and Proof|Evaluation|Discussion and Limitations|Conclusion|Whole manuscript","severity":"blocker|major|minor","rationale":"specific reason grounded in artifacts","suggested_action":"specific rewrite instruction","authority_class":"author_feedback|claim_safety|proof_preservation|benchmark_framing|citation_support|narrative_quality|meta_leakage","owner_category":"author|experiment|proof|bibliography|implementation"}]}
If the packet contains an unpromoted qa_loop_execution/operator_feedback_execution candidate_approval with candidate_progress.forward_progress=true, choose intent=approve_existing_candidate and include issue(s) whose source_artifact_role targets only that candidate approval source. Do not include extra diagnostic issues from stale candidate sources when approving. A historical approval whose candidate_sha256 already equals the packet manuscript_sha256 is not actionable; in that case choose generate_new_operator_candidate unless rejecting is safer.
PROMPT
  run_codex_last_message "operator_feedback_author_cycle_${cycle}" "$prompt" "$response" "$OPFB/operator-feedback-author.cycle-${cycle}.jsonl" "$OPFB/operator-feedback-author.cycle-${cycle}.stderr.log" "$OPFB/operator-feedback-author.cycle-${cycle}.exitcode" "gpt-5.5" "high"
  local rc=$?
  [[ "$rc" == "0" ]] || return "$rc"
  python3 - "$packet" "$response" "$feedback" <<'PY'
import json, re, sys
from pathlib import Path
from paperorchestra.fresh_smoke import normalize_operator_feedback_draft
packet_path, response_path, output_path = map(Path, sys.argv[1:4])
packet=json.loads(packet_path.read_text(encoding='utf-8'))
text=response_path.read_text(encoding='utf-8')
try:
    draft=json.loads(text)
except Exception:
    m=re.search(r'\{.*\}', text, re.S)
    draft=json.loads(m.group(0)) if m else {"issues": []}

payload=normalize_operator_feedback_draft(packet, draft)
output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
PY
  run_step "operator_import_cycle_${cycle}" "${CLI[@]}" import-operator-feedback --packet "$packet" --feedback "$feedback" --output "$OPFB/operator-feedback-imported.cycle-${cycle}.json" || return 1
  set +e
  run_step "operator_apply_cycle_${cycle}" "${CLI[@]}" apply-operator-feedback --imported-feedback "$OPFB/operator-feedback-imported.cycle-${cycle}.json" --quality-mode claim_safe --citation-evidence-mode web --require-compile --require-live-verification --max-supervised-iterations 1 --max-iterations "$MAX_ITER" "${PROVIDER[@]}" "${CITATION_PROVIDER[@]}" "${RUNTIME[@]}"
  rc=$?
  set -e
  preserve_operator_feedback_execution_cycle "$cycle" "$rc" || true
  return "$rc"
}

# Bootstrap evidence files early.
echo "# Timeline" > "$READABLE/timeline.md"
record_command_markdown
write_verdict "fail_preflight" '"preflight_not_completed"' 'null'
if [[ "$DRY_RUN_CONTRACT" == "1" ]]; then
  emit_dry_run_contract
  exit 0
fi
write_provider_wrapper

# Preflight before live budget.
run_step git_status git status --short --untracked-files=all || fail_now fail_preflight '"git_status"' '"logs/git_status.stderr.log"' 1
run_step git_head git rev-parse HEAD || fail_now fail_preflight '"git_head"' '"logs/git_head.stderr.log"' 1
run_step py_compile python3 -m py_compile paperorchestra/providers.py paperorchestra/critics.py paperorchestra/quality_loop_citation_support.py paperorchestra/cli.py paperorchestra/mcp_server.py paperorchestra/operator_feedback.py paperorchestra/ralph_bridge_state.py paperorchestra/ralph_bridge_handoff.py paperorchestra/quality_loop_history.py paperorchestra/fresh_smoke.py scripts/validate-fresh-smoke-lane-a.py scripts/validate-fresh-smoke-materials.py scripts/validate-fresh-smoke-evidence.py || fail_now fail_preflight '"py_compile"' '"logs/py_compile.stderr.log"' 1
run_step smoke_script_syntax bash -n scripts/live-smoke-claim-safe.sh scripts/pre-live-check.sh scripts/fresh-full-live-smoke-loop.sh || fail_now fail_preflight '"smoke_script_syntax"' '"logs/smoke_script_syntax.stderr.log"' 1
run_step unittest bash -c 'run_without_papero_env "$@"' bash "$REPO_ROOT" python3 -m unittest discover -s tests -q || fail_now fail_preflight '"unittest"' '"logs/unittest.stderr.log"' 1
run_step pre_live_all bash -c 'run_without_papero_env "$@"' bash "$REPO_ROOT" bash scripts/pre-live-check.sh --all || fail_now fail_preflight '"pre_live_all"' '"logs/pre_live_all.stderr.log"' 1
run_step release_safety_scan_preflight run_release_safety_scan "$EVIDENCE_ROOT" "$ARTIFACTS/release-safety-scan.preflight.json" || fail_now fail_preflight '"release_safety_scan_preflight"' '"artifacts/release-safety-scan.preflight.json"' 1

# Material invariance.
mkdir -p .omx/state
printf '%s' "$MATERIAL_ROOT" > .omx/state/current-fresh-smoke-materials-root
run_step material_invariance python3 scripts/validate-fresh-smoke-materials.py "$MATERIAL_ROOT" --output "$ARTIFACTS/material-invariance.json" || {
  MATERIAL_INVARIANCE_STATUS="fail"
  fail_now fail_material_invariance '"material_invariance"' '"artifacts/material-invariance.json"' 1
}
MATERIAL_INVARIANCE_STATUS="pass"
cp "$MATERIAL_ROOT/inputs/material-manifest.json" "$EVIDENCE_ROOT/evidence-only/material-manifest.original.json"
cp "$MATERIAL_ROOT/review/all-files.sha256" "$EVIDENCE_ROOT/evidence-only/all-files.sha256"
cp "$MATERIAL_ROOT/review/material-validation.json" "$EVIDENCE_ROOT/evidence-only/material-validation.json" 2>/dev/null || true
cp "$MATERIAL_ROOT/review/external-review-manifest.json" "$EVIDENCE_ROOT/evidence-only/external-review-manifest.json" 2>/dev/null || true
cp "$MATERIAL_ROOT/materials/"*.tex "$EVIDENCE_ROOT/inputs-materials/"
cp "$MATERIAL_ROOT/policy/material-boundary.md" "$EVIDENCE_ROOT/inputs-materials/material-boundary.md"
run_step derive_fresh_inputs python3 scripts/derive-fresh-smoke-inputs.py "$EVIDENCE_ROOT" || fail_now fail_preflight '"derive_fresh_inputs"' '"logs/derive_fresh_inputs.stderr.log"' 1
mkdir -p "$EVIDENCE_ROOT/inputs"
cp "$WORKDIR/inputs/provenance-ledger.json" "$EVIDENCE_ROOT/inputs/provenance-ledger.json"
cp "$WORKDIR/inputs/redacted-material-manifest.json" "$EVIDENCE_ROOT/inputs/redacted-material-manifest.json" 2>/dev/null || true
python3 - "$EVIDENCE_ROOT" > "$EVIDENCE_ROOT/inputs.sha256" <<'PY'
import hashlib, sys
from pathlib import Path
root=Path(sys.argv[1])
for base in [root/'workdir'/'inputs', root/'inputs-materials', root/'evidence-only']:
    for p in sorted(base.rglob('*')):
        if p.is_file(): print(hashlib.sha256(p.read_bytes()).hexdigest(), p.relative_to(root))
PY

cd "$WORKDIR"
run_step init "${CLI[@]}" init --idea inputs/idea.tex --experimental-log inputs/experimental_log.tex --template inputs/template.tex --guidelines inputs/guidelines.md --figures-dir inputs/figures --venue "TDSC-style systems/security paper" --page-limit 12 --cutoff-date 2026-04-01 || fail_now fail_execution_error '"init"' '"logs/init.stderr.log"' 1
run_step import_reference_metadata_seed "${CLI[@]}" import-prior-work --seed-file inputs/reference_metadata_seed.bib --source metadata_seed_for_live_verification || fail_now fail_execution_error '"import_reference_metadata_seed"' '"logs/import_reference_metadata_seed.stderr.log"' 1
run_step research_prior_work "${CLI[@]}" research-prior-work --source "fresh material smoke" --import "${PROVIDER[@]}" "${RUNTIME[@]}" || fail_now fail_execution_error '"research_prior_work"' '"logs/research_prior_work.stderr.log"' 1
run_step verify_papers_live "${CLI[@]}" verify-papers --mode live --on-error skip || fail_now fail_execution_error '"verify_papers_live"' '"logs/verify_papers_live.stderr.log"' 1
printf 'write_live_verification_summary\n' > "$LOGS/live_verification_provenance.command"
set +e
write_live_verification_summary > "$LOGS/live_verification_provenance.stdout.log" 2> "$LOGS/live_verification_provenance.stderr.log"
LIVE_PROVENANCE_RC=$?
set -e
printf '%s\n' "$LIVE_PROVENANCE_RC" > "$LOGS/live_verification_provenance.exitcode"
COMMAND_ROWS+=("live_verification_provenance|${LIVE_PROVENANCE_RC}")
record_command_markdown
[[ "$LIVE_PROVENANCE_RC" == "0" ]] || fail_now fail_execution_error '"live_verification_provenance"' '"logs/live_verification_provenance.stderr.log"' 1
run_step build_bib "${CLI[@]}" build-bib || fail_now fail_execution_error '"build_bib"' '"logs/build_bib.stderr.log"' 1
run_step outline "${CLI[@]}" outline "${PROVIDER[@]}" "${RUNTIME[@]}" || fail_now fail_execution_error '"outline"' '"logs/outline.stderr.log"' 1
run_step generate_plots "${CLI[@]}" generate-plots "${PROVIDER[@]}" "${RUNTIME[@]}" || fail_now fail_execution_error '"generate_plots"' '"logs/generate_plots.stderr.log"' 1
run_step plan_narrative "${CLI[@]}" plan-narrative "${PROVIDER[@]}" "${RUNTIME[@]}" || fail_now fail_execution_error '"plan_narrative"' '"logs/plan_narrative.stderr.log"' 1
run_step write_intro_related "${CLI[@]}" write-intro-related "${PROVIDER[@]}" "${RUNTIME[@]}" --claim-safe || fail_now fail_execution_error '"write_intro_related"' '"logs/write_intro_related.stderr.log"' 1
run_step write_sections "${CLI[@]}" write-sections "${PROVIDER[@]}" "${RUNTIME[@]}" --claim-safe || fail_now fail_execution_error '"write_sections"' '"logs/write_sections.stderr.log"' 1
run_step compile_initial "${CLI[@]}" compile || { scan_meta_leakage || true; fail_now fail_execution_error '"compile_initial"' '"logs/compile_initial.stderr.log"' 1; }
scan_meta_leakage || fail_now fail_meta_leakage '"meta_leakage"' '"artifacts/meta-leakage-scan.json"' 1
run_step review "${CLI[@]}" review "${PROVIDER[@]}" "${RUNTIME[@]}" || fail_now fail_execution_error '"review"' '"logs/review.stderr.log"' 1
run_step review_sections_initial "${CLI[@]}" review-sections --output "$ARTIFACTS/section_review.initial.json" || fail_now fail_execution_error '"review_sections_initial"' '"logs/review_sections_initial.stderr.log"' 1
run_step review_figure_placement_initial "${CLI[@]}" review-figure-placement --output "$ARTIFACTS/figure_placement_review.initial.json" || fail_now fail_execution_error '"review_figure_placement_initial"' '"logs/review_figure_placement_initial.stderr.log"' 1
run_step review_citations_web_initial "${CLI[@]}" review-citations --evidence-mode web "${WEB_PROVIDER[@]}" || fail_now fail_execution_error '"review_citations_web_initial"' '"logs/review_citations_web_initial.stderr.log"' 1
copy_session_artifacts
[[ -f "$ARTIFACTS/citation_support_review.json" ]] && cp "$ARTIFACTS/citation_support_review.json" "$ARTIFACTS/citation_support_review.initial.json" || true
[[ -f "$ARTIFACTS/citation_support_review.trace.json" ]] && cp "$ARTIFACTS/citation_support_review.trace.json" "$ARTIFACTS/citation_support_review.initial.trace.json" || true
run_step build_source_obligations "${CLI[@]}" build-source-obligations --output "$ARTIFACTS/source_obligations.json" || fail_now fail_execution_error '"build_source_obligations"' '"logs/build_source_obligations.stderr.log"' 1
run_step validate_current "${CLI[@]}" validate-current --output "$ARTIFACTS/validation.current.json" || fail_now fail_execution_error '"validate_current"' '"logs/validate_current.stderr.log"' 1

FINAL="continue"; STEP_RC=10; LOOP_STOP_REASON="max_iterations_exhausted"
for iter in $(seq 1 "$MAX_ITER"); do
  run_step "quality_eval_iter_${iter}" "${CLI[@]}" quality-eval --quality-mode claim_safe --max-iterations "$MAX_ITER" --require-live-verification --output "$ARTIFACTS/quality-eval.iter-${iter}.json" --record-history || fail_now fail_execution_error '"quality_eval"' '"logs/quality_eval.stderr.log"' 1
  cp "$ARTIFACTS/quality-eval.iter-${iter}.json" "$ARTIFACTS/quality-eval.json"
  run_step "qa_loop_plan_iter_${iter}" "${CLI[@]}" qa-loop-plan --quality-mode claim_safe --max-iterations "$MAX_ITER" --require-live-verification --quality-eval "$ARTIFACTS/quality-eval.iter-${iter}.json" --output "$ARTIFACTS/qa-loop.plan.iter-${iter}.json" || fail_now fail_execution_error '"qa_loop_plan"' '"logs/qa_loop_plan.stderr.log"' 1
  cp "$ARTIFACTS/qa-loop.plan.iter-${iter}.json" "$ARTIFACTS/qa-loop.plan.json"
  set +e
  run_step "qa_loop_step_iter_${iter}" "${CLI[@]}" qa-loop-step --quality-mode claim_safe --max-iterations "$MAX_ITER" --require-compile --citation-evidence-mode web --require-live-verification "${PROVIDER[@]}" "${CITATION_PROVIDER[@]}" "${RUNTIME[@]}"
  STEP_RC=$?
  set -e
  case "$STEP_RC" in
    0) FINAL="ready_for_human_finalization"; LOOP_STOP_REASON="ready_for_human_finalization"; QA_LOOP_TERMINAL_VERDICT='"ready_for_human_finalization"'; QA_LOOP_TERMINAL_EXIT_CODE=0; break ;;
    10) FINAL="continue"; QA_LOOP_TERMINAL_VERDICT='"continue"'; QA_LOOP_TERMINAL_EXIT_CODE=10 ;;
    20)
      FINAL="human_needed"; QA_LOOP_TERMINAL_VERDICT='"human_needed"'; QA_LOOP_TERMINAL_EXIT_CODE=20
      copy_session_artifacts
      scan_meta_leakage || fail_now fail_meta_leakage '"meta_leakage"' '"artifacts/meta-leakage-scan.json"' 1
      current_plan_verdict="$(current_qa_plan_verdict)"
      if [[ "$current_plan_verdict" == "failed" ]]; then
        LOOP_STOP_REASON="iteration_budget_exhausted_after_operator_feedback"
        break
      fi
      if [[ "$OPERATOR_FEEDBACK_CYCLES" -ge "$MAX_OPERATOR_CYCLES" ]]; then
        LOOP_STOP_REASON="operator_cycle_cap_reached"
        break
      fi
      OPERATOR_FEEDBACK_CYCLES=$((OPERATOR_FEEDBACK_CYCLES + 1))
      write_operator_feedback "$OPERATOR_FEEDBACK_CYCLES" || fail_now fail_loop_feedback_not_reflected '"operator_feedback"' "\"operator-feedback/operator-feedback.cycle-${OPERATOR_FEEDBACK_CYCLES}.json\"" 1
      copy_session_artifacts
      FINAL="continue"; STEP_RC=10; QA_LOOP_TERMINAL_VERDICT='"continue"'; QA_LOOP_TERMINAL_EXIT_CODE=10
      ;;
    30) FINAL="failed"; LOOP_STOP_REASON="qa_loop_failed"; QA_LOOP_TERMINAL_VERDICT='"failed"'; QA_LOOP_TERMINAL_EXIT_CODE=30; break ;;
    40) FINAL="execution_error"; LOOP_STOP_REASON="qa_loop_execution_error"; QA_LOOP_TERMINAL_VERDICT='"execution_error"'; QA_LOOP_TERMINAL_EXIT_CODE=40; break ;;
    *) FINAL="unknown_exit_${STEP_RC}"; LOOP_STOP_REASON="unknown_exit"; QA_LOOP_TERMINAL_VERDICT="\"${FINAL}\""; QA_LOOP_TERMINAL_EXIT_CODE="$STEP_RC"; break ;;
  esac
  copy_session_artifacts
  scan_meta_leakage || fail_now fail_meta_leakage '"meta_leakage"' '"artifacts/meta-leakage-scan.json"' 1
done

copy_session_artifacts
case "$FINAL" in
  continue)
    scan_meta_leakage || fail_now fail_meta_leakage '"meta_leakage"' '"artifacts/meta-leakage-scan.json"' 1
    set +e
    run_step validate_fresh_smoke_lane_a python3 "$REPO_ROOT/scripts/validate-fresh-smoke-lane-a.py" "$EVIDENCE_ROOT" --output "$ARTIFACTS/fresh-smoke-lane-a-acceptance.json"
    lane_rc=$?
    set -e
    [[ "$lane_rc" == "0" ]] && LANE_A_STATUS="pass" || LANE_A_STATUS="fail"
    printf '%s\n' "$FINAL" > "$EVIDENCE_ROOT/final-smoke-status.txt"
    printf '%s\n' "$STEP_RC" > "$EVIDENCE_ROOT/final-smoke-exit-code.txt"
    fail_now fail_loop_feedback_not_reflected '"max_iterations_exhausted_with_continue"' '"readable/verdict.json"' 1
    ;;
  failed|execution_error|unknown_exit_*)
    scan_meta_leakage || fail_now fail_meta_leakage '"meta_leakage"' '"artifacts/meta-leakage-scan.json"' 1
    set +e
    run_step validate_fresh_smoke_lane_a python3 "$REPO_ROOT/scripts/validate-fresh-smoke-lane-a.py" "$EVIDENCE_ROOT" --output "$ARTIFACTS/fresh-smoke-lane-a-acceptance.json"
    lane_rc=$?
    set -e
    [[ "$lane_rc" == "0" ]] && LANE_A_STATUS="pass" || LANE_A_STATUS="fail"
    printf '%s\n' "$FINAL" > "$EVIDENCE_ROOT/final-smoke-status.txt"
    printf '%s\n' "$STEP_RC" > "$EVIDENCE_ROOT/final-smoke-exit-code.txt"
    fail_now fail_execution_error '"qa_loop_terminal"' '"readable/verdict.json"' 1
    ;;
esac

run_step compile_final "${CLI[@]}" compile || true
run_step review_sections_final "${CLI[@]}" review-sections --output "$ARTIFACTS/section_review.final.json" || true
run_step review_citations_web_final "${CLI[@]}" review-citations --evidence-mode web "${WEB_PROVIDER[@]}" --output "$ARTIFACTS/citation_support_review.final.json" || true
run_step review_figure_placement_final "${CLI[@]}" review-figure-placement --output "$ARTIFACTS/figure_placement_review.final.json" || true
run_step quality_eval_final "${CLI[@]}" quality-eval --quality-mode claim_safe --max-iterations "$MAX_ITER" --require-live-verification --output "$ARTIFACTS/quality-eval.final.json" --record-history || true
derive_final_quality_status
run_step qa_loop_plan_final "${CLI[@]}" qa-loop-plan --quality-mode claim_safe --max-iterations "$MAX_ITER" --require-live-verification --quality-eval "$ARTIFACTS/quality-eval.final.json" --output "$ARTIFACTS/qa-loop.plan.final.json" || true
[[ -f "$ARTIFACTS/quality-eval.final.json" ]] && cp "$ARTIFACTS/quality-eval.final.json" "$ARTIFACTS/quality-eval.json" || true
[[ -f "$ARTIFACTS/qa-loop.plan.final.json" ]] && reconcile_final_qa_plan_with_terminal_state || true
run_step ralph_start_dry_run "${CLI[@]}" ralph-start --quality-mode claim_safe --max-iterations "$MAX_ITER" --require-live-verification --evidence-root "$EVIDENCE_ROOT" --dry-run --output "$ARTIFACTS/ralph-brief.from-start.md" || true
copy_session_artifacts
[[ -f "$ARTIFACTS/qa-loop.plan.final.json" ]] && reconcile_final_qa_plan_with_terminal_state || true
scan_meta_leakage || fail_now fail_meta_leakage '"meta_leakage"' '"artifacts/meta-leakage-scan.json"' 1
run_step validate_fresh_smoke_lane_a python3 "$REPO_ROOT/scripts/validate-fresh-smoke-lane-a.py" "$EVIDENCE_ROOT" --output "$ARTIFACTS/fresh-smoke-lane-a-acceptance.json" || {
  LANE_A_STATUS="fail"
  fail_now fail_lane_a_predicate '"lane_a"' '"artifacts/fresh-smoke-lane-a-acceptance.json"' 1
}
LANE_A_STATUS="pass"


case "$FINAL" in
  ready_for_human_finalization) ;;
  human_needed)
    if [[ "$OPERATOR_FEEDBACK_CYCLES" -lt 1 ]]; then
      fail_now fail_loop_feedback_not_reflected '"human_needed_without_operator_cycle"' '"readable/verdict.json"' 1
    fi
    ;;
  continue)
    fail_now fail_loop_feedback_not_reflected '"max_iterations_exhausted_with_continue"' '"readable/verdict.json"' 1
    ;;
  failed|execution_error|unknown_exit_*)
    fail_now fail_execution_error '"qa_loop_terminal"' '"readable/verdict.json"' 1
    ;;
  *)
    fail_now fail_execution_error '"qa_loop_terminal_unknown"' '"readable/verdict.json"' 1
    ;;
esac

printf '%s
' "$FINAL" > "$EVIDENCE_ROOT/final-smoke-status.txt"
printf '%s
' "$STEP_RC" > "$EVIDENCE_ROOT/final-smoke-exit-code.txt"
write_verdict fail_critic_reject '"critic_not_run_yet"' 'null'
make_manifest
python3 "$REPO_ROOT/scripts/validate-fresh-smoke-evidence.py" "$EVIDENCE_ROOT" --output "$ARTIFACTS/evidence-completeness.json" || {
  EVIDENCE_COMPLETENESS_STATUS="fail"
  fail_now fail_evidence_incomplete '"evidence_completeness"' '"artifacts/evidence-completeness.json"' 1
}
EVIDENCE_COMPLETENESS_STATUS="pass"
write_verdict fail_critic_reject '"critic_not_run_yet"' 'null'
# Re-run evidence completeness before the Critic so the Critic reviews the actual machine report.
make_manifest
python3 "$REPO_ROOT/scripts/validate-fresh-smoke-evidence.py" "$EVIDENCE_ROOT" --output "$ARTIFACTS/evidence-completeness.json" || {
  EVIDENCE_COMPLETENESS_STATUS="fail"
  fail_now fail_evidence_incomplete '"evidence_completeness_pre_critic"' '"artifacts/evidence-completeness.json"' 1
}

cat > "$CRITIC/q1-loop-critic.prompt.md" <<PROMPT
You are a strict system-loop Critic for a PaperOrchestra fresh full live smoke. Evaluate the system test, not whether the manuscript is camera-ready. Cite artifact paths and line/JSON fields where possible.

You are producing the terminal critic response now, so do not reject merely because the q1_loop_critic response/exit artifacts are not present in the evidence bundle at prompt time. Evaluate all prior smoke artifacts, and start your response with exactly one machine-readable line:
SYSTEM_TEST_VERDICT: PASS
or
SYSTEM_TEST_VERDICT: REJECT

Required verdicts:
1. loop mechanics
2. evidence completeness
3. meta/process leakage
4. feedback incorporation or correct rejection
5. Lane A predicate interpretation
6. explicit distinction between manuscript draft-quality caveats and system-test failures

Evidence root: $EVIDENCE_ROOT
Verdict JSON: $READABLE/verdict.json
Material invariance: $ARTIFACTS/material-invariance.json
Evidence completeness: $ARTIFACTS/evidence-completeness.json
Lane A: $ARTIFACTS/fresh-smoke-lane-a-acceptance.json
Manuscript TeX/PDF text: $ARTIFACTS/paper.full.tex / $ARTIFACTS/paper.full.txt
Operator feedback: $OPFB
PROMPT
echo "==> q1_loop_critic"
write_timeline "- $(date -u +%Y-%m-%dT%H:%M:%SZ) start q1_loop_critic"
printf '%q ' codex exec --skip-git-repo-check -C "$REPO_ROOT" -m gpt-5.5 -c 'model_reasoning_effort="high"' --output-last-message "$CRITIC/q1-loop-critic.response.md" - > "$LOGS/q1_loop_critic.command"
printf '\n' >> "$LOGS/q1_loop_critic.command"
set +e
run_codex_last_message "q1_loop_critic" "$CRITIC/q1-loop-critic.prompt.md" "$CRITIC/q1-loop-critic.response.md" "$LOGS/q1_loop_critic.stdout.log" "$LOGS/q1_loop_critic.stderr.log" "$LOGS/q1_loop_critic.exitcode" "gpt-5.5" "high"
q1_rc=$?
set -e
COMMAND_ROWS+=("q1_loop_critic|${q1_rc}")
record_command_markdown
write_timeline "- $(date -u +%Y-%m-%dT%H:%M:%SZ) end q1_loop_critic rc=$q1_rc"
[[ "$q1_rc" == "0" ]] || {
  CRITIC_VERDICT="fail"
  fail_now fail_critic_reject '"critic"' '"logs/q1_loop_critic.stderr.log"' 1
}
if ! python3 - "$CRITIC/q1-loop-critic.response.md" <<'PY'
import re, sys
from pathlib import Path
text = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
head = text[:4000]
patterns = [
    r"(?im)^\s*SYSTEM_TEST_VERDICT\s*:\s*(PASS|REJECT|FAIL)\s*$",
    r"(?im)^\s*(?:overall\s+)?verdict\s*:\s*(PASS|APPROVE|APPROVED|REJECT|FAIL)\b",
]
verdict = None
for pattern in patterns:
    match = re.search(pattern, head)
    if match:
        verdict = match.group(1).lower()
        break
if verdict is None:
    if re.search(r"(?im)^\s*(reject|fail)\b|overall\s+verdict\s*:\s*reject|reject\s+this\s+as\s+a\s+fresh", head):
        verdict = "reject"
    elif re.search(r"(?im)^\s*(approve|pass)\b", head):
        verdict = "pass"
if verdict in {"pass", "approve", "approved"}:
    raise SystemExit(0)
raise SystemExit(1)
PY
then
  CRITIC_VERDICT="fail"
  fail_now fail_critic_reject '"critic_rejected"' '"critic/q1-loop-critic.response.md"' 1
fi
CRITIC_VERDICT="pass"
[[ -f "$ARTIFACTS/qa-loop.plan.final.json" ]] && reconcile_final_qa_plan_with_terminal_state || true
write_verdict pass_loop_verified 'null' 'null'
make_manifest
python3 "$REPO_ROOT/scripts/validate-fresh-smoke-evidence.py" "$EVIDENCE_ROOT" --output "$ARTIFACTS/evidence-completeness.json" || {
  EVIDENCE_COMPLETENESS_STATUS="fail"
  fail_now fail_evidence_incomplete '"evidence_completeness_post_critic"' '"artifacts/evidence-completeness.json"' 1
}
EVIDENCE_COMPLETENESS_STATUS="pass"
run_step release_safety_scan_final run_release_safety_scan "$EVIDENCE_ROOT" "$ARTIFACTS/release-safety-scan.final.json" || fail_now fail_preflight '"release_safety_scan_final"' '"artifacts/release-safety-scan.final.json"' 1
write_verdict pass_loop_verified 'null' 'null'
make_manifest
echo "Fresh full live smoke PASS: loop verified"
echo "Evidence: $EVIDENCE_ROOT"
exit 0
