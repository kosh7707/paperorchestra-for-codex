#!/usr/bin/env bash
set -euo pipefail

# Feature-by-feature pre-live verification before spending a full live-smoke run.
# Defaults are deterministic and do not require network/model calls.
# Use --live-s2 for one tiny Semantic Scholar live resolver probe.

usage() {
  cat <<'EOF'
Usage: scripts/pre-live-check.sh [--fast] [--full] [--live-s2] [--all]

Modes:
  --fast     Feature-matrix checks only (default). No network/model calls.
  --full     Include full unittest discovery after the feature matrix.
  --live-s2  Include a tiny live S2 resolver probe using .env/SEMANTIC_SCHOLAR_API_KEY.
  --all      Same as --full --live-s2.

Feature groups covered by --fast:
  environment_docs        docs/env/CLI readiness and this script's own guardrails
  provider_runtime        shell provider, request knobs, OMX bridge/control behavior
  s2_wrapper              S2 API wrapper, retry, timeout, fallback, cache, resolver
  literature_discovery    search-grounded candidate discovery and seed preservation
  live_verification       verify-papers live registry/map/dedup/error-policy behavior
  source_planning         narrative/claim/citation planning and source-material guards
  validation_review       extraction, validation, figure, section/citation critic checks
  quality_loop            tiered quality eval, QA/Ralph repair loop, audit gates
  omx_ralph_integration   actual omx CLI availability plus Ralph handoff/strict OMX tests
  eval_surfaces           benchmark/eval/reference comparison surfaces
  guided_intake           guided intake, evidence path safety, prior-work enrichment
  prompt_fidelity         prompt asset contracts and anti-leakage semantics
  citation_session        BibTeX, cutoff, citation key, session boundary checks
  strict_smoke_policy     executable claim-safe smoke surface covers the full critic stack

This script never prints SEMANTIC_SCHOLAR_API_KEY. Logs are written under
review/pre-live-check-<UTC timestamp>/.
EOF
}

RUN_FULL=0
RUN_LIVE_S2=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --fast) ;;
    --full) RUN_FULL=1 ;;
    --live-s2) RUN_LIVE_S2=1 ;;
    --all) RUN_FULL=1; RUN_LIVE_S2=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="review/pre-live-check-${TS}"
mkdir -p "$OUT/logs"

# Load local env quietly. .env is gitignored and may contain secrets.
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi
export PAPERO_ALLOWED_PROVIDER_BINARIES="${PAPERO_ALLOWED_PROVIDER_BINARIES:-codex,bash,python3}"

run_step() {
  local name="$1"; shift
  echo "==> $name"
  set +e
  "$@" >"$OUT/logs/${name}.stdout.log" 2>"$OUT/logs/${name}.stderr.log"
  local rc=$?
  set -e
  printf '%s\n' "$rc" >"$OUT/logs/${name}.exitcode"
  if [[ "$rc" -ne 0 ]]; then
    echo "FAILED: $name (exit=$rc)" >&2
    echo "stdout: $OUT/logs/${name}.stdout.log" >&2
    echo "stderr: $OUT/logs/${name}.stderr.log" >&2
    tail -120 "$OUT/logs/${name}.stderr.log" >&2 || true
    exit "$rc"
  fi
}

run_unittest_group() {
  local name="$1"; shift
  run_step "feature_${name}" env -u PAPERO_STRICT_CONTENT_GATES PYTHONDONTWRITEBYTECODE=1 python3 -m unittest "$@" -q
}

cat >"$OUT/README.md" <<EOF
# PaperOrchestra pre-live check

- started_at_utc: ${TS}
- repo: ${REPO_ROOT}
- run_full: ${RUN_FULL}
- run_live_s2: ${RUN_LIVE_S2}
- semantic_scholar_api_key_present: $([[ -n "${SEMANTIC_SCHOLAR_API_KEY:-}" ]] && echo true || echo false)

