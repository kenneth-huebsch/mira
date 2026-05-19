#!/usr/bin/env bash
set -euo pipefail

BLUEPRINT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OPENCLAW_SOURCE="${OPENCLAW_SOURCE:-$BLUEPRINT_ROOT/openclaw-src}"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-openclaw-mira}"

if [[ ! -d "$OPENCLAW_SOURCE" ]]; then
  echo "missing OpenClaw checkout: $OPENCLAW_SOURCE" >&2
  exit 1
fi

cd "$OPENCLAW_SOURCE"
exec docker compose -p "$COMPOSE_PROJECT_NAME" down
