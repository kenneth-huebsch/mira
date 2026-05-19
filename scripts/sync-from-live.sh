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
  cron/DRIPR_INBOX_TRIAGE.md
  cron/MYSQL_NEW_USERS.md
  cron/CLOUDWATCH_DASHBOARD.md
  plugins/output-hygiene-plugin.ts
  skills/agent-browser/SKILL.md
)

for rel in "${behavior_files[@]}"; do
  copy_file "$rel"
done

copy_dir "$LIVE_WORKSPACE/capabilities/dripr_inbox_triage" "$BLUEPRINT_WORKSPACE/capabilities/dripr_inbox_triage"
copy_dir "$LIVE_WORKSPACE/capabilities/mysql_new_users" "$BLUEPRINT_WORKSPACE/capabilities/mysql_new_users"
copy_dir "$LIVE_WORKSPACE/capabilities/cloudwatch_dashboard" "$BLUEPRINT_WORKSPACE/capabilities/cloudwatch_dashboard"

# Local skill currently lives in the OpenClaw source checkout, not the workspace.
copy_dir "$OPENCLAW_SOURCE/skills/quick-reminders" "$BLUEPRINT_WORKSPACE/skills/quick-reminders"
copy_openclaw_file "entrypoint.sh"

"$BLUEPRINT_ROOT/scripts/write-derived-files.sh"
