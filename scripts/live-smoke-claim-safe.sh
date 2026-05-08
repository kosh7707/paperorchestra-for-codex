#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/live-smoke-claim-safe.sh [--evidence-root DIR] [--max-iterations N]

Runs the strict full-stack claim-safe smoke gate for the current PaperOrchestra
session. This is not `paperorchestra run`; it assumes a draft/session already
exists and records every command, stdout/stderr, exit code, and final verdict.
EOF
}

EVIDENCE_ROOT=""
MAX_ITERATIONS=5
while [[ $# -gt 0 ]]; do
  case "$1" in
    --evidence-root) EVIDENCE_ROOT="$2"; shift 2 ;;
    --max-iterations) MAX_ITERATIONS="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
EVIDENCE_ROOT="${EVIDENCE_ROOT:-review/live-smoke-claim-safe-${TS}}"
mkdir -p "$EVIDENCE_ROOT/logs" "$EVIDENCE_ROOT/artifacts"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

export PAPERO_STRICT_CONTENT_GATES=1

run_step() {
  local name="$1"; shift
  echo "==> $name"
  printf '%q ' "$@" >"$EVIDENCE_ROOT/logs/${name}.command"
  printf '\n' >>"$EVIDENCE_ROOT/logs/${name}.command"
  set +e
  "$@" >"$EVIDENCE_ROOT/logs/${name}.stdout.log" 2>"$EVIDENCE_ROOT/logs/${name}.stderr.log"
  local rc=$?
  printf '%s\n' "$rc" >"$EVIDENCE_ROOT/logs/${name}.exitcode"
  return "$rc"
}

cat >"$EVIDENCE_ROOT/README.md" <<EOF
# Claim-safe live smoke evidence

- started_at_utc: ${TS}
- repo: ${REPO_ROOT}
- max_iterations: ${MAX_ITERATIONS}
- strict_content_gates: ${PAPERO_STRICT_CONTENT_GATES}
- semantic_scholar_api_key_present: $([[ -n "${SEMANTIC_SCHOLAR_API_KEY:-}" ]] && echo true || echo false)

This script never prints secret values.
EOF

run_required() {
  local name="$1"; shift
  if ! run_step "$name" "$@"; then
    echo "FAILED: $name" | tee "$EVIDENCE_ROOT/final-verdict.txt"
    exit "$(cat "$EVIDENCE_ROOT/logs/${name}.exitcode")"
  fi
}

run_required validate_current paperorchestra validate-current --output "$EVIDENCE_ROOT/artifacts/validation.current.json"
run_required build_source_obligations paperorchestra build-source-obligations --output "$EVIDENCE_ROOT/artifacts/source_obligations.json"
run_required compile paperorchestra compile
run_required review paperorchestra review --runtime-mode omx_native --strict-omx-native
run_required review_sections paperorchestra review-sections --output "$EVIDENCE_ROOT/artifacts/section_review.json"
run_required review_figure_placement paperorchestra review-figure-placement --output "$EVIDENCE_ROOT/artifacts/figure_placement_review.json"
run_required review_citations_web paperorchestra review-citations --evidence-mode web
citation_review_path="$(tail -n 1 "$EVIDENCE_ROOT/logs/review_citations_web.stdout.log" | tr -d '\r')"
if [[ -f "$citation_review_path" ]]; then
  cp "$citation_review_path" "$EVIDENCE_ROOT/artifacts/citation_support_review.json"
  citation_trace_path="${citation_review_path%.json}.trace.json"
  if [[ -f "$citation_trace_path" ]]; then
    cp "$citation_trace_path" "$EVIDENCE_ROOT/artifacts/citation_support_review.trace.json"
  fi
fi
run_required quality_eval paperorchestra quality-eval --quality-mode claim_safe --max-iterations "$MAX_ITERATIONS" --require-live-verification --output "$EVIDENCE_ROOT/artifacts/quality-eval.json"
run_required qa_loop_plan paperorchestra qa-loop-plan --quality-mode claim_safe --max-iterations "$MAX_ITERATIONS" --require-live-verification --quality-eval "$EVIDENCE_ROOT/artifacts/quality-eval.json" --output "$EVIDENCE_ROOT/artifacts/qa-loop.plan.json"
cp "$EVIDENCE_ROOT/artifacts/quality-eval.json" "$EVIDENCE_ROOT/artifacts/quality-eval.pre-step.json"

# qa-loop-step uses semantic exit codes: 0 ready, 10 continue, 20 human_needed,
# 30 failed, 40 execution_error. Record but do not let set -e hide the verdict.
set +e
run_step qa_loop_step paperorchestra qa-loop-step \
  --quality-mode claim_safe \
  --max-iterations "$MAX_ITERATIONS" \
  --provider shell \
  --runtime-mode omx_native \
  --strict-omx-native \
  --require-compile \
  --citation-evidence-mode web \
  --require-live-verification
STEP_RC=$?
set -e

