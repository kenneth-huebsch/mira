#!/usr/bin/env bash
set -euo pipefail

LIVE_WORKSPACE="${LIVE_WORKSPACE:-$HOME/.openclaw/workspace}"
BLUEPRINT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BLUEPRINT_WORKSPACE="$BLUEPRINT_ROOT/workspace"
OPENCLAW_SOURCE="${OPENCLAW_SOURCE:-$HOME/openclaw}"

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
  cron/memory_consolidation.py
  cron/NIGHTLY_SESSION_REFLECTION.md
  cron/nightly_session_reflection.py
  cron/PROACTIVE_ENGAGEMENT.md
  cron/proactive_engagement.py
  cron/email_triage_preflight.py
  cron/email_triage_record.py
  cron/morning_brief_collect.py
  cron/UPCOMING_DATES.md
  cron/ENGAGEMENT_FOLLOWUPS.md
  cron/engagement_followups.py
  plugins/memory-plugin.ts
  plugins/output-hygiene-plugin.ts
  skills/memory_manager.md
  skills/engagement_priorities_manager.md
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
  memory/engagement_memory.jsonl
  memory/engagement_priorities.jsonl
  memory/engagement_followups.jsonl
  memory/email_triage_state.jsonl
  memory/nightly_session_reflection_state.jsonl
  memory/rolling_summary.json
  memory/ACTIVE_PRIORITIES.md
)

for rel in "${seed_files[@]}"; do
  seed_file "$rel"
done

# Local skill currently lives in the OpenClaw source checkout, not the workspace.
copy_dir "$OPENCLAW_SOURCE/skills/quick-reminders" "$BLUEPRINT_WORKSPACE/skills/quick-reminders"

"$BLUEPRINT_ROOT/scripts/write-derived-files.sh"
