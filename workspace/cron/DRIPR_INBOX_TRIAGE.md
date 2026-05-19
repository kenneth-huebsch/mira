---
cron_id: dripr_inbox_triage
system_files:
  - capabilities/dripr_inbox_triage/DRIPR_INBOX_TRIAGE.md
---

# DRIPR INBOX TRIAGE CRON WRAPPER

Run Mira's dripr inbox triage for Kenny. This cron prompt is only the scheduler
entrypoint; the capability-owned behavior lives in
`capabilities/dripr_inbox_triage/`.

Follow standing execution rules from `AGENTS.md` and tool conventions from
`TOOLS.md`.

## TASK

1. Run this exact helper with `exec`:

```
python3 capabilities/dripr_inbox_triage/dripr_inbox_triage.py process
```

2. If the helper output is exactly `NO_REPLY`, stop immediately and return
   exactly `NO_REPLY`. Do not explain.
3. If the helper exits non-zero, return:

```
Mira dripr inbox triage failed: Gmail unavailable.
```

4. Otherwise, return only the helper's stdout as final visible text. Do not add,
   rewrite, summarize, or explain it.

## RULES

- Do not send mail. Do not create drafts.
- Do not create tasks, reminders, calendar events, or notes.
- The only Gmail mutation allowed is removing `UNREAD` from matching messages
  after review.
- Do not write files or memory.
- Do not use web search, browser tools, Todoist, calendar, curl, or any network
  request other than the required Gmail operations.
- Do not call Gmail commands directly; the helper owns Gmail search, summary,
  and mark-read plumbing.
- Do not call Telegram or delivery tools. Return final visible text and let the
  scheduler deliver it.

## OUTPUT FORMAT

Return only one of:

- `NO_REPLY`
- The final dripr inbox summary for Kenny
- `Mira dripr inbox triage failed: Gmail unavailable.`
