---
cron_id: dripr_reddit_followups
system_files:
  - capabilities/dripr_reddit_followups/DRIPR_REDDIT_FOLLOWUPS.md
---

# DRIPR REDDIT FOLLOW-UPS CRON WRAPPER

Run Mira's Dripr Reddit follow-up check for Kenny. This cron prompt is only the
scheduler entrypoint; the capability-owned behavior lives in
`capabilities/dripr_reddit_followups/`.

Follow standing execution rules from `AGENTS.md` and tool conventions from
`TOOLS.md`.

## TASK

1. Read `capabilities/dripr_reddit_followups/DRIPR_REDDIT_FOLLOWUPS.md` before any
   judgment or final output.
2. Run this exact helper with `exec`:

```bash
python3 capabilities/dripr_reddit_followups/dripr_reddit_followups.py review
```

3. If the helper output is exactly `NO_REPLY`, return exactly:

```text
NO_REPLY
```

4. If the helper output is JSON with `"status":"SETUP_REQUIRED"`, return:

```text
Mira Dripr Reddit follow-up check needs setup before it can run.
```

5. If the helper output is JSON with `"status":"ERROR"`, return:

```text
Mira Dripr Reddit follow-up check failed.
```

6. If the helper output is JSON with `"status":"OK"`, use only that compact JSON
   plus the capability prompt for review. Return a short, human-readable summary
   with each row's `why_relevant` and `url`.

## RULES

- Do not query Airtable except through the required helper.
- Do not create tasks, reminders, calendar events, notes, email, drafts, files,
  or memory.
- Do not use web search, browser tools, Gmail, Todoist, calendar, curl, or any
  network request other than the required helper behavior.
- Do not call Telegram or delivery tools. Return final visible text and let the
  scheduler deliver it.

## OUTPUT FORMAT

Return only one of:

- `NO_REPLY`
- A short human-readable Dripr Reddit follow-up summary for Kenny
- `Mira Dripr Reddit follow-up check needs setup before it can run.`
- `Mira Dripr Reddit follow-up check failed.`