The key value is never printed.
EOF

cat >"$OUT/FEATURE_MATRIX.md" <<'EOF'
# Feature matrix

| Group | What it proves before live smoke |
| --- | --- |
| environment_docs | CLI/env/docs surfaces are parseable and operator instructions are not broken. |
| provider_runtime | Shell provider and OMX bridge failures/timeouts/request controls are bounded. |
| s2_wrapper | S2 wrapper rate-limit/retry/timeout/fallback/cache/resolver behavior is safe. |
| literature_discovery | Search-grounded discovery dedupes, cutoff-filters, and preserves exact seeds. |
| live_verification | S2 metadata becomes registry/citation_map; bad candidates are skipped/failed deterministically. |
| source_planning | Narrative/claim/citation planning artifacts exist and writing gates require them. |
| validation_review | Manuscript extraction, citation/numeric/figure validation, section/citation critics catch bad output. |
| quality_loop | Tiered eval and QA/Ralph bridge stop/continue/human-needed semantics hold. |
| omx_ralph_integration | Cheap real `omx` CLI probes pass; Ralph handoff and strict OMX tests are exercised. |
| eval_surfaces | Reference benchmark, citation partition, and review-gate comparison artifacts work. |
| guided_intake | Human intake and evidence-path safety checks are enforced. |
| prompt_fidelity | Prompt assets keep reconstruction semantics and anti-leakage constraints. |
| citation_session | BibTeX, cutoff, citation keys, and session boundary behavior are stable. |
| strict_smoke_policy | Executable claim-safe smoke script runs the full critic stack before live smoke is trusted. |
EOF

run_step compileall python3 -m compileall paperorchestra tests

run_step fresh_smoke_contract_dry_run bash -lc '
  tmp="$(mktemp -d)"
  cleanup_contract_tmp() { rm -rf "$tmp"; }
  trap cleanup_contract_tmp EXIT
  scripts/fresh-full-live-smoke-loop.sh --dry-run-contract --evidence-root "$tmp/evidence" > "$tmp/contract.json"
  python3 - "$tmp/contract.json" <<"PY_CONTRACT_CHECK"
import json, sys
from paperorchestra.providers import get_citation_support_provider, provider_supports_web_search
payload=json.load(open(sys.argv[1], encoding="utf-8"))
web_cmd=json.dumps(payload["provider_commands"]["web"])
provider=get_citation_support_provider("shell", command=web_cmd, evidence_mode="web")
assert provider_supports_web_search(provider)
contract=payload["provider_wrapper_contract"]
assert payload["codex_cli_prefix"] == ["codex"]
assert payload["critic_exec_argv_prefix"] == ["codex", "exec"]
assert contract["codex_cli_prefix"] == ["codex"]
assert contract["modes"]["web"]["trace_wrapped"] is True
assert contract["modes"]["web"]["web_search_capable"] is True
assert contract["modes"]["web"]["exec_argv_prefix"] == ["codex", "--search", "exec"]
assert any(item["name"] == "compile_initial" and item["class"] == "mandatory" for item in payload["stage_contracts"])
PY_CONTRACT_CHECK
'

run_step strict_smoke_policy python3 - <<'PY'
from pathlib import Path
script = Path("scripts/live-smoke-claim-safe.sh")
wrapper = Path("scripts/fresh-full-live-smoke-loop.sh")
if not script.exists():
    raise SystemExit("missing scripts/live-smoke-claim-safe.sh")
if not wrapper.exists():
    raise SystemExit("missing scripts/fresh-full-live-smoke-loop.sh")
