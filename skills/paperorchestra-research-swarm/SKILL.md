---
name: paperorchestra-research-swarm
description: Run parallel, source-backed prior-work and citation web research for PaperOrchestra manuscripts. Use when Related Work, bibliography expansion, citation_map/references.bib generation, prior_work_seed import, or evidence verification needs broad/deep multi-cluster web search before authoring, live review, quality gate, or plan approval; combines ultrawork/team-style parallel research lanes with autoresearch-style validator-gated completion.
---

# PaperOrchestra Research Swarm

## Invocation contract

Before executing any `$skill`, `omx`, `codex`, MCP, web, or PaperOrchestra CLI action from this skill, read `../paperorchestra/references/invocation-contract.md` and follow it. Required companion skills must be invoked, not merely recommended.

Use this skill as the PaperOrchestra-owned high-throughput research layer. It sits between `$paperorchestra-status` and manuscript writing/review when citation/source work is broad enough to benefit from parallel lanes.

## Core contract

Create an auditable chain:

```text
PaperOrchestra status/materials -> research-swarm-plan.md -> parallel lane plan -> lane-*/findings.md -> synthesis.md -> prior_work_seed.json/import -> citation artifacts -> autoresearch-state.json/result.json -> research-swarm.manifest.json -> next PaperOrchestra workflow
```

Do not fabricate papers, BibTeX, DOIs, URLs, quotes, results, or citation support. Treat unsupported findings as candidate-only. Respect copyright limits when quoting sources.

## When to use

Use `$paperorchestra-research-swarm` when any active PaperOrchestra workflow has machine-solvable source gaps and at least one of these is true:

- Related Work, citation candidates, bibliography, `citation_map.json`, `references.bib`, or source-backed positioning is missing/weak/stale.
- Two or more independent research clusters can run in parallel.
- The authoring round needs prior-work/search positioning before drafting.
- Live review or quality gate found broad citation/source-evidence gaps.
- Planning needs a small source-backed related-work seed to make the paper plan credible.

Do not use it for author-intent ambiguity (`$deep-interview`), human-only metrics/results, figure design itself (`$paperorchestra-figure`), or final manuscript prose (`$paperorchestra-authoring-round`).

## OMX companion routing

- `$ultrawork`: mandatory when two or more independent research clusters exist. Invoke it first to fan out bounded subagent/researcher lanes or explicitly record `no independent lanes`.
- `$team`: use instead of or under `$ultrawork` when the search needs coordinated tmux workers, shared task state, long-running web lanes, or durable mailbox evidence. Prefer `omx team N:researcher "<mission>"` only after its preflight is satisfied.
- `$autoresearch`: mandatory validator gate. Persist a completion artifact and do not mark the swarm complete until `result.json` records `passed: true`. If `prompt-architect-artifact` is used internally, mirror the architect approval into the same `result.json` with `passed: true` plus `architect_review`.
- `$best-practice-research`: add a lane for venue/style/comparable-paper norms when that affects the related-work story.
- `$paperorchestra-authoring-round`: next owner after research artifacts are imported and plan approval allows drafting.
- `$paperorchestra-live-review`: next owner after research is integrated and citation support needs web/model critique.
- `$paperorchestra-quality-gate`: next owner when the draft has fresh research/review artifacts and needs state-machine validation.
- `$ralph`: wrap a bounded research -> import -> authoring/review -> gate sequence when the user asks to keep going persistently.

Companion names are obligations under their triggers. Record skip reasons only when a trigger cannot safely run (`runtime unavailable`, `web unavailable`, `provider missing`, `no independent lanes`, or `human-only evidence`).

## Workflow

