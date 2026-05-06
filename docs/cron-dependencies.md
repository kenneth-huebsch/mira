# Cron Dependencies

This file documents behavior-bearing files that cron jobs or cron context injection depend on.

## Cron Prompts

- `workspace/cron/ENGAGEMENT_FOLLOWUPS.md`
- `workspace/cron/KENNYS_EMAIL_TRIAGE.md`
- `workspace/cron/MEMORY_CONSOLIDATION.md`
- `workspace/cron/MORNING_BRIEF.md`
- `workspace/cron/NIGHTLY_SESSION_REFLECTION.md`
- `workspace/cron/PROACTIVE_ENGAGEMENT.md`
- `workspace/cron/RUMIS_EMAIL_TRIAGE.md`
- `workspace/cron/UPCOMING_DATES.md`

## Required Supporting Files

- `workspace/AGENTS.md` (present) - Standing execution rules and schemas referenced by cron prompts.
- `workspace/USER.md` (present) - Shared non-tool, non-rule preferences and context. Cron jobs that draft, summarize, or proactively message using personal context should honor relevant preferences here.
- `workspace/TOOLS.md` (present) - Tool account, calendar, Gmail, Todoist, Telegram, OpenClaw cron creation, and skill conventions.
- `workspace/cron/memory_consolidation.py` (present) - Helper used by Memory Consolidation to perform deterministic JSONL hygiene and sidecar compaction.
- `workspace/cron/proactive_engagement.py` (present) - Helper used by Proactive Engagement to enforce eligibility, select a topic/style, and append engagement state.
- `workspace/cron/engagement_followups.py` (present) - Helper used by Engagement Follow-Ups to validate queued instructions, process due follow-ups, run supported live checks, and append engagement state.
- `workspace/cron/email_triage_preflight.py` (present) - Helper used by email triage crons to search Gmail and prepare compact message records.
- `workspace/cron/morning_brief_collect.py` (present) - Helper used by Morning Brief to collect calendar and memory facts before model-written prose.
- `workspace/cron/nightly_session_reflection.py` (present) - Helper used by Nightly Session Reflection to collect interactive transcript context, validate memory writes, audit results, and gate reset behavior.
- `workspace/memory/medium_memory.jsonl` (present) - Read by Morning Brief, Memory Consolidation, Nightly Session Reflection, Proactive Engagement, and the memory plugin; written by Nightly Session Reflection and the memory plugin.
- `workspace/memory/long_memory.jsonl` (present) - Read by Memory Consolidation, Nightly Session Reflection, and the memory plugin; written by Nightly Session Reflection when Kenny reveals durable facts.
- `workspace/memory/engagement_memory.jsonl` (present) - Read and appended by Proactive Engagement and Engagement Follow-Ups.
- `workspace/memory/engagement_priorities.jsonl` (present) - Read and rewritten by Proactive Engagement, Memory Consolidation, Nightly Session Reflection, and the memory plugin.
- `workspace/memory/engagement_followups.jsonl` (present) - Short-lived queue written by interactive Rumi through the engagement follow-up helper and processed by Engagement Follow-Ups.
- `workspace/memory/email_triage_state.jsonl` (present) - Written by email crons and compacted by Memory Consolidation.
- `workspace/memory/nightly_session_reflection_state.jsonl` (present) - Audit sidecar written by Nightly Session Reflection with counts and reset status, not transcript contents.
- `workspace/memory/rolling_summary.json` (present) - Optional dynamic context loaded by the memory plugin when cron frontmatter asks for rolling_summary.
- `workspace/memory/ACTIVE_PRIORITIES.md` (present) - Optional dynamic context loaded by the memory plugin when cron frontmatter asks for active_priorities.
- `workspace/skills/memory_manager.md` (present) - Used by the memory plugin after interactive turns.
- `workspace/skills/engagement_priorities_manager.md` (present) - Used by the memory plugin after interactive turns.

## Sync Rule

Run `scripts/sync-from-live.sh` after changing Rumi behavior. It copies the allowlisted behavior files and reseeds memory/state files without copying accumulated private history.
