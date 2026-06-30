# Cron Dependencies

This file documents behavior-bearing files that cron jobs or cron context injection depend on.

## Cron Prompts

- None configured.

## Required Supporting Files

- `workspace/AGENTS.md` (present) - Standing harness-routing policy, privacy, memory, Gmail, Telegram, and cron policy.
- `workspace/USER.md` (present) - Kenny's interaction preferences.
- `workspace/TOOLS.md` (present) - Harness routing, memory tools, on-demand Gmail, Telegram, and cron conventions.
- `workspace/skills/coding-harness/SKILL.md` (present) - Routes non-Mira coding requests through Kenny's private agent harness.
- `workspace/skills/coding-harness/coding_harness.py` (present) - Refreshes the harness and runs Cursor CLI against non-Mira target repos.
- `workspace/skills/memory-cold-store/SKILL.md` (present) - Documents ignored git-notes cold memory.
- `workspace/skills/memory-cold-store/memory_cold_store.py` (present) - Stores and searches high-value cold memories in ignored runtime storage.
- `workspace/skills/mira-memory/SKILL.md` (present) - Documents Mira's supported local-first memory stack.
- `workspace/skills/mira-memory/mira_memory_check.py` (present) - Verifies Mira's local-first memory configuration and cold store.

## QMD Recall Backend

QMD is not configured by default in the harness-routing Mira template.

Do not add QMD indexes, session exports, or `~/.openclaw/agents/*/qmd/` runtime state to this dependency map or to the backup allowlist.

## Sync Rule

Run `scripts/sync-from-live.sh` after changing Mira behavior. It copies the manifest-listed behavior files without copying accumulated private history.
