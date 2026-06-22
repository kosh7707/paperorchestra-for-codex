# PaperOrchestra Invocation Contract

Use this reference before executing any PaperOrchestra skill instruction that mentions `$skill`, `omx`, `codex`, MCP tools, or a CLI fallback.

## Skill invocation is not a shell command

A `$skill-name` token means: load that installed skill's `SKILL.md` and execute its workflow. Do not merely recommend, echo, or write the token. Do not run `$skill-name` in a shell.

When a PaperOrchestra skill says another skill is **required**, stop the current workflow after safe read-only/state work and execute the required skill before continuing. When it says another skill is **recommended**, report it as a next action unless the user asked to continue through that workflow now.

## OMX runtime workflows

For OMX-owned workflows such as `$deep-interview`, `$ralplan`, `$ultrawork`, `$ralph`, `$team`, `$ultraqa`, `$autoresearch`, `$best-practice-research`, and `$visual-verdict`:

1. read the target skill instructions first;
2. follow that skill's state/artifact protocol;
3. collect completion evidence before handing control back to PaperOrchestra.

In attached tmux sessions, `$deep-interview` asks every user-facing interview round through:

```bash
OMX_QUESTION_RETURN_PANE=$TMUX_PANE omx question --input '<json>' --json
```

with `source:"deep-interview"`. A valid deep-interview handoff normally includes `.omx/specs/deep-interview-*.md` and `.omx/interviews/*.md` artifacts. If the required OMX question path is unavailable, mark the PaperOrchestra step blocked; do not fabricate intake or plan artifacts from fallback prose in the same turn.

## MCP attachment versus registration

Prefer visible MCP tools when attached. Active attachment means the tool namespace is present in the current session, not merely that `codex mcp list` shows a registration. If no visible `mcp__paperorchestra__...` tools exist, use CLI fallback and say MCP active attachment is unavailable.

## CLI fallback discipline

Before using a CLI command that is not already verified in the current run, check the installed surface with:

```bash
paperorchestra <command> --help
```

Do not invent commands from MCP tool names. Source checkout helpers may expose commands that the installed `paperorchestra` console script does not. If the installed command is absent, use the documented staged fallback or block with the missing command named.

Currently observed installed CLI gaps include `paperorchestra authoring-round`, `paperorchestra approve-plan`, `paperorchestra quality-gate`, and `paperorchestra visual-audit`; use MCP/source tools only when actually attached/verified, or staged fallbacks.

## State-update verification

Any command or MCP tool that may change PaperOrchestra, OMX, Codex, or job state must be followed by a readback before claiming success.

For PaperOrchestra state changes:

```bash
paperorchestra status --json
```

Check the session id, `current_phase`, expected artifact paths, review/gate JSON, and notes. For background jobs, also use `paperorchestra jobs-list` and `paperorchestra job-status --job-id <id>` / `run-status --job-id <id>` until the job reaches a terminal state, then inspect the produced stdout/stderr JSON or manifest.

For OMX mode changes:

```bash
omx state read --mode <mode> --json
omx state get-status --mode <mode> --json
```

For `omx question`, read the returned JSON and use `answers[]` as the source of truth. Do not continue to another round or downstream PaperOrchestra step until the answer has been captured and persisted by the owning skill.

For Codex/MCP configuration checks, distinguish registration from active attachment and report both when relevant. Do not claim an MCP tool updated state unless the tool returned success and a subsequent status/artifact readback supports it.

## Completion evidence

Before claiming a required invocation completed, report concrete evidence: command status, state JSON, artifact path(s), manifest path, review/gate JSON, or the exact blocking condition. Diagnostic artifacts are not readiness passes.
