# Slice AH mini-plan — private final-smoke execution and redacted completion evidence

Status: draft mini-plan requiring Critic validation before execution
Date: 2026-05-14
Branch: `orchestrator-v1-runtime`
Scope: execution/evidence slice. Do not add product heuristics, fixtures, docs, or
tests that encode private-domain assumptions. Public commits may contain only
redacted labels, counts, hashes, status codes, and generic failure predicates.

## 0. Pre-plan issue check

Required by the post-Z workflow plan before every slice mini-plan:

```bash
gh issue list --state open --json number,title,labels,updatedAt,url --limit 50
# []
```

No actionable open GitHub issue blocked Slice AH planning.

## 1. Target result

Slice AG added a public-safe summarizer for existing fresh-smoke evidence roots.
Slice AH uses that surface for the first real private final-smoke execution pass:

1. verify the private material packet exists outside the public repo;
2. prepare an isolated private material directory outside the repo;
3. run a fresh full live smoke in a Docker container with host-mounted private
   material and host-mounted evidence output;
4. allow up to five bounded operator/human-needed cycles, with the operator role
   handled by Codex/OMX inside the smoke loop;
5. summarize the resulting evidence with
   `paperorchestra summarize-fresh-smoke --smoke-mode private_final`;
6. commit only redacted public evidence and validation results.

This slice is allowed to fail or block if the private smoke output is not
near-human-finalization quality. Failure is valuable evidence; the forbidden
outcome is pretending that a failed/blocked private smoke run passed.

## 2. Private input proof, redacted

Private zip candidate was verified outside the repo:

```json
{
  "exists": true,
  "redacted_path_label": "redacted-private-zip-path:7b17e0e1700b",
  "sha256": "ae91fe3dff31947c5d11b5dd1f0f62aa07773770d506731d7ae08f175a6ebd4c",
  "zip_member_count": 14,
  "size_bytes": 2473243
}
```

The public repo must not store the private zip name, extracted filenames,
claims, figure names, titles, captions, source text, or raw paths.

## 3. Execution boundary

This slice is primarily an execution/evidence slice, not a product-code slice.
Do not modify product behavior unless a preflight failure reveals a blocker that
prevents the generic smoke harness from running safely.

Permitted operations:

- create outside-repo directories under `/tmp` or `~/temp`;
- run `scripts/prepare-private-smoke-materials.py` with the private zip and
  outside-repo output;
- run containerized smoke commands with private material mounted read-only and
  evidence mounted read-write;
- run `summarize-fresh-smoke` over the resulting evidence root;
- run leakage scans over tracked files and over any public redacted summary;
- commit a public evidence note with only redacted labels/counts/hashes/statuses.

Forbidden operations:

- commit extracted private material, private zip paths, material filenames, raw
  prompts, raw provider responses, full private logs, PDFs, TeX, BibTeX, or
  screenshots;
- add private-domain-specific heuristics or tests;
- mark `private_final_live_smoke_redacted` pass from synthetic/container-only
  evidence;
- use `human_needed` for machine-solvable research, citation, metadata, or web
  lookup gaps;
- call deprecated `omx autoresearch`.

## 4. Planned commands

All concrete paths below are examples; actual public records must use redacted
labels and hashes.

### 4.1 Prepare private material outside the repo

```bash
PRIVATE_PREP=/tmp/paperorchestra-private-materials-$(date -u +%Y%m%dT%H%M%SZ)
scripts/prepare-private-smoke-materials.py \
  --source-zip <private zip outside repo> \
  --output-dir "$PRIVATE_PREP" \
  --json
```

Expected:

- extracted material exists outside the repo;
- `private-smoke-manifest.redacted.json` exists;
- manifest contains only safe labels/counts/hashes;
- no public tracked file changes.

### 4.2 Container dry-run contract

Before the long live run, prove that the current remote branch, Docker image,
mounts, and wrapper contract can run without touching live models:

```bash
docker run --rm \
  -v "$PRIVATE_PREP:$PRIVATE_PREP:ro" \
  -v "$EVIDENCE_ROOT:$EVIDENCE_ROOT:rw" \
  paperorchestra-ubuntu-tools:24.04 bash -lc '
    set -euo pipefail
    git clone --branch orchestrator-v1-runtime https://github.com/kosh7707/paperorchestra-for-codex.git /tmp/paperorchestra-ah
    cd /tmp/paperorchestra-ah
    python3 -m venv .venv
    . .venv/bin/activate
    python -m pip install -e ".[dev]"
    PAPERO_CODEX_CLI_PREFIX="<authenticated-codex-omx-provider-command>" \
      scripts/fresh-full-live-smoke-loop.sh \
        --evidence-root "$EVIDENCE_ROOT/dry-run" \
        --material-root "$PRIVATE_PREP" \
        --expected-material-root "$PRIVATE_PREP" \
        --max-operator-cycles 5 \
        --dry-run-contract
  '
```

Expected:

- provider wrapper contract JSON exists in the evidence root;
- dry-run contract exits successfully or records a redacted actionable blocker;
- no private material is copied into tracked repo files.

### 4.3 Long private full live smoke

After dry-run passes, use the authenticated provider command from the local
operator environment. The exact command/prefix is operationally sensitive and
must stay outside tracked files, public evidence notes, and committed summaries:

```bash
PAPERO_CODEX_CLI_PREFIX="<authenticated-codex-omx-provider-command>" \
scripts/fresh-full-live-smoke-loop.sh \
  --evidence-root <outside-repo-evidence-root> \
  --material-root <outside-repo-private-material-dir> \
  --expected-material-root <outside-repo-private-material-dir> \
  --max-operator-cycles 5
```

