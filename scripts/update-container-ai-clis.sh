#!/usr/bin/env bash
# Update the AI CLIs that PaperOrchestra container QA depends on.
#
# This is intentionally derived from ~/helper/update-ai-clis.sh, narrowed to the
# two tools that must be fresh in PaperOrchestra containers:
#   - OMX (oh-my-codex)
#   - Codex CLI (@openai/codex)
#
# By default this script only performs installs inside a container. Use
# --allow-host if an operator explicitly wants to reuse it on the host.

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
MODE="update"
FORCE="${PAPERO_CONTAINER_AI_CLI_UPDATE_FORCE:-false}"
QUIET="${PAPERO_CONTAINER_AI_CLI_UPDATE_QUIET:-false}"
ALLOW_HOST="${PAPERO_CONTAINER_AI_CLI_UPDATE_ALLOW_HOST:-false}"
REQUIRE_CONTAINER="${PAPERO_CONTAINER_AI_CLI_UPDATE_REQUIRE_CONTAINER:-true}"
NPM_BIN="${NPM_BIN:-npm}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
INSTALL_PREREQS="${PAPERO_CONTAINER_AI_CLI_INSTALL_PREREQS:-1}"

readonly NPM_PACKAGES=(
  "OMX|oh-my-codex|omx"
  "Codex CLI|@openai/codex|codex"
)

usage() {
  cat <<EOF_USAGE
Usage: $SCRIPT_NAME [options]

Update container AI CLIs used by PaperOrchestra:
  - oh-my-codex (omx)
  - @openai/codex (codex)

Options:
  --check        Compare current/latest versions only; do not install.
  --force        Reinstall even when current == latest.
  --quiet        Reduce progress logging.
  --allow-host   Permit updating outside a detected container.
  -h, --help     Show this help.

Environment:
  PAPERO_UPDATE_CONTAINER_AI_CLIS=0       Skip all updates when called by repo scripts.
  PAPERO_CONTAINER_AI_CLI_UPDATE_FORCE=1  Same as --force.
  PAPERO_CONTAINER_AI_CLI_INSTALL_PREREQS=0
                                           Do not apt-install xz-utils/bubblewrap.
  NPM_BIN=/path/to/npm                    Override npm command for debugging.
  PYTHON_BIN=/path/to/python3             Override python command for debugging.
EOF_USAGE
}

log() {
  if [[ "$QUIET" != "true" && "$QUIET" != "1" ]]; then
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
  fi
}

warn() {
  printf '[%s] WARN: %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2
}

fail() {
  printf '[%s] ERROR: %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "required command not found: $1"
}

apt_install_prefix() {
  if [[ "$(id -u)" == "0" ]]; then
    printf ''
  elif command -v sudo >/dev/null 2>&1; then
    printf 'sudo '
  else
    return 1
  fi
}

ensure_container_prereqs() {
  local missing=() prefix
  command -v xz >/dev/null 2>&1 || missing+=(xz-utils)
  command -v bwrap >/dev/null 2>&1 || missing+=(bubblewrap)
  if [[ "${#missing[@]}" -eq 0 ]]; then
    return 0
  fi

  if [[ "$MODE" == "check" || "$INSTALL_PREREQS" == "0" ]]; then
    warn "container prerequisite packages missing: ${missing[*]}"
    return 0
  fi

  command -v apt-get >/dev/null 2>&1 || fail "apt-get not available; install missing container prerequisites manually: ${missing[*]}"
  prefix="$(apt_install_prefix)" || fail "cannot install missing container prerequisites without root or sudo: ${missing[*]}"
  log "Installing container prerequisites for OMX/Codex control surfaces: ${missing[*]}"
  ${prefix}apt-get update -qq
  # shellcheck disable=SC2086
  ${prefix}apt-get install -y -qq "${missing[@]}"
}

truthy() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

is_container() {
  [[ -f /.dockerenv ]] && return 0
  [[ -f /run/.containerenv ]] && return 0
  grep -qaE '/docker/|/kubepods/|/containerd/' /proc/1/cgroup 2>/dev/null
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --check) MODE="check" ;;
      --force) FORCE=true ;;
      --quiet) QUIET=true ;;
      --allow-host) ALLOW_HOST=true ;;
      -h|--help) usage; exit 0 ;;
      *) fail "unknown option: $1" ;;
    esac
    shift
  done
}

