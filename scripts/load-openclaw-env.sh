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

  local n8n_env_file="${OPENCLAW_N8N_SECRET_ENV_FILE:-$BLUEPRINT_ROOT/.openclaw/secrets/n8n.env}"
  if [[ -f "$n8n_env_file" ]]; then
    set -a
    # shellcheck disable=SC1090
    . "$n8n_env_file"
    set +a
  fi

  local wordpress_env_file="${OPENCLAW_WORDPRESS_SECRET_ENV_FILE:-$BLUEPRINT_ROOT/.openclaw/secrets/wordpress.env}"
  if [[ -f "$wordpress_env_file" ]]; then
    set -a
    # shellcheck disable=SC1090
    . "$wordpress_env_file"
    set +a
  fi
}
