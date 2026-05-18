# Orchestrator v1 fresh-container functional smoke summary

Status: pass for the public synthetic-container functional smoke gate
Date: 2026-05-18
Branch under test: `orchestrator-v1-runtime`
Scope: public-safe summary only. Raw Docker logs and full artifact packets remain outside the tracked repository.

## Container recipe

- Engine: Docker
- Image: `paperorchestra-ubuntu-tools:24.04`
- Source checkout: fresh clone from the public GitHub branch after `cd9c5db`
- Private materials used: false
- Output mode: synthetic container smoke; not private final live evidence

The container updated the Codex and OMX npm CLIs through the host helper path before the smoke. The helper returned a nonzero status after warning about unrelated missing non-required CLIs, but the required versions were confirmed inside the container:

```text
codex-cli 0.130.0
oh-my-codex v0.17.3
```

## Functional proof

The container smoke completed the following proof points:

- clean clone and editable dev install passed;
- CLI version, environment summary, and doctor commands returned successfully;
- compile toolchain was installed in the container and detected as ready;
- Codex MCP registration script completed against the project-local venv;
- raw MCP stdio smokes passed for both supported transports;
- Codex active attach smoke observed a PaperOrchestra MCP tool call;
- OMX explore returned `OK`;
- `scripts/fresh-qa.sh` completed with every step `ok`;
- full pytest inside the container passed;
- mock demo completed;
- compile produced a two-page PDF;
- export produced the main PDF, TeX, BibTeX, review, reproducibility, fidelity, runtime parity, compile report, and session files;
- tracked-file leakage scan against synthetic denylist tokens found zero matches;
- fresh-smoke evidence completeness and synthetic acceptance summary both passed;
- the generated public summary records hashes for key raw evidence files without exposing raw paths.

## Key counts

```text
fresh-qa status: ok
full pytest: 1016 passed, 182 subtests passed
MCP raw tools: 66
PDF pages: 2
PDF size: 46468 bytes
leakage matches: 0
acceptance summary: pass
artifact file count: 416
operator feedback cycles: 0
```

## Gate interpretation

This evidence is allowed to satisfy:

- `fresh_container_functional_smoke`
- `exported_pdf_tex_evidence_bundle`

It does not satisfy:

- private final live smoke;
- manuscript quality/readiness;
- citation integrity for a private live paper;
- critical-claim support;
- supplied-figure matching;
- final Critic consensus or Verifier completion audit.