refresh_session_artifacts() {
  if [[ ! -f .paper-orchestra/current_session.txt ]]; then
    return 0
  fi
  current_session="$(cat .paper-orchestra/current_session.txt)"
  current_run_root=".paper-orchestra/runs/${current_session}"
  current_artifacts=".paper-orchestra/runs/${current_session}/artifacts"
  if [[ -d "${current_artifacts}/prompts" ]]; then
    mkdir -p "$EVIDENCE_ROOT/artifacts/prompts"
    cp -R "${current_artifacts}/prompts/." "$EVIDENCE_ROOT/artifacts/prompts/"
  fi
  if [[ -d "${current_artifacts}/lane-manifests" ]]; then
    mkdir -p "$EVIDENCE_ROOT/artifacts/lane-manifests"
    cp -R "${current_artifacts}/lane-manifests/." "$EVIDENCE_ROOT/artifacts/lane-manifests/"
  fi
  if [[ -f "${current_artifacts}/provider-identity.json" ]]; then
    cp "${current_artifacts}/provider-identity.json" "$EVIDENCE_ROOT/artifacts/provider-identity.json"
  fi
  if [[ -f "${current_run_root}/qa-loop-history.jsonl" ]]; then
    cp "${current_run_root}/qa-loop-history.jsonl" "$EVIDENCE_ROOT/artifacts/qa-loop-history.jsonl"
  elif [[ -f ".paper-orchestra/qa-loop-history.jsonl" ]]; then
    cp ".paper-orchestra/qa-loop-history.jsonl" "$EVIDENCE_ROOT/artifacts/qa-loop-history.jsonl"
  fi
  for artifact in quality-eval.json qa-loop.plan.json validation.qa-loop-step.json citation_support_review.json citation_support_review.trace.json; do
    if [[ -f "${current_artifacts}/${artifact}" ]]; then
      cp "${current_artifacts}/${artifact}" "$EVIDENCE_ROOT/artifacts/${artifact}"
    fi
  done
  shopt -s nullglob
  for execution_artifact in "${current_run_root}"/qa-loop-execution.iter-*.json; do
    cp "$execution_artifact" "$EVIDENCE_ROOT/artifacts/$(basename "$execution_artifact")"
  done
  for candidate_artifact in \
    "${current_artifacts}/paper.citation-repair.candidate.tex" \
    "${current_artifacts}/validation.citation-repair.json" \
    "${current_artifacts}/validation.qa-loop-step.rollback.json" \
    "${current_artifacts}/validation.qa-loop-step.candidate-approved-original-restored.json"; do
    if [[ -f "$candidate_artifact" ]]; then
      cp "$candidate_artifact" "$EVIDENCE_ROOT/artifacts/$(basename "$candidate_artifact")"
    fi
  done
  shopt -u nullglob
  python3 - "$EVIDENCE_ROOT" "$REPO_ROOT" <<'PY'
import filecmp
import json
import re
import shutil
import sys
from pathlib import Path

evidence = Path(sys.argv[1]).resolve()
repo = Path(sys.argv[2]).resolve()
artifact_dir = evidence / "artifacts"
copied = []
missing = []
path_re = re.compile(r'(?:"path"|"quality_eval_path"|"qa_loop_plan_path"|"manuscript_path")\s*:\s*"([^"]+)"')
json_sources = sorted(path for path in artifact_dir.rglob("*.json") if path.name != "artifact-manifest.json")
for artifact_json in json_sources:
    try:
        text = artifact_json.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        continue
    for raw in path_re.findall(text):
        src = Path(raw)
        if not src.is_absolute():
            src = (repo / src).resolve()
        if src.exists() and src.is_file():
            dest_name = src.name
            dest_path = artifact_dir / dest_name
            if dest_path.exists() and not filecmp.cmp(src, dest_path, shallow=False):
                dest_name = src.parent.name + "." + src.name
                dest_path = artifact_dir / dest_name
            shutil.copy2(src, dest_path)
            copied.append({
                "referenced_by": f"artifacts/{artifact_json.relative_to(artifact_dir)}",
                "source": str(src),
                "artifact": f"artifacts/{dest_name}",
            })
        else:
            missing.append({
                "referenced_by": f"artifacts/{artifact_json.relative_to(artifact_dir)}",
                "source": raw,
                "reason": "not_found",
            })
manifest = {"schema_version": "smoke-evidence-manifest/1", "copied_referenced_artifacts": copied, "missing_referenced_artifacts": missing}
(evidence / "artifact-manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
PY
}

refresh_session_artifacts

bind_final_citation_review() {
  local name="$1"
  if [[ ! -f "$EVIDENCE_ROOT/artifacts/quality-eval.json" || ! -f "$EVIDENCE_ROOT/artifacts/citation_support_review.json" ]]; then
    return 0
  fi
  cp "$EVIDENCE_ROOT/artifacts/citation_support_review.json" "$EVIDENCE_ROOT/artifacts/citation_support_review.final.json"
  run_required "$name" python3 - "$EVIDENCE_ROOT/artifacts/quality-eval.json" "$EVIDENCE_ROOT/artifacts/citation_support_review.final.json" <<'PY'
import json
import sys
from paperorchestra.quality_loop_citation_support import ensure_final_citation_review_bound_to_quality_eval

result = ensure_final_citation_review_bound_to_quality_eval(sys.argv[1], sys.argv[2])
print(json.dumps(result, sort_keys=True))
PY
}

bind_final_citation_review pre_step_bind_final_citation_review

run_step validate_claim_safe_current paperorchestra validate-claim-safe-current --max-iterations "$MAX_ITERATIONS" --require-live-verification --output "$EVIDENCE_ROOT/artifacts/validation.claim-safe-current.json" || true
# validate-claim-safe-current regenerates fresh quality-eval and qa-loop-plan
# artifacts. Refresh again so README summaries and manifest links point at the
# post-step policy state rather than the pre-step plan.
refresh_session_artifacts
if [[ -f "$EVIDENCE_ROOT/artifacts/quality-eval.json" ]]; then
  cp "$EVIDENCE_ROOT/artifacts/quality-eval.json" "$EVIDENCE_ROOT/artifacts/quality-eval.post-step.json"
fi
bind_final_citation_review post_step_bind_final_citation_review

POST_STEP_PLAN_VERDICT=""
POST_STEP_PLAN_RATIONALE=""
if [[ -f "$EVIDENCE_ROOT/artifacts/qa-loop.plan.json" ]]; then
  POST_STEP_PLAN_VERDICT="$(
    python3 - "$EVIDENCE_ROOT/artifacts/qa-loop.plan.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
print(data.get("verdict") or "")
PY
  )"
  POST_STEP_PLAN_RATIONALE="$(
    python3 - "$EVIDENCE_ROOT/artifacts/qa-loop.plan.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
