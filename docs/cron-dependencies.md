# Cron Dependencies

This file documents behavior-bearing files that cron jobs or cron context injection depend on.

## Cron Prompts

- None configured.

## Required Supporting Files

- `workspace/AGENTS.md` (present) - Standing coding workflow, privacy, Gmail, Telegram, and cron policy.
- `workspace/USER.md` (present) - Kenny's coding collaboration preferences.
- `workspace/TOOLS.md` (present) - Coding tool, on-demand Gmail, Telegram, and cron conventions.

## QMD Recall Backend

QMD is not configured by default in the coding-only Mira template.

Do not add QMD indexes, session exports, or `~/.openclaw/agents/*/qmd/` runtime state to this dependency map or to the backup allowlist.

## Sync Rule

Run `scripts/sync-from-live.sh` after changing Mira behavior. It copies the manifest-listed behavior files without copying accumulated private history.
