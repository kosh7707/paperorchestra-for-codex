# Slice AD mini-plan — figure gate and placeholder replacement evidence

Status: implemented and container-proven
Date: 2026-05-13
Branch: `orchestrator-v1-runtime`
Scope: public, domain-general figure inventory, slot matching, and placeholder replacement evidence. Do not include private smoke material, private-domain terms, or private figure names.

## 0. Pre-plan issue check

Required by the post-Z workflow plan before every slice mini-plan:

```bash
gh issue list --state open --json number,title,labels,updatedAt,url --limit 50
# []
```

No actionable open GitHub issue blocked Slice AD planning.

## 1. Target result

Slice AD hardens the figure side of final-readiness. A generated paper may contain
placeholder/generated plot assets even when the user supplied real figures. The
engine must inventory supplied assets, map figure slots to suitable assets where
safe, record a public-safe replacement report, and block or mark human-polish
when ambiguity remains.

This slice is general-purpose. It must not special-case private figure names or
assume a particular paper domain.

## 2. Current baseline

Existing surfaces:

- `paperorchestra/orchestra_figures.py`
  - `FigureAsset`, `FigureInventory`, `FigureSlot`, `FigureMatchDecision`,
    `FigureGatePolicy`;
  - current matching is filename-token based and records raw paths/filenames in
    internal dataclasses;
  - current report is not a complete public-safe replacement artifact.
- `paperorchestra/orchestra_state.py` and `paperorchestra/orchestra_policies.py`
  - `figures=placeholder_only` / `placeholder_figure_unresolved` already blocks
    ready-for-human-finalization.
- `paperorchestra/orchestra_loop.py` and `paperorchestra/orchestra_planner.py`
  - placeholder figures route to `match_supplied_figures` / blocking paths.
- `paperorchestra/pipeline.py`, `plot_assets.py`, and `validator.py`
  - generated placeholder plot assets and plot usage validation exist.
- Existing tests:
  - `tests/test_orchestra_figures.py` covers basic inventory/match/blocking;
  - `tests/test_orchestra_full_loop_planner.py` covers placeholder routing;
  - pipeline/validator tests cover generated plot asset usage.

Gaps:

- no single public-safe figure gate artifact maps supplied assets -> slots ->
  match/replacement decisions;
- no deterministic ambiguity handling for multiple plausible supplied assets;
- no public-safe redaction contract for private-looking figure filenames/paths;
- no CLI/MCP-accessible smoke surface for the figure gate;
- acceptance gate `supplied_figures_inventoried_matched_or_blocked` has no direct
  artifact to cite.

## 3. Implementation boundary

Extend `paperorchestra/orchestra_figures.py` rather than adding a large new
subsystem. Proposed additions:

```text
FIGURE_GATE_SCHEMA_VERSION = "figure-gate-report/1"
FigureAsset.to_public_dict()
FigureSlot.to_public_dict()
FigureMatchDecision.to_public_dict()
FigureGateReport.to_public_dict()
figure_gate_report_path(cwd)
build_figure_gate_report(cwd, *, figures_dir=None, plot_assets_path=None, plot_manifest_path=None)
write_figure_gate_report(cwd, *, figures_dir=None, output_path=None)
```

Default artifact path:

```text
figure_gate_report_path(cwd) -> artifact_path(cwd, "figure_gate.report.json")
```

Input priority/order:

1. current session if available;
2. explicit `figures_dir` argument, otherwise `state.inputs.figures_dir`;
3. `state.artifacts.plot_assets_json` for generated placeholder assets;
4. `state.artifacts.plot_manifest_json` for figure slots/captions;
5. `state.artifacts.plot_captions_json` only as a fallback source of slot text;
6. existing `latest_figure_placement_review_json` only as supporting status, not
   as a replacement for this gate.

Missing-session behavior:

- Library builder may accept explicit `figures_dir`, `plot_assets_path`,
  `plot_manifest_path`, and optional `plot_captions_path` for unit tests without
  a session.
- CLI command supports explicit non-session smoke inputs:
  `--figures-dir`, `--plot-assets`, `--plot-manifest`, and optional
  `--plot-captions`. If no session is present and slot sources are missing, CLI
  fails deterministically with a clear error instead of fabricating slots.

## 4. Public schema contract

The report should look like:

```json
{
  "schema_version": "figure-gate-report/1",
  "status": "pass | warn | fail | blocked",
  "summary": {
    "supplied_asset_count": 2,
    "slot_count": 1,
    "matched_slot_count": 1,
    "ambiguous_slot_count": 0,
    "missing_slot_count": 0,
    "placeholder_slot_count": 1
  },
  "decisions": [
    {
      "slot_id": "F1",
      "slot_label": "redacted-figure-slot:...",
      "status": "matched | ambiguous | missing | already_realized | human_finalization_needed",
      "selected_asset_label": "redacted-figure-asset:...",
      "selected_asset_sha256": "...",
      "candidate_asset_count": 1,
      "reasons": ["safe_token_match"],
      "replacement_proposed": true,
      "replacement_applied": false,
      "private_safe": true
    }
  ],
  "blocking_reasons": [],
  "acceptance_gate_impacts": {
    "supplied_figures_inventoried_matched_or_blocked": "pass | blocked | fail"
  },
  "private_safe_summary": true
}
```

