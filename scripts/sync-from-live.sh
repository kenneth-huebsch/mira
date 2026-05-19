#!/usr/bin/env bash
set -euo pipefail

BLUEPRINT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIVE_OPENCLAW_HOME="${LIVE_OPENCLAW_HOME:-$BLUEPRINT_ROOT/.openclaw}"
LIVE_WORKSPACE="${LIVE_WORKSPACE:-$LIVE_OPENCLAW_HOME/workspace}"
BLUEPRINT_WORKSPACE="$BLUEPRINT_ROOT/workspace"
OPENCLAW_SOURCE="${OPENCLAW_SOURCE:-$BLUEPRINT_ROOT/openclaw-src}"

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

seed_file() {
  local rel="$1"
  local dst="$BLUEPRINT_WORKSPACE/$rel"
  mkdir -p "$(dirname "$dst")"

  if [[ "$rel" == *.json ]]; then
    printf '{}\n' > "$dst"
  else
    : > "$dst"
  fi
  echo "seeded: $rel"
}

copy_dir() {
  local src="$1"
  local dst="$2"

  if [[ ! -d "$src" ]]; then
    echo "missing dir: $src" >&2
    return 0
  fi

  rm -rf "$dst"
  mkdir -p "$(dirname "$dst")"
  cp -a "$src" "$dst"
  echo "copied dir: ${dst#$BLUEPRINT_ROOT/}"
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

behavior_files=(
  AGENTS.md
  SOUL.md
  IDENTITY.md
  USER.md
  TOOLS.md
  HEARTBEAT.md
  package.json
  package-lock.json
  plugins/memory-plugin.ts
  plugins/output-hygiene-plugin.ts
  skills/memory_manager.md
  skills/agent-browser/SKILL.md
)

for rel in "${behavior_files[@]}"; do
  copy_file "$rel"
done

# These files are cron/plugin dependencies. Keep paths and schemas present,
# but do not copy accumulated live memory/history into the blueprint.
seed_files=(
  memory/medium_memory.jsonl
  memory/long_memory.jsonl
  memory/rolling_summary.json
)

for rel in "${seed_files[@]}"; do
  seed_file "$rel"
done

# Local skill currently lives in the OpenClaw source checkout, not the workspace.
copy_dir "$OPENCLAW_SOURCE/skills/quick-reminders" "$BLUEPRINT_WORKSPACE/skills/quick-reminders"
copy_openclaw_file "entrypoint.sh"

"$BLUEPRINT_ROOT/scripts/write-derived-files.sh"