text = script.read_text(encoding="utf-8") + "\n" + wrapper.read_text(encoding="utf-8")
required = [
    "validate-current",
    "build-source-obligations",
    "compile",
    "review --runtime-mode omx_native --strict-omx-native",
    "review-sections",
    "review-figure-placement",
    "review-citations --evidence-mode web",
    'quality-eval --quality-mode claim_safe --max-iterations "$MAX_ITERATIONS" --require-live-verification',
    'qa-loop-plan --quality-mode claim_safe --max-iterations "$MAX_ITERATIONS" --require-live-verification',
    "qa-loop-step",
    "--require-compile",
    "--citation-evidence-mode web",
    "validate-fresh-smoke-lane-a.py",
    "validate_fresh_smoke_lane_a",
    "fresh-smoke-lane-a-acceptance.json",
    "quality-eval.pre-step.json",
    "quality-eval.post-step.json",
    "final-verdict.txt",
    "fresh-full-live-smoke-loop.sh",
    "validate-fresh-smoke-materials.py",
    "validate-fresh-smoke-evidence.py",
    "fresh-smoke-verdict/1",
    "pass_loop_verified",
    "fail_material_invariance",
    "fail_evidence_incomplete",
    "operator-feedback",
]
missing = [token for token in required if token not in text]
if missing:
    raise SystemExit("strict smoke script missing required tokens: " + ", ".join(missing))
print("strict smoke policy surface present")
PY

run_step controlled_quality_gate_smoke python3 scripts/controlled-quality-gate-smoke.py

run_step omx_runtime_probe bash -lc 'command -v omx >/dev/null && command -v codex >/dev/null && omx --help >/dev/null && omx state list-active --json >/dev/null && omx ralph --help >/dev/null'

run_unittest_group environment_docs \
  tests.test_pre_live_check_script \
  tests.test_jobs_and_pipeline.PipelineTests.test_environment_inventory_and_cli_surface \
  tests.test_jobs_and_pipeline.PipelineTests.test_environment_docs_and_example_cover_operator_vars \
  tests.test_jobs_and_pipeline.PipelineTests.test_quickstart_cli_surface \
  tests.test_jobs_and_pipeline.PipelineTests.test_doctor_report_and_cli_surface

run_unittest_group provider_runtime \
  tests.test_jobs_and_pipeline.OmxBridgeTests.test_resolve_exec_timeout_rejects_invalid_values \
  tests.test_jobs_and_pipeline.OmxBridgeTests.test_resolve_exec_timeout_clamps_large_values \
  tests.test_jobs_and_pipeline.OmxBridgeTests.test_resolve_omx_model_and_reasoning_effort_from_environment \
  tests.test_jobs_and_pipeline.MockProviderTests.test_shell_provider_honors_optional_timeout \
  tests.test_jobs_and_pipeline.MockProviderTests.test_web_citation_provider_requires_global_codex_search_exec_shape \
  tests.test_jobs_and_pipeline.MockProviderTests.test_web_citation_provider_uses_codex_search_default_when_model_cmd_is_non_search \
  tests.test_jobs_and_pipeline.MockProviderTests.test_shell_provider_passes_request_knobs_via_environment_only_when_set \
  tests.test_jobs_and_pipeline.MockProviderTests.test_shell_provider_drops_invalid_ambient_request_knobs

run_unittest_group s2_wrapper tests.test_s2_api
run_unittest_group literature_discovery tests.test_literature_grounding

run_unittest_group live_verification \
  tests.test_jobs_and_pipeline.PipelineTests.test_verify_papers_live_success_uses_s2_metadata_and_citation_map \
  tests.test_jobs_and_pipeline.PipelineTests.test_verify_papers_live_filters_after_cutoff_and_deduplicates_paper_ids \
  tests.test_jobs_and_pipeline.PipelineTests.test_verify_papers_live_skips_candidate_errors_and_records_artifact \
  tests.test_jobs_and_pipeline.PipelineTests.test_verify_papers_live_preserves_existing_registry_when_skip_probe_regresses \
  tests.test_jobs_and_pipeline.PipelineTests.test_verify_papers_live_blocks_when_all_candidates_error \
  tests.test_jobs_and_pipeline.PipelineTests.test_verify_papers_live_fail_policy_raises_on_first_error \
  tests.test_jobs_and_pipeline.PipelineTests.test_run_pipeline_can_fallback_to_mock_verification_after_live_failure

