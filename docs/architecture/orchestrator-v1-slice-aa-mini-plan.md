# Slice AA mini-plan — acceptance ledger and completion-audit harness

Status: draft mini-plan requiring Critic validation before tests or implementation
Date: 2026-05-13
Branch: `orchestrator-v1-runtime`
Scope: public, domain-general acceptance ledger. Do not include private smoke material.

## 0. Pre-plan issue check

Required by the post-Z workflow plan before every slice mini-plan:

```bash
gh issue list --state open --limit 20 --json number,title,author,createdAt,updatedAt,labels,url
# []
```

No actionable open issue blocked Slice AA planning.

## 1. Target result

Add a machine-readable **Orchestrator v1 acceptance ledger** that maps each public
v1 acceptance gate to explicit evidence and a conservative status. This is a
completion-audit harness, not a readiness shortcut.

The ledger answers:

```text
Which v1 acceptance gates exist?
Which evidence currently supports each gate?
Which gates are pass/fail/blocked/unknown?
What is still missing before the active goal can be called complete?
```

## 2. Why AA comes before more runtime work

The active objective is broad and requires a completion audit against actual
evidence. Without a ledger, future slices can pass tests while leaving acceptance
gates unmapped. AA creates the non-proxy evidence surface that later slices must
update.

AA must not change manuscript generation, OMX execution behavior, readiness
policy, quality scoring, MCP attachment, citation logic, or figure handling.

## 3. Exact gate ID contract

AA locks these 19 gate IDs from `docs/architecture/orchestrator-v1-runtime-plan.md`
section 12:

1. `state_contract_tests`
2. `action_planner_scenario_tests`
3. `fake_omx_unit_contract_tests`
4. `real_bounded_omx_command_probes`
5. `mcp_raw_and_attach_smoke`
6. `mock_demo`
7. `compile_export`
8. `fresh_container_functional_smoke`
9. `private_final_live_smoke_redacted`
10. `private_leakage_scan`
11. `no_unsupported_critical_claims`
12. `no_unknown_refs_for_critical_claims`
13. `citation_integrity`
14. `supplied_figures_inventoried_matched_or_blocked`
15. `hard_gates_no_fail_except_human_polish`
16. `critic_consensus_near_ready_or_better`
17. `verifier_evidence_completeness_no_leakage`
18. `exported_pdf_tex_evidence_bundle`
19. `readme_environment_skill_docs_updated`

No gate may be renamed, dropped, or silently added in AA tests without an explicit
contract update.

## 4. Proposed implementation surface

Add a small module:

```text
paperorchestra/orchestra_acceptance.py
```

Public functions/classes:

```python
ACCEPTANCE_GATE_IDS: tuple[str, ...]
AcceptanceGate
AcceptanceLedger
build_acceptance_ledger(evidence: Mapping[str, Any] | None = None) -> AcceptanceLedger
render_acceptance_ledger_summary(ledger: AcceptanceLedger) -> str
```

Mandatory read-only CLI surface:

```bash
paperorchestra acceptance-ledger [--evidence <path>] [--json]
```

The CLI must remain read-only and must not infer pass from missing evidence. If
`--evidence` is omitted, every gate defaults to `unknown`. AA must not add
auto-detection; future auto-detection requires a separate plan and tests.

## 5. Evidence input contract

`build_acceptance_ledger(evidence=...)` accepts either `None` or a mapping keyed
by gate ID:

```json
{
  "state_contract_tests": {
    "status": "pass",
    "evidence_refs": [
      {
        "kind": "command",
        "summary": "pytest state contract tests passed",
        "path": "optional/workspace-relative/path.json",
        "sha256": "optional-64-hex-or-omitted"
      }
    ],
    "notes": ["optional public-safe note"]
  }
}
```

Input behavior:

- missing gate IDs: included in output as `unknown` with empty evidence;
- unknown gate IDs: `ValueError` / CLI nonzero failure;
- invalid status values: `ValueError` / CLI nonzero failure;
- malformed evidence refs: `ValueError` / CLI nonzero failure;
- malformed notes: `ValueError` / CLI nonzero failure;
- no input: all gates `unknown`.

AA chooses rejection, not auto-redaction, for supplied unsafe evidence. Safe
redaction placeholders are accepted only when the caller intentionally supplies
`"<redacted>"` in public fields.

Rejected supplied values:

- keys named `argv`, `prompt`, `raw_text`, or `executable_command` anywhere in
  evidence refs or notes;
- absolute paths in `path` or summary/note text;
- parent traversal paths;
- private-looking markers such as `PRIVATE`, `SECRET`, `TOKEN` in summaries,
  paths, notes, or hashes;
- command strings beginning with or containing raw executable invocations such as
  `omx ` when supplied as a public summary instead of a hash/abstract summary.

Accepted supplied redaction:

- `"<redacted>"` as a whole-field summary/path/note value;
- hashes, counts, generic summaries, and workspace-relative paths.

## 6. Ledger schema

Top-level public JSON shape:

```json
{
  "schema_version": "orchestrator-acceptance-ledger/1",
  "overall_status": "unknown|blocked|failed|partial|pass",
  "gate_count": 19,
  "gates": [
    {
      "id": "state_contract_tests",
      "title": "State contract tests pass",
      "status": "unknown|blocked|fail|pass",
      "required": true,
      "evidence_refs": [
        {
          "kind": "command|artifact|container|critic|verifier|private_redacted|issue_check",
          "summary": "short public-safe summary",
          "path": "optional workspace-relative or redacted path",
          "sha256": "optional hash"
        }
      ],
      "notes": [],
      "private_safe_summary": true
    }
  ],
  "missing_gate_ids": [],
  "private_safe_summary": true
}
```

