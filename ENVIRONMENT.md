# PaperOrchestra environment

This file is intentionally short. The normal setup path is still:

```bash
./install.sh
```

`install.sh` creates `.venv`, installs the package, installs bundled Codex skills, registers the Codex MCP server, writes `.paperorchestra.env`, and runs `omx setup` when `omx` is available.

## Local provider command

`./install.sh` writes a generic provider command without pinning a model or reasoning effort:

```bash
source .paperorchestra.env
```

Override `PAPERO_MODEL_CMD` only when you want a specific provider/model policy.

## Common knobs

| Variable | Default | Purpose |
| --- | --- | --- |
| `PAPERO_MODEL_CMD` | written by `./install.sh` | Shell-provider command for live model-backed stages. |
| `PAPERO_ALLOWED_PROVIDER_BINARIES` | `codex,openai,ollama,llm,claude,gemini` | Executable allowlist for shell providers. |
| `PAPERO_ALLOW_TEX_COMPILE` | unset | Set to `1` before intentional PDF compilation. |
| `PAPERO_OMX_MODEL` | Codex/OMX config | Optional explicit model override. |
| `PAPERO_OMX_REASONING_EFFORT` | Codex/OMX config | Optional explicit reasoning-effort override. |
| `SEMANTIC_SCHOLAR_API_KEY` | unset | Optional; S2 is not required when using web/source/manual evidence. |
| `PAPERO_DOMAIN` | `generic` | Optional domain profile name. |

## Readiness meanings

- `complete`: a bounded run finished or a compiled PDF exists.
- `pass_loop_verified`: configured loop checks passed.
- `ready_for_human_finalization`: automation has no more safe action.

None of these means submission-ready. Human authors own final claims, citations, figures, and submission decisions.

## Minimal local fixture

The repository keeps only one tiny fixture for smoke/demo use:

```bash
paperorchestra init \
  --idea examples/minimal/idea.md \
  --experimental-log examples/minimal/experimental_log.md \
  --template examples/minimal/template.tex \
  --guidelines examples/minimal/conference_guidelines.md \
  --figures-dir examples/minimal/figures
```

If setup looks stale, run:

```bash
.venv/bin/paperorchestra doctor
.venv/bin/paperorchestra environment --summary
```
