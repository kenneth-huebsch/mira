#!/usr/bin/env bash
set -euo pipefail

TARGET_WORKSPACE="${TARGET_WORKSPACE:-$HOME/.openclaw/workspace}"
BLUEPRINT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BLUEPRINT_WORKSPACE="$BLUEPRINT_ROOT/workspace"

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

touch_seed_file() {
  local rel="$1"
  local src="$BLUEPRINT_WORKSPACE/$rel"
  local dst="$TARGET_WORKSPACE/$rel"
  mkdir -p "$(dirname "$dst")"

  if [[ -e "$dst" ]]; then
    echo "kept existing: $rel"
    return 0
  fi

  if [[ -f "$src" ]]; then
    cp -p "$src" "$dst"
  elif [[ "$rel" == *.json ]]; then
    printf '{}\n' > "$dst"
  else
    : > "$dst"
  fi
  echo "seeded: $rel"
}

copy_dir() {
  local rel="$1"
  local src="$BLUEPRINT_WORKSPACE/$rel"
  local dst="$TARGET_WORKSPACE/$rel"

  if [[ ! -d "$src" ]]; then
    echo "missing in blueprint: $rel" >&2
    return 0
  fi

  rm -rf "$dst"
  mkdir -p "$(dirname "$dst")"
  cp -a "$src" "$dst"
  echo "restored dir: $rel"
}

behavior_files=(
  AGENTS.md
  SOUL.md
  IDENTITY.md
  USER.md
  TOOLS.md
  HEARTBEAT.md
  assets/rumi.jpg
  package.json
  package-lock.json
  cron/RUMIS_EMAIL_TRIAGE.md
  cron/KENNYS_EMAIL_TRIAGE.md
  cron/MORNING_BRIEF.md
  cron/MEMORY_CONSOLIDATION.md
  cron/PROACTIVE_ENGAGEMENT.md
  cron/UPCOMING_DATES.md
  plugins/memory-plugin.ts
  skills/memory_manager.md
  skills/engagement_priorities_manager.md
  skills/agent-browser/SKILL.md
)

for rel in "${behavior_files[@]}"; do
  copy_file "$rel"
done

copy_dir "skills/quick-reminders"

seed_files=(
  memory/medium_memory.jsonl
  memory/long_memory.jsonl
  memory/engagement_memory.jsonl
  memory/engagement_priorities.jsonl
  memory/email_triage_state.jsonl
  memory/rolling_summary.json
  memory/ACTIVE_PRIORITIES.md
)

for rel in "${seed_files[@]}"; do
  touch_seed_file "$rel"
done

cat <<'MSG'

Workspace behavior restored. Now manually configure:
- ~/.openclaw/openclaw.json credentials and provider auth
- ~/.openclaw/cron/jobs.json schedules/delivery, using templates/cron-jobs.friend-safe.example.json as a guide
- Gmail/Google/Todoist/Telegram credentials and OAuth tokens
MSG