run_unittest_group source_planning \
  tests.test_narrative_planning \
  tests.test_jobs_and_pipeline.PipelineTests.test_intro_related_allows_source_template_numbers_outside_rewrite_scope \
  tests.test_jobs_and_pipeline.PipelineTests.test_material_packet_sections_are_removed_but_macros_are_preserved \
  tests.test_jobs_and_pipeline.PipelineTests.test_expected_section_titles_from_outline_skips_meta_sections \
  tests.test_jobs_and_pipeline.PipelineTests.test_teach_bundle_preserves_source_preamble_and_bibliography_contract \
  tests.test_jobs_and_pipeline.PipelineTests.test_teach_bundle_inlines_local_preamble_inputs

run_unittest_group validation_review \
  tests.test_extraction_and_validation \
  tests.test_jobs_and_pipeline.PipelineTests.test_section_and_citation_critics_emit_actionable_artifacts \
  tests.test_jobs_and_pipeline.PipelineTests.test_model_citation_support_supported_requires_evidence_provenance \
  tests.test_jobs_and_pipeline.PipelineTests.test_web_citation_support_rejects_explicit_non_search_provider \
  tests.test_jobs_and_pipeline.PipelineTests.test_review_citations_cli_model_mode_writes_s2_independent_artifact \
  tests.test_pipeline_quality_and_operator_feedback.PipelineQualityAndOperatorFeedbackTests.test_section_and_citation_critic_cli_surfaces

run_unittest_group quality_loop \
  tests.test_audit_surface_invariants \
  tests.test_pipeline_quality_and_operator_feedback.PipelineQualityAndOperatorFeedbackTests.test_qa_loop_bridge_exit_codes_and_progress_delta \
  tests.test_pipeline_quality_and_operator_feedback.PipelineQualityAndOperatorFeedbackTests.test_qa_loop_step_runs_missing_citation_review_handler \
  tests.test_pipeline_quality_and_operator_feedback.PipelineQualityAndOperatorFeedbackTests.test_qa_loop_step_runs_tier0_precondition_refresh_handlers \
  tests.test_pipeline_quality_and_operator_feedback.PipelineQualityAndOperatorFeedbackTests.test_qa_loop_step_stops_on_unsupported_executable_action \
  tests.test_pipeline_quality_and_operator_feedback.PipelineQualityAndOperatorFeedbackTests.test_qa_loop_step_noops_on_terminal_human_needed_even_with_executable_action \
  tests.test_pipeline_quality_and_operator_feedback.PipelineQualityAndOperatorFeedbackTests.test_qa_loop_step_cli_passes_citation_provider_settings \
  tests.test_pipeline_quality_and_operator_feedback.PipelineQualityAndOperatorFeedbackTests.test_repair_citation_claims_restores_validation_pointer_on_compile_reject \
  tests.test_pipeline_quality_and_operator_feedback.PipelineQualityAndOperatorFeedbackTests.test_qa_loop_step_rolls_back_candidate_on_verification_exception