Public report must not include:

- raw filenames that may contain private terms;
- raw absolute paths;
- raw figure captions or manuscript excerpts;
- raw user notes or private material;
- private markers or private-domain terms.

Allowed:

- stable redacted labels derived from hashes;
- asset SHA-256 hashes;
- bounded status/reason codes;
- counts and booleans.

Internal dataclasses may keep raw `path`/`filename` only for local matching and
file operations. Their `to_public_dict()` output must be redacted.

Important AD boundary: `status=pass` means the **matching gate is complete** and a
safe replacement has been proposed. It does **not** mean the manuscript/PDF was
mutated or that final output already uses the supplied figure. All AD decisions
must emit `replacement_applied=false`. Applying replacements to TeX/PDF is a
future separately tested slice unless the plan is explicitly revised.

Raw slot IDs are public only when they match a strict safe pattern such as
`^[A-Za-z][A-Za-z0-9_-]{0,31}$` and contain no private markers. Otherwise public
output must use a redacted slot label/hash and omit the raw ID.

## 5. Slot and match semantics

### 5.1 Figure inventory

- Inventory should accept `.pdf`, `.png`, `.jpg`, `.jpeg`, `.svg`.
- Inventory should be deterministic and sorted.
- Public inventory entries use labels/hashes, not raw filenames/paths.
- Missing figures directory is not a hard failure if no placeholder slots exist;
  it is a blocker if placeholder/generated slots remain.

### 5.2 Slot derivation

Slots are derived in this order:

1. generated placeholder entries in `plot_assets_json` with
   `asset_kind="generated_placeholder"` or equivalent placeholder marker;
2. figures in `plot_manifest_json` with `figure_id` / `caption` / `purpose`;
3. fallback slot from `plot_captions_json` when no manifest exists;
4. explicit `FigureSlot` passed by tests.

Slot public output must use slot IDs and hashes/redacted labels only. Captions are
used for matching tokens but not emitted raw.

### 5.3 Matching

A match is safe only when:

- exactly one supplied asset has sufficient token overlap with the slot purpose;
- token overlap is based on normalized alphanumeric tokens from slot purpose and
  filename stem;
- common stopwords and very short tokens are ignored;
- no private marker appears in public output.

Decision status split:

- `matched`: exactly one asset clears the safe threshold.
- `ambiguous`: more than one asset ties for best plausible score; reason
  `multiple_plausible_figure_matches`; no replacement proposal.
- `missing`: no asset clears the safe threshold; reason `figure_asset_missing`;
  no replacement proposal.
- `human_finalization_needed`: broader/manual-polish wrapper status may be used
  at report/blocking level, but individual decisions should prefer `ambiguous`
  or `missing` so operators know why automation stopped.

A matched decision may propose replacement but must still set
`replacement_applied=false` in AD. Ambiguous/missing decisions must not propose
replacement and should block final readiness or require human polish.

## 6. Integration points

Required:

1. Add CLI command, likely:

   ```bash
   paperorchestra audit-figure-gate [--figures-dir path] [--plot-assets path] [--plot-manifest path] [--plot-captions path] [--output path]
   ```

2. For AD, writing `figure_gate.report.json` under the session artifact directory
   satisfies artifact reachability. Export-bundle inclusion is a future enhancement
   unless implemented with an explicit test in this slice.

3. Keep existing `review-figure-placement` behavior green. AD adds a gate report;
   it must not remove existing figure placement review artifacts.

4. Ensure `FigureGatePolicy.apply_to_state` and/or planner behavior continues to
   block unresolved placeholders. If the new gate returns `matched`, it may set
   `figures=matched` only through a separately tested path; otherwise it records
   evidence and leaves state conservative.

5. Ensure acceptance-ledger gate
   `supplied_figures_inventoried_matched_or_blocked` can later cite this report.
   AC-style automatic ledger population is not required in AD.

## 7. Tests to add first

Update/add tests before implementation, mainly in `tests/test_orchestra_figures.py`
and CLI/export tests if needed.

Minimum failing tests:

1. Inventory public output redacts raw private-looking filenames and absolute
   paths while retaining SHA-256 and deterministic labels.
2. A generated placeholder slot plus one semantically matching supplied asset
   produces report `status=pass`, decision `matched`,
   `replacement_proposed=true`, and `replacement_applied=false`.
3. Ambiguous multiple supplied assets for one slot produce decision `ambiguous`,
   report blocker/human-polish status, and no replacement proposal.
4. Missing supplied asset for a placeholder slot produces decision `missing` with
   `placeholder_figure_unresolved` / `figure_asset_missing`.
5. Duplicate/non-placeholder/generated-realized slots do not create false
   blockers.
