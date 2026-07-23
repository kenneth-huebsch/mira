#!/usr/bin/env bash
set -euo pipefail

BLUEPRINT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIVE_OPENCLAW_HOME="${LIVE_OPENCLAW_HOME:-$BLUEPRINT_ROOT/.openclaw}"
LIVE_WORKSPACE="${LIVE_WORKSPACE:-$LIVE_OPENCLAW_HOME/workspace}"
OPENCLAW_SOURCE="${OPENCLAW_SOURCE:-$BLUEPRINT_ROOT/openclaw-src}"
MANIFEST="${WORKSPACE_MANIFEST:-$BLUEPRINT_ROOT/scripts/workspace-manifest.txt}"

python3 "$BLUEPRINT_ROOT/scripts/managed_transaction.py" \
  sync "$BLUEPRINT_ROOT" "$LIVE_OPENCLAW_HOME" "$LIVE_WORKSPACE" "$OPENCLAW_SOURCE" "$MANIFEST"

"$BLUEPRINT_ROOT/scripts/write-derived-files.sh"
