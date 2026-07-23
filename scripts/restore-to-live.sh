#!/usr/bin/env bash
set -euo pipefail

BLUEPRINT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_OPENCLAW_HOME="${TARGET_OPENCLAW_HOME:-$BLUEPRINT_ROOT/.openclaw}"
TARGET_WORKSPACE="${TARGET_WORKSPACE:-$TARGET_OPENCLAW_HOME/workspace}"
OPENCLAW_SOURCE="${OPENCLAW_SOURCE:-$BLUEPRINT_ROOT/openclaw-src}"
MANIFEST="${WORKSPACE_MANIFEST:-$BLUEPRINT_ROOT/scripts/workspace-manifest.txt}"

python3 "$BLUEPRINT_ROOT/scripts/managed_transaction.py" \
  restore "$BLUEPRINT_ROOT" "$TARGET_OPENCLAW_HOME" "$TARGET_WORKSPACE" "$OPENCLAW_SOURCE" "$MANIFEST"

# Memory scaffolds are create-only and are deliberately outside the managed-file
# replacement transaction. Existing memory and all runtime state are untouched.
if [[ -L "$TARGET_WORKSPACE" || -L "$TARGET_WORKSPACE/memory" ]]; then
  echo "refusing symlinked workspace or memory scaffold destination" >&2
  exit 1
fi
mkdir -p "$TARGET_WORKSPACE/memory"
for name in SESSION-STATE.md MEMORY.md DREAMS.md; do
  src="$BLUEPRINT_ROOT/templates/memory-scaffold/$name"
  dst="$TARGET_WORKSPACE/$name"
  if [[ -f "$src" && ! -e "$dst" && ! -L "$dst" ]]; then
    cp -p "$src" "$dst"
  fi
done
today="$(date +%F)"
daily="$TARGET_WORKSPACE/memory/$today.md"
if [[ -f "$BLUEPRINT_ROOT/templates/memory-scaffold/daily-template.md" && ! -e "$daily" && ! -L "$daily" ]]; then
  sed "s/YYYY-MM-DD/$today/g" "$BLUEPRINT_ROOT/templates/memory-scaffold/daily-template.md" > "$daily"
fi

echo "Workspace behavior restored without deleting runtime or existing memory."