Status semantics:

- `pass`: direct evidence satisfies this gate.
- `fail`: inspected evidence proves this gate failed.
- `blocked`: a known prerequisite/environment/human-finalization blocker exists.
- `unknown`: no sufficient evidence was supplied or detected.

Overall semantics:

- any `fail` => `failed`;
- else any `blocked` => `blocked`;
- else any `unknown` => `unknown`;
- else all pass => `pass`;
- `partial` is reserved for future grouped/optional evidence and should not be
  emitted in AA unless tests explicitly define it.

## 7. Public-safety rules

The output ledger must not include:

- raw private material;
- private file names or absolute private paths;
- raw prompts or command argv;
- provider traces;
- unredacted private smoke identifiers;
- secret-like tokens.

Allowed:

- hashes;
- counts;
- generic summaries;
- workspace-relative paths;
- explicit redaction placeholders.

AA should share simple sanitization helpers only when they preserve this stricter
reject-unsafe-input contract. Do not silently redact raw unsafe caller input into
a passing ledger entry.

## 8. Tests to add first

Add:

```text
tests/test_orchestra_acceptance_ledger.py
```

Required tests before implementation:

1. Gate ID tuple exactly matches the 19 IDs above in order.
2. Empty/default ledger contains all gates with `unknown` status and
   `overall_status=unknown`.
3. Supplied pass evidence for all gates yields `overall_status=pass`.
4. One `fail` gate yields `overall_status=failed`.
5. One `blocked` gate with no failures yields `overall_status=blocked`.
6. Unknown gates are never treated as pass.
7. Evidence refs reject private-looking absolute paths, parent traversal, raw prompts,
   `argv`, executable command strings, and private markers.
8. Intentionally supplied `"<redacted>"` placeholders are accepted as public-safe
   whole-field values.
9. Unknown gate IDs, invalid statuses, malformed evidence refs, and unsafe values
   fail closed with `ValueError` in Python and nonzero CLI failure.
10. Rendered human summary lists counts and first missing/blocking gates without
    leaking raw private strings.
11. JSON round-trip preserves schema version, gate IDs, statuses, and public-safe
    evidence summaries.
12. `paperorchestra acceptance-ledger --json` emits the schema and defaults to
    all `unknown` without evidence.
13. `paperorchestra acceptance-ledger --evidence synthetic.json --json` reflects
    supplied synthetic statuses.
14. CLI with unknown/malformed/private-looking evidence file fails closed and does
    not emit a passing ledger.

The tests must use synthetic generic evidence only.

## 9. Validation before implementation commit

Local:

```bash
.venv/bin/python -m pytest tests/test_orchestra_acceptance_ledger.py -q
.venv/bin/python -m pytest -q
scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
grep -RIn "<private-denylisted-literal>" $(git ls-files 'docs/**' 'paperorchestra/**' 'tests/**' 'skills/**' 'README.md' 'ENVIRONMENT.md') || true
git diff --check
```

The literal grep will use the concrete local denylist/known private markers, but
public evidence must report only whether tracked public files are clean.

Critic implementation validation is required before commit/push.

## 10. Container proof after push

After the implementation commit is pushed, run a fresh container proof from the
public remote:

```bash
docker run --rm paperorchestra-ubuntu-tools:24.04 bash -lc 'set -euo pipefail; git clone --quiet https://github.com/kosh7707/paperorchestra-for-codex.git repo; cd repo; git checkout --quiet orchestrator-v1-runtime; python3 -m venv .venv; . .venv/bin/activate; python -m pip install --quiet -e ".[dev]"; python -m pytest tests/test_orchestra_acceptance_ledger.py -q'
```

Record the result in this plan or a follow-up evidence commit.

## 11. Stop/replan triggers

Stop and replan if:

- the ledger needs private final-smoke material to pass unit tests;
- default unknown gates are accidentally treated as pass;
- public output includes raw private paths/prompts/argv or silently redacts unsafe supplied evidence into pass;
- the ledger claims v1 readiness instead of audit status;
- implementation requires changing generation/readiness behavior;
- CLI scope is absent, grows beyond read-only audit/reporting, or performs auto-pass inference;
- the exact 19 gate IDs conflict with the runtime plan.

## 12. Local implementation evidence (2026-05-13)

Tests were added before implementation and initially failed as expected with:

```text
ModuleNotFoundError: No module named 'paperorchestra.orchestra_acceptance'
```

Implementation added:

- `paperorchestra/orchestra_acceptance.py`
- `paperorchestra acceptance-ledger [--evidence <path>] [--json]`
- `tests/test_orchestra_acceptance_ledger.py`

Local verification after implementation:

```bash
.venv/bin/python -m pytest tests/test_orchestra_acceptance_ledger.py -q
# 14 passed, 15 subtests passed in 0.12s

.venv/bin/python -m pytest -q
# 909 passed, 161 subtests passed in 67.39s

scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
# {"status":"ok","match_count":0,"private_safe_summary":true}

grep -RIn "<private-domain literal>" $(git ls-files 'docs/**' 'paperorchestra/**' 'tests/**' 'skills/**' 'README.md' 'ENVIRONMENT.md')
# no matches

git diff --check
# ok
```

Critic implementation validation returned `APPROVE`. Fresh container proof remains
required after push.