Preferred execution surface is a Docker container with the same mounts as the
dry run. If the container cannot access the required authenticated Codex/OMX
state, stop and record a redacted blocker rather than falling back silently.

## 4.5 Docker auth/mount contract

Allowed container mounts:

- private material root: read-only;
- expected material root: read-only, usually the same path as private material;
- evidence root: read-write;
- a minimal Codex/OMX auth/config bundle: read-only where possible, copied from
  the operator environment only when needed for live execution.

Forbidden container mounts:

- the whole home directory;
- the public repo as a read-write mount for private smoke output;
- private material mounted anywhere inside the public repo;
- auth/config copied into the repo, evidence summary, public docs, or committed
  files;
- provider trace prompts/responses copied into public commits.

Auth preflight:

```bash
docker run --rm <mount allowlist only> paperorchestra-ubuntu-tools:24.04 bash -lc '
  set -euo pipefail
  test -n "${PAPERO_CODEX_CLI_PREFIX:-}" || { echo "auth_provider_prefix_missing"; exit 20; }
  # Run only a non-secret version/help/status probe. Do not echo config, tokens,
  # cookies, auth paths, or provider stderr unless it has been redacted.
'
```

If auth preflight fails, record only a generic blocker such as
`container_auth_preflight_failed`; do not paste raw stderr/stdout into public
tracked files.

### 4.4 Redacted summary

```bash
.venv/bin/paperorchestra summarize-fresh-smoke \
  --evidence-root <outside-repo-evidence-root> \
  --smoke-mode private_final \
  --material-manifest <outside-repo-material-dir>/private-smoke-manifest.redacted.json \
  --output <outside-or-repo-redacted-summary.json> \
  --json
```

Expected:

- summary is `pass`, `blocked`, or `fail`;
- `private_final_live_smoke_redacted` mirrors only private-final evidence;
- `private_leakage_scan` combines meta-leakage and manifest safety;
- summary contains no raw private path/name/content.

If dry-run or live smoke fails before `summarize-fresh-smoke` can produce a
valid summary, the public fallback evidence shape is:

```json
{
  "schema_version": "redacted-smoke-blocker/1",
  "status": "blocked | fail",
  "redacted_evidence_root_label": "redacted-evidence-root:<digest>",
  "redacted_material_manifest_label": "redacted-material-manifest:<digest>",
  "blocker_code": "container_auth_preflight_failed | dry_run_contract_failed | live_smoke_execution_failed | summary_unavailable",
  "private_safe_summary": true
}
```

Fallback evidence must not include raw logs, raw command lines, raw private
paths, provider stderr, prompts, responses, or private material names.

## 5. Tests and validation

Before any evidence commit:

```bash
.venv/bin/python -m pytest tests/test_fresh_smoke_acceptance.py \
  tests/test_private_smoke_safety.py \
  tests/test_fresh_smoke_inputs.py \
  tests/test_orchestra_acceptance_ledger.py \
  tests/test_orchestrator_cli_entrypoints.py \
  tests/test_orchestrator_mcp_entrypoints.py -q

.venv/bin/python -m pytest -q

scripts/check-private-leakage.py --denylist /tmp/paperorchestra-private-denylist.txt --root "$PWD" --json

grep -RIn "<private-domain literal>" $(git ls-files 'docs/**' 'paperorchestra/**' 'tests/**' 'skills/**' 'README.md' 'ENVIRONMENT.md') 2>/dev/null | head -50 || true

git diff --check
```

Critic implementation/execution validation must review the redacted summary and
public evidence note before commit.

Additional cleanliness and redaction checks:

```bash
git status --short
# must not show extracted private material or raw smoke logs

python3 - <<'PY'
# Load every proposed public evidence JSON/Markdown file and fail if it contains
# raw private paths, auth paths, provider commands, private markers, or absolute
# outside-repo smoke paths. Exact scanner implementation may be ad hoc for this
# execution slice, but the output must be recorded as pass/fail only.
PY
```

Do not commit raw `readable/commands.md`, `logs/*.command`, provider traces,
operator feedback packets, Critic prompts/responses, generated PDFs, generated
TeX, generated BibTeX, or private smoke manifests unless they are first proven
public-safe by the summarizer and leakage scanner. Prefer committing only this
plan’s redacted evidence section.

## 6. Public evidence commit content

The public evidence commit may include:

- this plan updated with final status;
- redacted evidence root label;
- private manifest hash/counts;
- final `summarize-fresh-smoke` overall status;
- acceptance gate statuses for the gates the summary covers;
- operator cycle counts;
- generic first failing predicate/code;
- local and container verification counts;
- leakage scan `match_count=0` or failure code.

It must not include:

- private zip/source path;
- private material filenames;
- generated private manuscript PDF/TeX/BibTeX;
- raw provider/Critic/operator prompts or responses;
- raw command lines containing private paths;
- raw domain-specific text.

Raw evidence handling:

- the outside-repo smoke evidence root may contain raw logs and private generated
  outputs for local debugging only;
- public commits must reference that root only through a redacted label and, when
  useful, SHA-256 hashes of redacted summaries;
- any public command/log summary must use generic blocker codes and counts, not
  copied command lines.

## 7. Stop/replan triggers

Stop and replan if:

- Docker cannot mount authenticated Codex/OMX state and the smoke cannot run in
  a fresh container;
- the private material manifest is unsafe or cannot be summarized redacted;
- `summarize-fresh-smoke` leaks private strings or raw paths;
- the wrapper needs code changes not covered by failing public tests;
- the run reaches six or more operator cycles;
- final smoke passes despite hard-gate failures;
- the redacted summary cannot be consumed by `build_acceptance_ledger`.