run_unittest_group omx_ralph_integration \
  tests.test_jobs_and_pipeline.OmxBridgeTests.test_run_omx_uses_control_timeout_and_reports_timeouts \
  tests.test_jobs_and_pipeline.OmxBridgeTests.test_run_omx_error_includes_returncode_when_outputs_are_empty \
  tests.test_jobs_and_pipeline.OmxBridgeTests.test_omx_exec_sends_large_prompt_over_stdin_not_argv \
  tests.test_jobs_and_pipeline.PipelineTests.test_strict_omx_native_disallows_python_fallback \
  tests.test_jobs_and_pipeline.PipelineTests.test_cli_strict_omx_native_returns_distinct_exit_code \
  tests.test_jobs_and_pipeline.PipelineTests.test_outline_cli_accepts_strict_omx_native_flag \
  tests.test_pipeline_quality_and_operator_feedback.PipelineQualityAndOperatorFeedbackTests.test_qa_loop_brief_contains_omx_handoff_and_no_success_verdict \
  tests.test_pipeline_quality_and_operator_feedback.PipelineQualityAndOperatorFeedbackTests.test_qa_loop_brief_prioritizes_executable_actions_over_human_needed_sidecars \
  tests.test_pipeline_quality_and_operator_feedback.PipelineQualityAndOperatorFeedbackTests.test_next_ralph_instruction_uses_supported_executable_action \
  tests.test_pipeline_quality_and_operator_feedback.PipelineQualityAndOperatorFeedbackTests.test_ralph_start_dry_run_cli_does_not_launch \
  tests.test_pipeline_quality_and_operator_feedback.PipelineQualityAndOperatorFeedbackTests.test_ralph_start_launch_calls_omx_ralph_explicitly

run_unittest_group eval_surfaces tests.test_eval
run_unittest_group guided_intake tests.test_guided_intake
run_unittest_group prompt_fidelity tests.test_prompt_fidelity
run_unittest_group citation_session tests.test_citation_and_session

run_step markdown_fence_check python3 - <<'PY'
from pathlib import Path
for name in ["README.md", "ENVIRONMENT.md"]:
    path = Path(name)
    if not path.exists():
        continue
    text = path.read_text(encoding="utf-8")
    fences = text.count("```")
    if fences % 2:
        raise SystemExit(f"{name}: unbalanced markdown code fences ({fences})")
    print(f"{name}: code fences balanced ({fences})")
PY
run_step secret_scan bash -lc "! grep -RInE --exclude='.env' --exclude-dir='.git' --exclude-dir='.omx' --exclude-dir='.paper-orchestra' --exclude-dir='__pycache__' 's2'\''k-[A-Za-z0-9]+|sk-(proj|live|test|svcacct)-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9]{32,}|Bearer[[:space:]]+[A-Za-z0-9._-]{20,}|api[_-]?key[[:space:]]*[:=][[:space:]]*[A-Za-z0-9_-]{16,}' README.md ENVIRONMENT.md NOTICE.md docs paperorchestra tests scripts examples pyproject.toml 2>/dev/null"
if [[ "${PAPERO_PRE_LIVE_DIFF_CHECK_IGNORE_MATERIAL_ROOT:-0}" == "1" ]]; then
  run_step diff_check git diff --check -- . ':(exclude,glob)examples/fresh-smoke-materials/**'
else
  run_step diff_check git diff --check
fi

if [[ "$RUN_FULL" -eq 1 ]]; then
  run_step full_unittest env PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
fi

if [[ "$RUN_LIVE_S2" -eq 1 ]]; then
  if [[ -z "${SEMANTIC_SCHOLAR_API_KEY:-}" ]]; then
    echo "SEMANTIC_SCHOLAR_API_KEY missing; cannot run --live-s2" >&2
    exit 20
  fi
  run_step live_s2_resolver_probe python3 - <<'PY'
from paperorchestra.literature import verify_candidate_title
from paperorchestra.s2_api import S2RetryPolicy, SemanticScholarClient
client = SemanticScholarClient(retry_policy=S2RetryPolicy(max_attempts=2))
paper = verify_candidate_title(
    "Attention Is All You Need",
    query_hint="Vaswani 2017 transformers",
    client=client,
    rate_limit_seconds=0,
)
if paper is None:
    raise SystemExit("S2 live resolver probe failed to verify canonical paper")
print("verified", bool(paper.paper_id), paper.year, paper.title_match_ratio)
PY
fi

cat >>"$OUT/README.md" <<EOF

## Completed

- completed_at_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)
- status: pass
EOF

echo "Pre-live check PASS"
echo "Evidence: $OUT"
