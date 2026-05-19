# Cron Dependencies

Mira has no recurring cron prompts by default. This file tracks dependencies for future scheduled behavior if Kenny adds any.

## Cron Prompts

- None configured.

## Required Supporting Files

- `workspace/AGENTS.md` (present) - Standing execution rules and workflow policy.
- `workspace/USER.md` (present) - Shared non-tool, non-rule preferences and context.
- `workspace/TOOLS.md` (present) - Tool account, calendar, Gmail, Todoist, Telegram, OpenClaw cron creation, and skill conventions.
- `workspace/memory/medium_memory.jsonl` (present) - Read and written by the memory plugin for time-bounded interactive context.
- `workspace/memory/long_memory.jsonl` (present) - Read by the memory plugin for durable context.
- `workspace/memory/rolling_summary.json` (present) - Optional dynamic context available to the memory plugin.
- `workspace/skills/memory_manager.md` (present) - Used by the memory plugin after interactive turns.

## QMD Recall Backend

QMD is configured in `templates/openclaw.friend-safe.example.json` as a
read-only memory search backend over selected markdown sources:

- root workspace docs (`workspace/*.md`)
- workspace skills (`workspace/skills/**/*.md`)

QMD does not replace the curated JSONL files above. Historical JSONL memory is
not backfilled into QMD, and session transcript indexing is disabled by default.
Do not add QMD indexes, session exports, or `~/.openclaw/agents/*/qmd/` runtime
state to this dependency map or to the backup allowlist.

## Sync Rule

Run `scripts/sync-from-live.sh` after changing Mira behavior. It copies the allowlisted behavior files and reseeds memory files without copying accumulated private history.