6. Public report JSON omits raw captions, raw filenames, raw slot IDs,
   absolute paths, private markers, and private-domain terms.
7. Private-looking `figure_id`, filename, and caption are redacted in public JSON.
8. CLI explicit non-session smoke path with `--figures-dir`, `--plot-assets`, and
   `--plot-manifest` writes a report; missing slot sources fail deterministically.
9. Existing placeholder state/readiness tests remain green.
10. Full-loop planner still routes unresolved placeholders to
    `match_supplied_figures` before compile/export.
11. AD does not promote readiness/final figure status and does not mutate TeX/PDF;
    it records `replacement_applied=false` only.
12. Artifact reachability is satisfied by writing `figure_gate.report.json` under
    the session artifact directory.

Existing tests that must remain green:

```bash
.venv/bin/python -m pytest tests/test_orchestra_figures.py \
  tests/test_orchestra_full_loop_planner.py \
  tests/test_orchestra_state_scenarios.py \
  tests/test_orchestrator_action_executor.py -q
```

## 8. Validation before implementation commit

Local:

```bash
.venv/bin/python -m pytest tests/test_orchestra_figures.py -q
.venv/bin/python -m pytest tests/test_orchestra_full_loop_planner.py \
  tests/test_orchestra_state_scenarios.py \
  tests/test_orchestrator_action_executor.py \
  tests/test_orchestrator_cli_entrypoints.py \
  tests/test_orchestrator_mcp_entrypoints.py -q
.venv/bin/python -m pytest -q
scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
grep -RIn "<private-domain literal>" $(git ls-files 'docs/**' 'paperorchestra/**' 'tests/**' 'skills/**' 'README.md' 'ENVIRONMENT.md') || true
git diff --check
```

Critic implementation validation is required before commit/push.

## 9. Container proof after push

After implementation commit is pushed:

```bash
docker run --rm paperorchestra-ubuntu-tools:24.04 bash -lc 'set -euo pipefail; \
  git clone --quiet https://github.com/kosh7707/paperorchestra-for-codex.git repo; \
  cd repo; \
  git checkout --quiet orchestrator-v1-runtime; \
  python3 -m venv .venv; \
  . .venv/bin/activate; \
  python -m pip install --quiet -e ".[dev]"; \
  python -m pytest tests/test_orchestra_figures.py \
    tests/test_orchestra_full_loop_planner.py \
    tests/test_orchestra_state_scenarios.py \
    tests/test_orchestrator_cli_entrypoints.py \
    tests/test_orchestrator_mcp_entrypoints.py -q'
```

Record proof in this plan or a follow-up evidence commit.

### Container proof recorded

Implementation commit:

```text
a2696e0 Block unresolved figure placeholders without mutating manuscripts
```

Fresh-container command used:

```bash
docker run --rm \
  -v /tmp/paperorchestra-private-denylist.txt:/tmp/paperorchestra-private-denylist.txt:ro \
  paperorchestra-ubuntu-tools:24.04 bash -lc 'set -euo pipefail
WORK=/tmp/paperorchestra-ad-proof
rm -rf "$WORK"
git clone --branch orchestrator-v1-runtime https://github.com/kosh7707/paperorchestra-for-codex.git "$WORK" >/tmp/git-clone.log
cd "$WORK"
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]" >/tmp/pip-install.log
python -m pytest tests/test_orchestra_figures.py -q
python -m pytest tests/test_orchestra_figures.py tests/test_orchestra_full_loop_planner.py tests/test_orchestra_state_scenarios.py tests/test_orchestrator_cli_entrypoints.py -q
scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
printf "HEAD=%s\n" "$(git rev-parse --short HEAD)"
'
```

Evidence:

```text
tests/test_orchestra_figures.py: 16 passed
figure/planner/state/CLI container subset: 50 passed, 2 subtests
private leakage scan: status ok, match_count 0
HEAD=a2696e0
```

Local verification before the implementation commit:

```text
tests/test_orchestra_figures.py: 16 passed
figure/planner/state/action/CLI/MCP subset: 99 passed, 22 subtests
full suite: 943 passed, 177 subtests
private leakage scan: status ok, match_count 0
Critic implementation validation: APPROVE
```

## 10. Explicit non-goals

Slice AD must not:

- call LLMs, web search, OMX, or live vision models;
- perform lossy image editing or generate new image content;
- add private-domain-specific figure filename rules;
- silently replace ambiguous figures;
- mark final output as submission-ready;
- delete existing figure placement review or plot asset behavior;
- require private material in public tests.

## 11. Stop/replan triggers

Stop and replan if:

- safe matching requires raw private captions/names in public artifacts;
- a placeholder can pass without inventory/match/block evidence;
- multiple plausible supplied assets are auto-selected without human polish;
- public report leaks raw filename/path/caption/private markers;
- implementation mutates generated TeX or PDF output without a separate tested
  replacement/apply plan;
- existing plot/figure pipeline tests would need broad rewrites.
