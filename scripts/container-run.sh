#!/usr/bin/env bash
# Host-side Docker wrapper for PaperOrchestra container QA.
# It always enters through scripts/container-entrypoint.sh, which updates Codex
# CLI and OMX before running the requested shell/command.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="${PAPERO_CONTAINER_IMAGE:-paperorchestra-ubuntu-tools:24.04}"
ARTIFACTS="${PAPERO_CONTAINER_ARTIFACTS:-$ROOT/.paper-orchestra/container-artifacts}"
PRIVILEGED=0
WITH_CODEX_AUTH=0
AUTH_SOURCE="${CODEX_HOME:-$HOME/.codex}"
AUTH_TMP=""
EXTRA_DOCKER_ARGS=()
COMMAND=()

usage() {
  cat <<EOF_USAGE
Usage: scripts/container-run.sh [options] [-- command ...]

Run the PaperOrchestra Docker image through a repo entrypoint that updates
Codex CLI and OMX on every container entry.

Options:
  --image IMAGE          Docker image (default: $IMAGE)
  --artifacts DIR        Host directory mounted at /artifacts.
  --privileged           Allow bwrap/user-namespace probes for omx_native_ready.
  --with-codex-auth      Copy minimal host Codex config/auth into a temp mount.
  --codex-home DIR       Source Codex home for --with-codex-auth.
  --docker-arg ARG       Additional docker run argument; repeatable.
  -h, --help             Show this help.

Examples:
  scripts/container-run.sh --privileged --with-codex-auth
  scripts/container-run.sh --privileged --with-codex-auth -- omx explore --prompt 'Return exactly OK'
EOF_USAGE
}

cleanup_auth_tmp() {
  if [[ -n "$AUTH_TMP" && -e "$AUTH_TMP" ]]; then
    docker run --rm -v "$AUTH_TMP:/cleanup:rw" ubuntu:24.04 bash -lc 'find /cleanup -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +' >/dev/null 2>&1 || true
    rm -rf "$AUTH_TMP" 2>/dev/null || true
  fi
}
trap cleanup_auth_tmp EXIT

while [[ $# -gt 0 ]]; do
  case "$1" in
    --image) IMAGE="$2"; shift 2 ;;
    --artifacts) ARTIFACTS="$2"; shift 2 ;;
    --privileged) PRIVILEGED=1; shift ;;
    --with-codex-auth) WITH_CODEX_AUTH=1; shift ;;
    --codex-home) AUTH_SOURCE="$2"; shift 2 ;;
    --docker-arg) EXTRA_DOCKER_ARGS+=("$2"); shift 2 ;;
    --) shift; COMMAND=("$@"); break ;;
    -h|--help) usage; exit 0 ;;
    *) COMMAND=("$@"); break ;;
  esac
done

mkdir -p "$ARTIFACTS"
DOCKER_ARGS=(--rm -v "$ROOT:/repo:rw" -w /repo -v "$ARTIFACTS:/artifacts:rw" --entrypoint /repo/scripts/container-entrypoint.sh)
if [[ -t 0 && -t 1 ]]; then
  DOCKER_ARGS+=(-it)
else
  DOCKER_ARGS+=(-i)
fi
if [[ "$PRIVILEGED" == "1" ]]; then
  DOCKER_ARGS+=(--privileged)
fi
if [[ "${#EXTRA_DOCKER_ARGS[@]}" -gt 0 ]]; then
  DOCKER_ARGS+=("${EXTRA_DOCKER_ARGS[@]}")
fi

if [[ "$WITH_CODEX_AUTH" == "1" ]]; then
  AUTH_TMP="$(mktemp -d "${TMPDIR:-/tmp}/paperorchestra-codex-home.XXXXXX")"
  chmod 700 "$AUTH_TMP"
  for file in auth.json config.toml AGENTS.md version.json installation_id models_cache.json; do
    if [[ -f "$AUTH_SOURCE/$file" ]]; then
      cp "$AUTH_SOURCE/$file" "$AUTH_TMP/$file"
      chmod 600 "$AUTH_TMP/$file" 2>/dev/null || true
    fi
  done
  DOCKER_ARGS+=(-v "$AUTH_TMP:/root/.codex:rw")
fi

if [[ "${#COMMAND[@]}" -eq 0 ]]; then
  COMMAND=(bash -l)
fi

docker run "${DOCKER_ARGS[@]}" "$IMAGE" "${COMMAND[@]}"
