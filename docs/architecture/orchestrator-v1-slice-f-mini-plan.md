# Slice F mini-plan — private-smoke safety rails and material preparation

Status: slice implementation plan requiring Critic validation before code
Date: 2026-05-13
Branch: `orchestrator-v1-runtime`

## 1. Target result

Before running any final private full-live smoke, add public-safe utilities that make private material handling auditable and hard to accidentally commit.

Slice F adds:

```text
tracked-file private leakage scanner
repo-external private material preparation utility
redacted manifest/checklist output
```

The tools must be generic and use synthetic tests. They must not include private material names, titles, claims, figure names, or BibTeX keys.

## 2. Public utilities

### 2.1 Leakage scanner

Proposed script:

```text
scripts/check-private-leakage.py
```

Behavior:

- reads denylist tokens/patterns from a user-provided local file (`--denylist` or `PAPERO_PRIVATE_DENYLIST`);
- scans tracked files by default (`git ls-files`) so ignored private temp directories are not traversed accidentally;
- supports `--paths` for explicit path lists in tests;
- reports JSON with `status=ok|blocked`, match counts, redacted path labels/hashes, and redacted token labels/hashes;
- exits nonzero on match;
- never ships actual private denylist content in repo.

### 2.2 Repo-external material prep

Proposed script:

```text
scripts/prepare-private-smoke-materials.py
```

Behavior:

- accepts `--source-zip` and `--output-dir`;
- refuses to extract into the git worktree unless `--allow-inside-repo` is explicitly given;
- extracts into a repo-external directory;
- emits a redacted manifest with counts, extensions, total bytes, and file hashes;
- optionally writes an answer-key/material split checklist but does not infer domain-specific meaning;
- does not print raw file contents.

## 3. Tests to add first

Proposed file:

```text
tests/test_private_smoke_safety.py
```

Minimum failing tests before implementation:

1. leakage scanner returns ok when denylist token is absent;
2. leakage scanner blocks when synthetic private token appears in a tracked/test path;
3. scanner JSON redacts actual token but includes token hash/label;
4. scanner JSON redacts matched paths or uses path hashes so private tokens in filenames cannot leak;
5. scanner defaults to tracked-file mode by invoking a git file list helper or accepting injected paths in tests;
6. material prep refuses output inside repo by default;
7. material prep extracts a synthetic zip outside repo;
8. material prep manifest contains counts/extensions/hashes but not raw file contents;
9. material prep manifest marks `private_safe_summary=true`.

## 4. Validation for this slice

Required before commit/push:

```bash
.venv/bin/python -m pytest tests/test_private_smoke_safety.py -q
.venv/bin/python -m pytest tests/test_orchestrator_* tests/test_orchestra_*.py -q
.venv/bin/python -m pytest tests/test_mcp_server.py tests/test_pre_live_check_script.py -q
git diff --check
```

Preferred:

```bash
.venv/bin/python -m pytest -q
```

Critic implementation validation is required before commit.

## 5. Explicit non-goals

Slice F must not:

- include actual private denylist entries;
- include private zip path/name in public files;
- inspect or summarize raw private scientific claims;
- run the final private smoke;
- change orchestrator runtime semantics;
- add non-stdlib dependencies.

## 6. Stop/replan triggers

Stop and replan if:

- any test or public doc needs actual private identifiers;
- scanner traverses ignored directories by default;
- prep utility extracts into repo without explicit override;
- manifest or scanner output prints raw private contents, raw denied tokens, or raw matched paths containing denied tokens;
- leakage scanner cannot be used in pre-push/final audit scripts.
