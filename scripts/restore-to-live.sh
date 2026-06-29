#!/usr/bin/env bash
set -euo pipefail

BLUEPRINT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_OPENCLAW_HOME="${TARGET_OPENCLAW_HOME:-$BLUEPRINT_ROOT/.openclaw}"
TARGET_WORKSPACE="${TARGET_WORKSPACE:-$TARGET_OPENCLAW_HOME/workspace}"
BLUEPRINT_WORKSPACE="$BLUEPRINT_ROOT/workspace"
OPENCLAW_SOURCE="${OPENCLAW_SOURCE:-$BLUEPRINT_ROOT/openclaw-src}"
MANIFEST="$BLUEPRINT_ROOT/scripts/workspace-manifest.txt"

copy_file() {
  local rel="$1"
  local src="$BLUEPRINT_WORKSPACE/$rel"
  local dst="$TARGET_WORKSPACE/$rel"

  if [[ ! -f "$src" ]]; then
    echo "missing in blueprint: $rel" >&2
    return 1
  fi

  mkdir -p "$(dirname "$dst")"
  cp -p "$src" "$dst"
  echo "restored: $rel"
}

restore_openclaw_file() {
  local rel="$1"
  local src="$BLUEPRINT_ROOT/openclaw/$rel"
  local dst="$OPENCLAW_SOURCE/$rel"

  if [[ ! -f "$src" ]]; then
    echo "missing in blueprint: openclaw/$rel" >&2
    return 0
  fi

  mkdir -p "$(dirname "$dst")"
  cp -p "$src" "$dst"
  if [[ "$rel" == "entrypoint.sh" ]]; then
    chmod 755 "$dst"
  fi
  echo "restored openclaw: $rel"
}

clean_managed_workspace() {
  mkdir -p "$TARGET_WORKSPACE"
  rm -rf \
    "$TARGET_WORKSPACE/.clawhub" \
    "$TARGET_WORKSPACE/capabilities" \
    "$TARGET_WORKSPACE/cron" \
    "$TARGET_WORKSPACE/memory" \
    "$TARGET_WORKSPACE/plugins" \
    "$TARGET_WORKSPACE/runtime" \
    "$TARGET_WORKSPACE/skills"
  echo "cleaned managed workspace directories"
}

clean_managed_workspace

while IFS= read -r rel || [[ -n "$rel" ]]; do
  [[ -z "$rel" || "$rel" == \#* ]] && continue
  copy_file "$rel"
done < "$MANIFEST"

restore_openclaw_file "docker-compose.yml"
restore_openclaw_file "entrypoint.sh"

cat <<MSG

Workspace behavior restored. Now manually configure:
- $TARGET_OPENCLAW_HOME/openclaw.json credentials and provider auth
- $TARGET_OPENCLAW_HOME/cron/jobs.json as an empty jobs config unless Kenny adds scheduled behavior
- Telegram credentials and Mira Gmail OAuth for on-demand Gmail checks
- Provider secrets under $TARGET_OPENCLAW_HOME/secrets/ before starting the container
MSG
