# Orchestrator v1 current verification summary

Status: current local verification checkpoint before next fresh full live smoke  
Date: 2026-05-18  
Branch: `orchestrator-v1-runtime`  
Scope: public-safe summary only. Raw runtime logs are local ignored review artifacts.

## 1. Targeted tests

Current targeted suites passed:

```text
86 passed, 53 subtests passed
```

Covered areas:

- state contract;
- state scenarios;
- action planner;
- OMX executor/invocation contracts;
- MCP orchestrator entrypoints;
- runtime facade;
- acceptance ledger.

After the wrapper safety fix, focused wrapper/ledger tests passed. A smaller focused redaction/venue/refresh/ledger rerun after Critic redaction feedback also passed.

```text
63 passed, 15 subtests passed
17 passed, 15 subtests passed
1016 passed, 182 subtests passed
```

## 2. Full pre-live verification

`pre-live-check --all` completed successfully after the wrapper safety fix:

```text
Pre-live check PASS
Evidence label: review/pre-live-check-20260518T015346Z
```

The pre-live run included compileall, smoke contract dry-run, strict smoke policy,
controlled quality gate smoke, bounded OMX runtime probe, feature unittest groups,
markdown fence check, secret scan, diff check, full unittest, and live resolver
probe. A separate full pytest rerun after Critic redaction feedback also passed
with `1016 passed, 182 subtests passed`.

## 3. MCP smoke

Current raw MCP smoke used the project-local MCP server binary.

```text
content-length transport: server ok, 66 tools, expected tools present, status tool reached server
newline transport: server ok, 66 tools, expected tools present, status tool reached server
Codex attach smoke: ok, paperorchestra status tool call observed
Codex version: codex-cli 0.130.0
```

The local user config did not contain a persistent PaperOrchestra MCP registration,
but the attach smoke used explicit `codex exec` configuration overrides and did
not mutate user config. Final fresh-user acceptance should still verify the setup
or registration path in the target container/user profile.

## 4. Bounded OMX probes

Current bounded OMX probes completed for:

```text
version
status
state list-active JSON
trace summary JSON
ralph help
autoresearch-goal help
explore help
sparkshell help
```

Observed OMX version:

```text
oh-my-codex v0.17.3
```

## 5. Leakage and overfit safety

The current tracked-file denylist scan returned:

```text
status: ok
match_count: 0
```

A direct tracked-file literal grep for known private/domain markers also returned
no matches.

## 6. Wrapper safety fix

The fresh full live smoke wrapper no longer hard-codes a domain-specific venue
string. It now uses a generic default and allows override through:

```text
PAPERO_FRESH_SMOKE_VENUE
```

The wrapper also no longer hard-codes a local private parent path in redaction
patterns. A regression test proves an absolute path token containing the private
artifact marker is fully replaced, including the parent prefix before the marker.
The unittest selector-loadability check now probes selectors in an isolated
subprocess so full-suite import side effects cannot create false `_FailedTest`
results.

## 7. Remaining blockers

This checkpoint does not prove v1 completion. The current acceptance ledger remains
blocked because the following still require fresh evidence:

- mock demo rerun;
- compile/export rerun;
- fresh container functional smoke;
- fresh private final live smoke after T2 hardening;
- citation and critical-claim quality proof;
- supplied-figure inventory/match/replacement proof;
- final Critic consensus and Verifier evidence bundle;
- final README/ENVIRONMENT/Skill refresh.


## 8. Current mock demo and compile/export smoke

A current mock demo was rerun in a persistent repo-local workdir:

```text
status: SUCCESS
session: po-bf0fa0f9a354
phase before compile: draft_complete
```

The same session was compiled and exported:

```text
compile: pass
status after compile: complete
export: pass
exported files: paper.full.tex, paper.full.pdf, references.bib, review.latest.json, reproducibility.audit.json, fidelity.audit.json, runtime-parity.json, compile-report.json, session.json
pdf pages: 2
pdf size: 46480 bytes
```

This satisfies the current `mock_demo` and `compile_export` gates. It does not
satisfy final private-smoke manuscript quality, fresh-container functional smoke,
or final exported evidence-bundle gates.
