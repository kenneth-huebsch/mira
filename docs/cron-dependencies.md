# Cron Dependencies

This file documents behavior-bearing files that cron jobs or cron context injection depend on.

## Cron Prompts

- `workspace/cron/KENNYS_EMAIL_TRIAGE.md`
- `workspace/cron/MEMORY_CONSOLIDATION.md`
- `workspace/cron/MORNING_BRIEF.md`
- `workspace/cron/PROACTIVE_ENGAGEMENT.md`
- `workspace/cron/RUMIS_EMAIL_TRIAGE.md`
- `workspace/cron/UPCOMING_DATES.md`

## Required Supporting Files

- `workspace/AGENTS.md` (present) - Standing execution rules and schemas referenced by cron prompts.
- `workspace/TOOLS.md` (present) - Tool account, calendar, Gmail, Todoist, Telegram, and skill conventions.
- `workspace/memory/medium_memory.jsonl` (present) - Read by Morning Brief, Memory Consolidation, Proactive Engagement, and the memory plugin.
- `workspace/memory/long_memory.jsonl` (present) - Read and rewritten by Memory Consolidation and loaded by the memory plugin.
- `workspace/memory/engagement_memory.jsonl` (present) - Read and appended by Proactive Engagement.
- `workspace/memory/engagement_priorities.jsonl` (present) - Read and rewritten by Proactive Engagement, Memory Consolidation, and the memory plugin.
- `workspace/memory/email_triage_state.jsonl` (present) - Written by email crons and compacted by Memory Consolidation.
- `workspace/memory/rolling_summary.json` (present) - Optional dynamic context loaded by the memory plugin when cron frontmatter asks for rolling_summary.
- `workspace/memory/ACTIVE_PRIORITIES.md` (present) - Optional dynamic context loaded by the memory plugin when cron frontmatter asks for active_priorities.
- `workspace/skills/memory_manager.md` (present) - Used by the memory plugin after interactive turns.
- `workspace/skills/engagement_priorities_manager.md` (present) - Used by the memory plugin after interactive turns.

## Sync Rule

Run `scripts/sync-from-live.sh` after changing Rumi behavior. It copies the allowlisted behavior files and reseeds memory/state files without copying accumulated private history.
