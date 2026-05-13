# Slice AE mini-plan — first-user Skill/MCP UX guide

Status: draft mini-plan requiring Critic validation before tests or implementation
Date: 2026-05-13
Branch: `orchestrator-v1-runtime`
Scope: public, domain-general first-user onboarding and natural-language handoff guidance for Skill/MCP/CLI. Do not include private smoke material, private-domain terms, or private material names.

## 0. Pre-plan issue check

Required by the post-Z workflow plan before every slice mini-plan:

```bash
gh issue list --state open --json number,title,labels,updatedAt,url --limit 50
# []
```

No actionable open GitHub issue blocked Slice AE planning.

## 1. Target result

Slice AE makes the intended first-user path explicit and testable. A user who just
cloned the project is expected to talk to Codex/OMX in natural language, not read
or memorize a command catalog. The system should answer common first-use intents
with compact, action-oriented guidance, inspect available material when possible,
and ask only author-judgment questions that cannot be discovered automatically.

Primary use cases from the interview/spec:

1. `이 프로젝트 셋업해줘` / setup after clone;
2. `paperorchestra 어떻게 쓰는거야?` / first-use explanation after setup;
3. `이거 쓰고 싶어` / start guided orchestration from current material/session;
4. `바로 써줘` with insufficient material / refuse drafting, explain missing
   material, and offer valid next steps rather than inventing claims/citations.

## 2. Current baseline

Existing surfaces:

- `skills/paperorchestra/SKILL.md`
  - already says to prefer high-level orchestrator tools and not dump README;
  - documents MCP registration-vs-active-attachment distinction;
  - lacks a single canonical, testable first-use response contract for the four
    named user intents.
- `paperorchestra/mcp_server.py`
  - exposes high-level tools: `inspect_state`, `orchestrate`, `continue_project`,
    `answer_human_needed`, `export_results`;
  - does not expose a dedicated first-user guide tool.
- `paperorchestra/cli.py`
  - exposes CLI fallbacks: `inspect-state`, `orchestrate`, `continue-project`,
    `answer-human-needed`;
  - has no compact first-user guide command that mirrors the Skill/MCP guidance.
- Tests:
  - `tests/test_paperorchestra_skill_guidance.py` checks a few static skill
    phrases;
  - `tests/test_orchestrator_mcp_entrypoints.py` and
    `tests/test_orchestrator_cli_entrypoints.py` cover high-level tool presence
    and bounded execution behavior;
  - `tests/test_mcp_server.py` covers MCP protocol/handler wiring.

Gaps:

- no machine-readable guide surface mapping first-user intents to safe next
  actions;
- no tests preventing README dumps, command catalogs, or asking the user to do
  machine-solvable setup/research work;
- no CLI/MCP parity for the first-user guidance itself;
- no compact five-axis status card exposed for first-user guidance;
- no explicit refusal contract for `바로 써줘` when material is insufficient.

## 3. Implementation boundary

Add a small bounded module rather than baking onboarding logic into the giant CLI
or MCP server:

```text
paperorchestra/first_user_guide.py
  FIRST_USER_GUIDE_SCHEMA_VERSION = "first-user-guide/1"
  build_first_user_guide(cwd, *, intent="auto", material=None, mcp_attached=None) -> dict
  render_first_user_guide_summary(payload) -> str
```

CLI addition:

```bash
paperorchestra first-use [--intent setup|how_to_use|start|write_now|auto] [--material path] [--mcp-attached yes|no|unknown] [--json]
```

MCP addition:

```text
first_use_guide(cwd?, intent?, material?, mcp_attached?)
```

Skill update:

- For the four first-use phrases, prefer `first_use_guide` when the MCP namespace
  is attached.
- If native MCP tools are absent but CLI is available, use
  `paperorchestra first-use ...` as the fallback.
- Do not dump README or a long command catalog by default.
- Tell the user “I will proceed this way unless interrupted” for machine-solvable
  next steps, while stopping for author-judgment or missing private material.

## 4. Public schema contract

The guide output should be public-safe and should not include raw material text,
private paths, or full command catalogs.

Expected payload shape:

```json
{
  "schema_version": "first-user-guide/1",
  "intent": "setup | how_to_use | start | write_now | auto",
  "status": "ready | needs_material | needs_setup | mcp_fallback | blocked",
  "scorecard": {
    "material": "ok | missing | insufficient | unknown",
    "evidence": "ok | missing | insufficient | unknown",
    "citations": "ok | needs_research | unknown",
    "figures": "ok | needs_inventory | unknown",
    "mcp": "attached | registered_only | unknown"
  },
  "summary": "compact one-paragraph explanation",
  "next_actions": [
    {"action_type": "inspect_state", "surface": "mcp|cli", "reason": "..."}
  ],
  "author_questions": [
    {"question": "...", "why_user_owned": "..."}
  ],
  "refusal": {
    "refused": true,
    "reason": "insufficient material; drafting would require invented claims/results"
  },
  "private_safe_summary": true
}
```