1. **Status and scope.** Start with `$paperorchestra-status` or MCP `inspect_state`; identify the paper workspace, current plan/draft, `prior_work_seed.json`, `candidate_papers.json`, `citation_registry.json`, `citation_map.json`, `references.bib`, and latest review/gate artifacts.
2. **Research mission.** Write `research-swarm-plan.md` with thesis, claim boundaries, target venue if known, allowed/blocked claims, required clusters, acceptance criteria, lane IDs, and output paths. Save it near the PaperOrchestra workspace when possible.
3. **Lane plan.** Split the mission into independent source-backed lanes. Default to 3--5 lanes; never exceed 6 native subagents/workers in one wave.
4. **Parallel execution.** Invoke `$ultrawork` for the lane plan. If native Codex subagents are available in the current session, call `spawn_agent` with `agent_type=researcher` for independent parallel subagent lanes and `agent_type=verifier` for citation-integrity validation; never omit the agent type. If the task is long-running or needs shared state, invoke `$team` and use `researcher` workers. If neither surface is available, run the lanes sequentially and record the skip reason.
5. **PaperOrchestra import.** Use MCP `research_prior_work(..., import_seed=true, citation_evidence_mode="web"|"source")` when attached; otherwise use verified CLI help before running `paperorchestra research-prior-work --import`. If the call times out, inspect status/log/artifact files before deciding whether it failed.
6. **Autoresearch gate.** Invoke `$autoresearch` with `mission-validator-script` when a deterministic artifact check is possible; otherwise use `prompt-architect-artifact` and then write the approval into the validator result. Persist `.omx/state/.../autoresearch-state.json` and a validator `result.json`. The completion artifact must include `passed: true`, validator mode, checked artifacts, and the output artifact path.
7. **Manifest.** Write `research-swarm.manifest.json` with mission path, lanes, runtime surface (`ultrawork`, `team`, native subagents, or sequential fallback), imported artifacts, validator artifact, weak/candidate-only sources, and next PaperOrchestra skill.
8. **Handoff.** Return to the narrow PaperOrchestra owner: authoring round for drafting/integration, live review for citation critique, quality gate for state-machine validation, or plan for approval updates.

## Lane template

Each lane assignment must be self-contained and source-backed:

```text
Lane id: lane-<cluster>
Role: researcher | verifier
Cluster:
Question:
Search targets: primary papers, official docs, benchmark docs, artifact repos, venue pages
Must return:
  - 5--10 candidate sources with title, authors, year, venue/source, DOI/URL, and why it matters
  - 2--4 contrast axes against the current manuscript
  - claim support limits and candidate-only warnings
  - BibTeX-ready metadata when available
  - source URLs checked during this lane
Must not:
  - invent citations or quote long passages
  - treat abstracts/blogs as final support when primary papers are available
```

Each lane writes `lane-<cluster>/findings.md`; the leader merges passed lanes into `synthesis.md` before PaperOrchestra import. Failed lanes remain in the manifest with a blocker and are not silently omitted.

Default lane clusters:

- `sast-static-analysis`: SAST false positives, alert triage, static-analysis precision/recall, CodeQL/SARIF, industrial SAST workflows.
- `llm-code-security`: LLM vulnerability detection, LLM-assisted static analysis, agentic code/security review, hallucination/verification limits.
- `benchmark-oracle`: OWASP Benchmark, Juliet/SARD, CWE/CVE oracle quality, benchmark labeling caveats, recall/precision interpretation.
- `agent-pipeline-methodology`: agent pipelines, tool-using LLMs, verifier/critic loops, provenance traces, human-in-the-loop repair.
- `venue-style-positioning`: comparable-paper related-work structure, section naming, contribution framing, and reviewer expectation evidence; invoke `$best-practice-research` for this lane when needed.

## Validation checklist

Before claiming completion, verify and report:

- `$ultrawork` was invoked for two or more lanes, or `$team` was invoked for durable workers, or a concrete skip reason was recorded.
- Subagent/worker lane evidence exists: lane IDs, prompts/assignments, returned source lists, and any failed/blocked lane.
- `$autoresearch` validator artifact exists and `result.json` records `passed: true`.
- PaperOrchestra import produced or updated at least one of: `prior_work_seed.json`, `candidate_papers.json`, `citation_registry.json`, `citation_map.json`, `references.bib`.
- Each accepted citation has source metadata and a claim-support note; weak sources remain candidate-only.
- No manuscript claim was strengthened beyond available evidence.

## Final card

```text
Research workspace:
Paper workspace:
Mission:
Runtime lanes:
Subagent/team evidence:
Autoresearch validator:
PaperOrchestra import:
Seed/citation artifacts:
Accepted clusters:
Weak/candidate-only sources:
Next PaperOrchestra skill:
Remaining blockers:
```
