#!/usr/bin/env bash
# Load ignored, per-instance provider credentials for this OpenClaw home.
load_openclaw_secret_env() {
  local env_file="${OPENCLAW_SECRET_ENV_FILE:-$BLUEPRINT_ROOT/.openclaw/secrets/openrouter.env}"
  if [[ -f "$env_file" ]]; then
    set -a
    # shellcheck disable=SC1090
    . "$env_file"
    set +a
  fi

  local memory_env_file="${OPENCLAW_MEMORY_SECRET_ENV_FILE:-$BLUEPRINT_ROOT/.openclaw/secrets/memory.env}"
  if [[ -f "$memory_env_file" ]]; then
    set -a
    # shellcheck disable=SC1090
    . "$memory_env_file"
    set +a
  fi
}
