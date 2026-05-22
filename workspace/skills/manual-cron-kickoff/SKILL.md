---
name: manual-cron-kickoff
description: Manually start an existing OpenClaw cron and acknowledge it safely.
---

# Manual Cron Kickoff

Use this skill when Kenny asks to manually run, kick off, start, trigger, or
re-run an existing cron job.

## Required Flow

1. Identify the intended cron from Kenny's wording.
   - If the target is ambiguous, ask one concise clarifying question and stop.
   - If the target is clear but you need the job id, use the cron list tool.
2. Start the job with the cron run tool.
3. If the tool reports the job was accepted or enqueued, immediately end the
   same turn with visible normal assistant text. Do not call more tools first.
4. Do not wait for the cron result unless Kenny explicitly asked you to wait or
   monitor in the same request. Delivery crons announce their own result.

## Visible Acknowledgement

The acknowledgement must be normal visible assistant text, not hidden thinking
or reasoning. Keep it short and useful:

```text
Started the <cron name> cron. I will send the result when it finishes.
```

If the cron run tool fails, return a visible blocker:

```text
I could not start the <cron name> cron: <short reason>.
```

## Hard Stops

- Never leave a successful manual kickoff turn with only hidden thinking.
- Never expose raw run ids, session ids, tool JSON, or internal metadata unless
  Kenny asks for debugging details.
- Never call Telegram or delivery tools yourself; the scheduler handles cron
  delivery.