print(data.get("verdict_rationale") or "")
PY
  )"
fi

session_id=""
if [[ -f .paper-orchestra/current_session.txt ]]; then
  session_id="$(cat .paper-orchestra/current_session.txt)"
fi
OPERATOR_FEEDBACK_CYCLES="$(
  python3 - "$REPO_ROOT" "$session_id" <<'PY'
import sys
from pathlib import Path

repo = Path(sys.argv[1])
session_id = sys.argv[2].strip() or None
if session_id is None:
    print(0)
    raise SystemExit
from paperorchestra.quality_loop_history import operator_feedback_cycle_count
print(operator_feedback_cycle_count(repo, session_id=session_id))
PY
)"
cat >"$EVIDENCE_ROOT/artifacts/operator-feedback-cycle-count.json" <<EOF
{
  "schema_version": "operator-feedback-cycle-count/1",
  "source": "qa-loop-history.jsonl",
  "session_id": "${session_id}",
  "operator_feedback_cycles": ${OPERATOR_FEEDBACK_CYCLES}
}
EOF
run_required validate_fresh_smoke_lane_a python3 scripts/validate-fresh-smoke-lane-a.py "$EVIDENCE_ROOT" --output "$EVIDENCE_ROOT/artifacts/fresh-smoke-lane-a-acceptance.json"

case "$STEP_RC" in
  0) FINAL="ready_for_human_finalization" ;;
  10) FINAL="continue" ;;
  20) FINAL="human_needed" ;;
  30) FINAL="failed" ;;
  40) FINAL="execution_error" ;;
  *) FINAL="unknown_exit_${STEP_RC}" ;;
esac
printf '%s\n' "$FINAL" >"$EVIDENCE_ROOT/final-verdict.txt"
printf '%s\n' "$STEP_RC" >"$EVIDENCE_ROOT/final-exit-code.txt"
cat >>"$EVIDENCE_ROOT/README.md" <<EOF

## Completed

- completed_at_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)
- qa_loop_step_verdict: ${FINAL}
- qa_loop_step_exit_code: ${STEP_RC}
- operator_feedback_cycles: ${OPERATOR_FEEDBACK_CYCLES}
- post_step_plan_verdict: ${POST_STEP_PLAN_VERDICT:-unknown}
- post_step_plan_rationale: ${POST_STEP_PLAN_RATIONALE:-unknown}
- artifact_manifest: artifact-manifest.json
- prompt_traces: artifacts/prompts/
- lane_manifests: artifacts/lane-manifests/
- provider_identity: artifacts/provider-identity.json

Interpretation: qa_loop_step_verdict is the direct semantic exit from the bounded repair step. post_step_plan_verdict is the refreshed policy state after that step's validation/quality artifacts have been copied into this packet. If they differ, operators should treat the refreshed post-step plan as the current quality-loop policy state while preserving the step verdict as execution evidence.
EOF

echo "Claim-safe smoke verdict: $FINAL"
echo "Evidence: $EVIDENCE_ROOT"
exit "$STEP_RC"
