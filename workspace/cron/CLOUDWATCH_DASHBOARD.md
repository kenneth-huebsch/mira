---
cron_id: cloudwatch_dashboard
system_files:
  - capabilities/cloudwatch_dashboard/CLOUDWATCH_DASHBOARD.md
---

# CLOUDWATCH DASHBOARD CRON WRAPPER

Run Mira's morning CloudWatch dashboard check for Kenny. This cron prompt is
only the scheduler entrypoint; the capability-owned behavior lives in
`capabilities/cloudwatch_dashboard/`.

Follow standing execution rules from `AGENTS.md` and tool conventions from
`TOOLS.md`.

## TASK

1. Read `capabilities/cloudwatch_dashboard/CLOUDWATCH_DASHBOARD.md` before any
   judgment or final output.
2. Run this exact helper with `exec`:

```bash
python3 capabilities/cloudwatch_dashboard/cloudwatch_dashboard.py review
```

3. If the helper output is exactly `NO_REPLY`, return exactly:

```text
✅ No Dripr operational issues today.
```

   This heartbeat line confirms the check ran successfully with nothing to
   report; do not add anything else.
4. If the helper output is JSON with `"status":"SETUP_REQUIRED"`, return:

```text
Mira CloudWatch dashboard check needs setup before it can run.
```

5. If the helper output is JSON with `"status":"ERROR"`, return:

```text
Mira CloudWatch dashboard check failed.
```

6. If the helper output is JSON with `"status":"OK"`, use only that compact JSON
   plus the capability prompt for review. Return a short Telegram-ready alert
   that tells Kenny which CloudWatch checks need attention.

## RULES

- Do not call AWS except through the required helper.
- Do not create tasks, reminders, calendar events, notes, email, drafts, files,
  or memory.
- Do not use web search, browser tools, Gmail, Todoist, calendar, curl, or any
  network request other than the required CloudWatch helper behavior.
- Do not call Telegram or delivery tools. Return final visible text and let the
  scheduler deliver it.

## OUTPUT FORMAT

Return only one of:

- `✅ No Dripr operational issues today.`
- A short CloudWatch dashboard alert for Kenny
- `Mira CloudWatch dashboard check needs setup before it can run.`
- `Mira CloudWatch dashboard check failed.`
