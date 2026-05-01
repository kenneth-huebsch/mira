---
name: operate-openclaw-crons
description: Manage, test, and debug Rumi/OpenClaw cron jobs. Use when changing cron schedules, models, payload messages, tools, thinking levels, manual runs, cron delivery behavior, or when investigating missing cron output, NO_REPLY, timeouts, or OpenClaw scheduler state.
---

# Operate OpenClaw Crons

Use this skill for live cron work on Kenny's OpenClaw/Rumi deployment.

## Core Rule

Prefer the OpenClaw cron CLI over hand-editing cron state files:

```bash
docker exec openclaw-openclaw-gateway-1 openclaw cron edit <job-id> ...
docker exec openclaw-openclaw-gateway-1 openclaw cron list --json
docker exec openclaw-openclaw-gateway-1 openclaw cron runs <job-id>
```

Direct edits to `/home/kenny/.openclaw/cron/jobs.json` can be overwritten by the live scheduler.

## Workflow

1. Identify the job id from `/home/kenny/.openclaw/cron/jobs.json` or `openclaw cron list --json`.
2. Use `openclaw cron edit` for model, message, schedule, delivery, tool allow-list, thinking, and timeout changes.
3. After a manual run, inspect `/home/kenny/.openclaw/cron/runs/<job-id>.jsonl`.
4. If the result is surprising, inspect the session transcript named by the run's `sessionId` under `/home/kenny/.openclaw/agents/main/sessions/`.
5. Verify persisted state with both the CLI and the JSON file when possible.

## Missing Output Checklist

When Kenny says a cron had no output:

- Check whether the latest run has `status: ok` with `delivered: false`. This often means the agent returned `NO_REPLY`, not that Telegram failed.
- Check whether the run has a `summary` field. If present with `delivered: true`, delivery likely worked.
- Read the session transcript to see whether the agent made tool calls, simulated the task, or returned literal `NO_REPLY`.
- For Gmail crons, run `gog` inside the OpenClaw container, not on the host:

```bash
docker exec openclaw-openclaw-gateway-1 gog ...
```

## Safe Cron Edits

When changing a cron that must use tools, consider setting:

```bash
--thinking off --tools read,exec
```

Only restrict tools when the cron's required tools are known. Do not over-restrict crons that need Todoist, calendar, write, edit, or other integrations.
