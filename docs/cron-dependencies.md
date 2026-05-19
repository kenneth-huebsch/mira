# Cron Dependencies

Mira has no recurring cron prompts by default. This file tracks dependencies for future scheduled behavior if Kenny adds any.

## Cron Prompts

- None configured.

## Required Supporting Files

- `workspace/AGENTS.md` (present) - Standing execution rules and workflow policy.
- `workspace/USER.md` (present) - Shared non-tool, non-rule preferences and context.
- `workspace/TOOLS.md` (present) - Tool account, calendar, Gmail, Todoist, Telegram, OpenClaw cron creation, and skill conventions.

## QMD Recall Backend

QMD is configured in `templates/openclaw.friend-safe.example.json` as a
read-only memory search backend over selected markdown sources:

- root workspace docs (`workspace/*.md`)
- workspace skills (`workspace/skills/**/*.md`)

QMD is read-only recall over selected markdown docs. Historical JSONL memory is
not present in Mira's blueprint, and session transcript indexing is disabled by default.
Do not add QMD indexes, session exports, or `~/.openclaw/agents/*/qmd/` runtime
state to this dependency map or to the backup allowlist.

## Sync Rule

Run `scripts/sync-from-live.sh` after changing Mira behavior. It copies the allowlisted behavior files without copying accumulated private history.
