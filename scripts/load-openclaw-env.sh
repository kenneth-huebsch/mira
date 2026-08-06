#!/usr/bin/env bash
# Load this OpenClaw home's ignored environment file for Compose interpolation.
load_openclaw_secret_env() {
  local env_file="${OPENCLAW_ENV_FILE:-$BLUEPRINT_ROOT/.openclaw/.env}"
  if [[ -f "$env_file" ]]; then
    set -a
    # shellcheck disable=SC1090
    . "$env_file"
    set +a
  fi
}
