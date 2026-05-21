#!/usr/bin/env bash
# PaperOrchestra container entrypoint.
# Runs the mandatory Codex CLI / OMX update before handing control to the user
# or one-shot command. Use via scripts/container-run.sh or Docker --entrypoint.

set -euo pipefail

find_repo_root() {
  if [[ -n "${PAPERO_CONTAINER_REPO_ROOT:-}" && -x "$PAPERO_CONTAINER_REPO_ROOT/scripts/update-container-ai-clis.sh" ]]; then
    printf '%s\n' "$PAPERO_CONTAINER_REPO_ROOT"
    return 0
  fi
  for candidate in /repo "$PWD" /workspace /work; do
    if [[ -x "$candidate/scripts/update-container-ai-clis.sh" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

if repo_root="$(find_repo_root)"; then
  "$repo_root/scripts/update-container-ai-clis.sh"
  if command -v git >/dev/null 2>&1; then
    git config --global --add safe.directory "$repo_root" >/dev/null 2>&1 || true
    if [[ -d "$repo_root/.git" ]]; then
      git config --global --add safe.directory "$repo_root/.git" >/dev/null 2>&1 || true
    fi
  fi
else
  echo "[paperorchestra-container] WARN: update script not found; continuing without AI CLI update" >&2
fi

if [[ $# -eq 0 ]]; then
  exec bash -l
fi

exec "$@"
