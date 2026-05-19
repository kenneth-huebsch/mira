# Cron Dependencies

This file documents behavior-bearing files that cron jobs or cron context injection depend on.

## Cron Prompts

- `workspace/cron/CLOUDWATCH_DASHBOARD.md`
- `workspace/cron/DRIPR_INBOX_TRIAGE.md`
- `workspace/cron/MYSQL_NEW_USERS.md`

## Required Supporting Files

- `workspace/AGENTS.md` (present) - Standing execution rules, mode policy, cron policy, and privacy rules.
- `workspace/USER.md` (present) - Shared non-tool, non-rule preferences and context.
- `workspace/TOOLS.md` (present) - Tool account, calendar, Gmail, MySQL, CloudWatch, Todoist, Telegram, OpenClaw cron creation, and skill conventions.
- `workspace/capabilities/dripr_inbox_triage/README.md` (present) - Capability overview for Dripr Inbox Triage, including source addresses and Gmail boundaries.
- `workspace/capabilities/dripr_inbox_triage/DRIPR_INBOX_TRIAGE.md` (present) - Capability-owned behavior for judging dripr mail and writing Kenny-facing summaries.
- `workspace/capabilities/dripr_inbox_triage/dripr_inbox_triage.py` (present) - Helper used by Dripr Inbox Triage to search Gmail and prepare compact message records.
- `workspace/capabilities/mysql_new_users/README.md` (present) - Capability overview for MySQL New Users, including setup and credential boundaries.
- `workspace/capabilities/mysql_new_users/MYSQL_NEW_USERS.md` (present) - Capability-owned behavior for summarizing new users and setup failures.
- `workspace/capabilities/mysql_new_users/mysql_new_users.py` (present) - Helper used by MySQL New Users to query MySQL and prepare compact user records.
- `workspace/capabilities/cloudwatch_dashboard/README.md` (present) - Capability overview for CloudWatch Dashboard, including setup and credential boundaries.
- `workspace/capabilities/cloudwatch_dashboard/CLOUDWATCH_DASHBOARD.md` (present) - Capability-owned behavior for summarizing dashboard threshold breaches and setup failures.
- `workspace/capabilities/cloudwatch_dashboard/cloudwatch_dashboard.py` (present) - Helper used by CloudWatch Dashboard to query CloudWatch and prepare compact issue records.

## QMD Recall Backend

QMD is configured in `templates/openclaw.friend-safe.example.json` as a
read-only memory search backend over selected markdown sources:

- root workspace docs (`workspace/*.md`)
- capability docs (`workspace/capabilities/**/*.md`)
- workspace skills (`workspace/skills/**/*.md`)

QMD is read-only recall over selected markdown docs. Historical JSONL memory is
not present in Mira's blueprint, and session transcript indexing is disabled by default.
Do not add QMD indexes, session exports, or `~/.openclaw/agents/*/qmd/` runtime
state to this dependency map or to the backup allowlist.

## Sync Rule

Run `scripts/sync-from-live.sh` after changing Mira behavior. It copies the allowlisted behavior files without copying accumulated private history.
