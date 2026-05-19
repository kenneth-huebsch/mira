#!/usr/bin/env bash
set -euo pipefail

BLUEPRINT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_OPENCLAW_HOME="${TARGET_OPENCLAW_HOME:-$BLUEPRINT_ROOT/.openclaw}"
TARGET_WORKSPACE="${TARGET_WORKSPACE:-$TARGET_OPENCLAW_HOME/workspace}"
BLUEPRINT_WORKSPACE="$BLUEPRINT_ROOT/workspace"
OPENCLAW_SOURCE="${OPENCLAW_SOURCE:-$BLUEPRINT_ROOT/openclaw-src}"

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
  chmod 755 "$dst"
  echo "restored openclaw: $rel"
}

install_output_hygiene_extension() {
  local src="$TARGET_WORKSPACE/plugins/output-hygiene-plugin.ts"
  local openclaw_home
  openclaw_home="$(cd "$TARGET_WORKSPACE/.." && pwd)"
  local dst_dir="$openclaw_home/extensions/output-hygiene-plugin"

  if [[ ! -f "$src" ]]; then
    echo "missing live plugin source: plugins/output-hygiene-plugin.ts" >&2
    return 1
  fi

  mkdir -p "$dst_dir"
  cp -p "$src" "$dst_dir/index.ts"
  cat > "$dst_dir/package.json" <<'JSON'
{
  "name": "output-hygiene-plugin",
  "version": "1.0.0",
  "type": "module",
  "openclaw": {
    "extensions": ["./index.ts"]
  }
}
JSON
  cat > "$dst_dir/openclaw.plugin.json" <<'JSON'
{
  "id": "output-hygiene-plugin",
  "name": "Mira Output Hygiene",
  "description": "Filters obvious tool-call markup and process narration before Telegram delivery",
  "configSchema": {
    "type": "object",
    "additionalProperties": false
  }
}
JSON
  chown -R root:root "$dst_dir" 2>/dev/null || true
  echo "installed extension: output-hygiene-plugin"
}

install_memory_plugin_extension() {
  local src="$TARGET_WORKSPACE/plugins/memory-plugin.ts"
  local openclaw_home
  openclaw_home="$(cd "$TARGET_WORKSPACE/.." && pwd)"
  local dst_dir="$openclaw_home/extensions/workspace-medium-memory"

  if [[ ! -f "$src" ]]; then
    echo "missing live plugin source: plugins/memory-plugin.ts" >&2
    return 1
  fi

  mkdir -p "$dst_dir"
  cp -p "$src" "$dst_dir/index.ts"
  cat > "$dst_dir/package.json" <<'JSON'
{
  "name": "workspace-medium-memory",
  "version": "1.0.0",
  "type": "module",
  "openclaw": {
    "extensions": ["./index.ts"]
  }
}
JSON
  cat > "$dst_dir/openclaw.plugin.json" <<'JSON'
{
  "id": "workspace-medium-memory",
  "name": "Workspace Context Loader",
  "description": "Loads Mira workspace memory and capability context into agent runs",
  "configSchema": {
    "type": "object",
    "additionalProperties": false
  }
}
JSON
  chown -R root:root "$dst_dir" 2>/dev/null || true
  echo "installed extension: workspace-medium-memory"
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

install_output_hygiene_extension
install_memory_plugin_extension

copy_dir "skills/quick-reminders"
restore_openclaw_file "entrypoint.sh"

seed_files=(
  memory/medium_memory.jsonl
  memory/long_memory.jsonl
  memory/rolling_summary.json
)

for rel in "${seed_files[@]}"; do
  touch_seed_file "$rel"
done

cat <<MSG

Workspace behavior restored. Now manually configure:
- $TARGET_OPENCLAW_HOME/openclaw.json credentials and provider auth
- cron jobs only if Kenny explicitly asks for scheduled behavior
- Gmail/Google/Todoist/Telegram credentials and OAuth tokens
- Docker compose mounts for openclaw/entrypoint.sh if using the container runtime
MSG
