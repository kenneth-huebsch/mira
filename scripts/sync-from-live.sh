#!/usr/bin/env bash
set -euo pipefail

BLUEPRINT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIVE_OPENCLAW_HOME="${LIVE_OPENCLAW_HOME:-$BLUEPRINT_ROOT/.openclaw}"
LIVE_WORKSPACE="${LIVE_WORKSPACE:-$LIVE_OPENCLAW_HOME/workspace}"
BLUEPRINT_WORKSPACE="$BLUEPRINT_ROOT/workspace"
OPENCLAW_SOURCE="${OPENCLAW_SOURCE:-$BLUEPRINT_ROOT/openclaw-src}"
MANIFEST="$BLUEPRINT_ROOT/scripts/workspace-manifest.txt"

copy_file() {
  local rel="$1"
  local src="$LIVE_WORKSPACE/$rel"
  local dst="$BLUEPRINT_WORKSPACE/$rel"

  if [[ ! -f "$src" ]]; then
    echo "missing: $rel" >&2
    return 0
  fi

  mkdir -p "$(dirname "$dst")"
  cp -p "$src" "$dst"
  echo "copied: $rel"
}

copy_openclaw_file() {
  local rel="$1"
  local src="$OPENCLAW_SOURCE/$rel"
  local dst="$BLUEPRINT_ROOT/openclaw/$rel"

  if [[ ! -f "$src" ]]; then
    echo "missing openclaw file: $rel" >&2
    return 0
  fi

  mkdir -p "$(dirname "$dst")"
  cp -p "$src" "$dst"
  echo "copied openclaw: $rel"
}

while IFS= read -r rel || [[ -n "$rel" ]]; do
  [[ -z "$rel" || "$rel" == \#* ]] && continue
  copy_file "$rel"
done < "$MANIFEST"

copy_openclaw_file "entrypoint.sh"

"$BLUEPRINT_ROOT/scripts/write-derived-files.sh"
