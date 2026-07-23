#!/usr/bin/env bash
set -euo pipefail

BLUEPRINT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OPENCLAW_SOURCE="${OPENCLAW_SOURCE:-$BLUEPRINT_ROOT/openclaw-src}"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-openclaw-mira}"

export OPENCLAW_CONFIG_DIR="${OPENCLAW_CONFIG_DIR:-$BLUEPRINT_ROOT/.openclaw}"
export OPENCLAW_WORKSPACE_DIR="${OPENCLAW_WORKSPACE_DIR:-$OPENCLAW_CONFIG_DIR/workspace}"
export OPENCLAW_GATEWAY_PORT="${OPENCLAW_GATEWAY_PORT:-18791}"
export OPENCLAW_BRIDGE_PORT="${OPENCLAW_BRIDGE_PORT:-18792}"
export OPENCLAW_UI_PORT="${OPENCLAW_UI_PORT:-3501}"
export OPENCLAW_TZ="${OPENCLAW_TZ:-America/New_York}"

# Load per-instance provider credentials after defaults so this claw does not
# inherit another OpenClaw home's model auth from the shell.
# shellcheck source=scripts/load-openclaw-env.sh
. "$BLUEPRINT_ROOT/scripts/load-openclaw-env.sh"
load_openclaw_secret_env

compose_files=(-f docker-compose.yml -f "$BLUEPRINT_ROOT/openclaw/provider-auth.compose.yml")

if [[ ! -d "$OPENCLAW_SOURCE" ]]; then
  echo "missing OpenClaw checkout: $OPENCLAW_SOURCE" >&2
  exit 1
fi

cd "$OPENCLAW_SOURCE"
exec docker compose -p "$COMPOSE_PROJECT_NAME" "${compose_files[@]}" up -d openclaw-gateway