npm_global_root() {
  "$NPM_BIN" root -g 2>/dev/null
}

needs_sudo_for_npm() {
  local root
  root="$(npm_global_root || true)"
  [[ -n "$root" && ! -w "$root" ]]
}

sudo_cache() {
  if needs_sudo_for_npm; then
    need_cmd sudo
    log "npm global root is not writable; acquiring sudo once."
    sudo -v
  fi
}

npm_pkg_current() {
  local pkg="$1"
  "$NPM_BIN" -g list "$pkg" --depth=0 --json 2>/dev/null | "$PYTHON_BIN" -c '
import json, sys
pkg = sys.argv[1]
try:
    data = json.load(sys.stdin)
except Exception:
    data = {}
deps = data.get("dependencies", {}) if isinstance(data, dict) else {}
entry = deps.get(pkg) if isinstance(deps, dict) else None
print(entry.get("version", "") if isinstance(entry, dict) else "")
' "$pkg"
}

npm_pkg_latest() {
  local pkg="$1"
  "$NPM_BIN" view "$pkg" version 2>/dev/null || true
}

compare_versions() {
  local current="$1" latest="$2"
  if [[ -z "$current" ]]; then
    printf 'not-installed'
  elif [[ -z "$latest" ]]; then
    printf 'latest-unknown'
  elif [[ "$current" == "$latest" ]]; then
    printf 'up-to-date'
  else
    printf 'update-available'
  fi
}

print_npm_status() {
  local label="$1" pkg="$2"
  local current latest status
  current="$(npm_pkg_current "$pkg")"
  latest="$(npm_pkg_latest "$pkg")"
  status="$(compare_versions "$current" "$latest")"
  printf '%-10s current=%-14s latest=%-14s status=%s\n' \
    "$label" "${current:-missing}" "${latest:-unknown}" "$status"
}

update_npm_package() {
  local label="$1" pkg="$2"
  local current latest
  current="$(npm_pkg_current "$pkg")"
  latest="$(npm_pkg_latest "$pkg")"

  if ! truthy "$FORCE" && [[ -n "$current" && -n "$latest" && "$current" == "$latest" ]]; then
    log "$label is already current ($current)."
    return 0
  fi

  log "Updating $label (${current:-missing} -> ${latest:-latest})."
  if needs_sudo_for_npm; then
    sudo "$NPM_BIN" install -g "$pkg@latest"
  else
    "$NPM_BIN" install -g "$pkg@latest"
  fi
}

main() {
  local failures=() label pkg cmd

  parse_args "$@"

  if [[ "${PAPERO_UPDATE_CONTAINER_AI_CLIS:-1}" == "0" ]]; then
    log "PAPERO_UPDATE_CONTAINER_AI_CLIS=0; skipping container AI CLI update."
    exit 0
  fi

  if ! is_container && ! truthy "$ALLOW_HOST"; then
    if truthy "$REQUIRE_CONTAINER"; then
      fail "refusing to update host AI CLIs without --allow-host"
    fi
    log "not in a detected container; skipping."
    exit 0
  fi

  need_cmd "$NPM_BIN"
  need_cmd "$PYTHON_BIN"
  ensure_container_prereqs

  log "Container AI CLI pre-update status:"
  for spec in "${NPM_PACKAGES[@]}"; do
    IFS='|' read -r label pkg cmd <<<"$spec"
    if ! command -v "$cmd" >/dev/null 2>&1; then
      warn "$label command ($cmd) is not on PATH before update; npm install will still be attempted."
    fi
    print_npm_status "$label" "$pkg"
  done

  if [[ "$MODE" == "check" ]]; then
    exit 0
  fi

  sudo_cache

  for spec in "${NPM_PACKAGES[@]}"; do
    IFS='|' read -r label pkg _ <<<"$spec"
    if ! update_npm_package "$label" "$pkg"; then
      failures+=("$label")
    fi
  done

  log "Container AI CLI post-update status:"
  for spec in "${NPM_PACKAGES[@]}"; do
    IFS='|' read -r label pkg cmd <<<"$spec"
    print_npm_status "$label" "$pkg"
    if command -v "$cmd" >/dev/null 2>&1; then
      "$cmd" --version 2>/dev/null | head -n 1 || true
    fi
  done

  if [[ "${#failures[@]}" -gt 0 ]]; then
    fail "AI CLI update failed for: ${failures[*]}"
  fi
}

main "$@"