Rules:

- `how_to_use`: show a compact scorecard and route to inspect/orchestrate/intake;
  do not dump README.
- `start`: inspect material/session and propose the next bounded orchestrator
  action; ask no question for discoverable facts.
- `write_now`: if material/evidence is insufficient, refuse drafting and propose
  material/intake/mock-demo next steps; do not fabricate claims, citations, or
  results.
- `setup`: propose setup/MCP/skill/smoke steps, but keep them grouped and short;
  mention restart/attach distinction.
- All payloads set `private_safe_summary=true` and redact filesystem paths to
  labels/hashes when material is supplied.

## 5. Integration points

Required:

1. `paperorchestra/first_user_guide.py` builder with deterministic outputs.
2. CLI parser and handler in `paperorchestra/cli.py`.
3. MCP tool spec + handler in `paperorchestra/mcp_server.py`.
4. Skill guidance update in `skills/paperorchestra/SKILL.md`.
5. Existing high-level orchestrator tools remain unchanged and green.

Optional if small and tested:

- README/ENVIRONMENT mention the new first-use guide as a compact alternative to
  reading the whole README.

Non-goal for AE:

- Do not run live model/search/OMX.
- Do not change actual drafting or citation/figure gate behavior.
- Do not solve MCP active attachment itself; continue to distinguish registration
  from active attachment.
- Do not include private material in tests.

## 6. Tests to add first

Minimum failing tests before implementation:

1. `tests/test_first_user_guide.py`
   - `how_to_use` returns schema, five-axis scorecard, compact next actions, and
     does not include README dump phrases or raw command catalog text.
   - `write_now` without sufficient material returns `refusal.refused=true`,
     explains insufficient material, and proposes intake/material/mock next steps.
   - supplied material path is redacted in rendered JSON while still affecting
     material status.
   - setup intent mentions MCP registration-vs-attachment and restart/check steps.
2. CLI tests:
   - `paperorchestra first-use --intent how_to_use --json` returns schema;
   - human summary includes scorecard and next actions, not a long command dump;
   - `--intent write_now` without material exits 0 but reports refusal/block.
3. MCP tests:
   - `first_use_guide` appears in `TOOLS` and `TOOL_HANDLERS`;
   - handler returns the same schema and redacts material paths;
   - MCP response for insufficient material refuses drafting without raw paths.
4. Skill guidance tests:
   - skill names `first_use_guide` and CLI fallback `paperorchestra first-use`;
   - skill still says do not dump README and ask only author-owned questions;
   - skill rejects `바로 써줘` when material is insufficient.

Existing tests that must remain green:

```bash
.venv/bin/python -m pytest tests/test_paperorchestra_skill_guidance.py \
  tests/test_orchestrator_cli_entrypoints.py \
  tests/test_orchestrator_mcp_entrypoints.py \
  tests/test_mcp_server.py -q
```

## 7. Validation before implementation commit

Local:

```bash
.venv/bin/python -m pytest tests/test_first_user_guide.py \
  tests/test_paperorchestra_skill_guidance.py \
  tests/test_orchestrator_cli_entrypoints.py \
  tests/test_orchestrator_mcp_entrypoints.py \
  tests/test_mcp_server.py -q
.venv/bin/python -m pytest -q
scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
grep -RIn "<private-domain literal>" $(git ls-files 'docs/**' 'paperorchestra/**' 'tests/**' 'skills/**' 'README.md' 'ENVIRONMENT.md') 2>/dev/null | head -50 || true
git diff --check
```

Critic implementation validation is required before commit/push.

## 8. Container proof after push

After implementation commit is pushed:

```bash
docker run --rm \
  -v /tmp/paperorchestra-private-denylist.txt:/tmp/paperorchestra-private-denylist.txt:ro \
  paperorchestra-ubuntu-tools:24.04 bash -lc 'set -euo pipefail
WORK=/tmp/paperorchestra-ae-proof
rm -rf "$WORK"
git clone --branch orchestrator-v1-runtime https://github.com/kosh7707/paperorchestra-for-codex.git "$WORK" >/tmp/git-clone.log
cd "$WORK"
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]" >/tmp/pip-install.log
python -m pytest tests/test_first_user_guide.py tests/test_paperorchestra_skill_guidance.py tests/test_orchestrator_mcp_entrypoints.py -q
scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json
printf "HEAD=%s\n" "$(git rev-parse --short HEAD)"
'
```

Record proof in this plan or a follow-up evidence commit.

## 9. Stop/replan triggers

Stop and replan if:

- the guide becomes a README/command dump instead of a compact first-user
  contract;
- the guide asks users to perform machine-solvable setup/research/citation tasks;
- `write_now` can draft or suggest drafting from insufficient material;
- public output includes raw material text, private paths, or private markers;
- MCP/CLI/Skill guidance diverges on the first-use path;
- tests would require private material or live services.
