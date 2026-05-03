# Engagement Follow-Ups

Rumi has two engagement systems with different jobs:

- `PROACTIVE_ENGAGEMENT` is for broad, low-frequency check-ins based on memory
  and engagement priorities.
- `ENGAGEMENT_FOLLOWUPS` is for short-lived situations that interactive Rumi
  noticed in the moment and intentionally queued for later.

## Mental Model

Interactive Rumi is the planner. She has the best model, current conversation
context, and social judgment, so she decides whether a later message would feel
human and welcome.

The follow-up cron is the executor. It wakes on a schedule, checks whether any
queued item is due, optionally verifies supported live facts, and either sends a
short Rumi-written message or returns `NO_REPLY`.

## When To Use Follow-Ups

Use an engagement follow-up when Kenny clearly mentions a short-lived situation
where a later message would feel natural:

- "I'm about to go work out" -> later ask how the workout went.
- "Heading into my interview" -> later ask how it went.
- "I'm starting the ribs now" -> later ask how they turned out.
- "Watching the Sixers tonight" -> later check the result if needed.
- "Tell me how the Phillies do" -> later report the final score if available.

Do not enqueue follow-ups for passive trivia, generic small talk, every
Philadelphia game by default, guest-sourced requests, or anything that would
feel creepy if Rumi brought it up later.

## Responsibility Split

`PROACTIVE_ENGAGEMENT`:

- Runs at a few fixed daily slots.
- Does not browse or fetch live data.
- Selects from `memory/engagement_priorities.jsonl` and recent medium memory.
- Is best for relationship/accountability nudges and general "thinking of you"
  messages.
- Appends to `memory/engagement_memory.jsonl` when it sends something.

`ENGAGEMENT_FOLLOWUPS`:

- Runs every 15 minutes from 9am through 11pm Eastern.
- Processes `memory/engagement_followups.jsonl`.
- Sends only when a queued item is due and still valid.
- Can perform supported live checks, currently `sports_result`.
- Appends to `memory/engagement_memory.jsonl` when it sends something so the
  broader engagement system knows Rumi already reached out.

## Queue Shape

Follow-up queue entries use a fixed safety envelope plus a flexible payload.
The fixed fields keep scheduling and delivery reliable; the payload lets
interactive Rumi use judgment for future cases we have not predicted.

Required instruction fields:

- `intent`: what later message should accomplish.
- `source_context`: why Rumi thinks the follow-up is welcome.
- `due_at` or `due_in_minutes`: when the follow-up should become eligible.

Common optional fields:

- `expires_at` or `expires_in_hours`: when to give up.
- `suggested_message_angle`: tone or framing.
- `constraints`: short guardrails.
- `requires_live_check`: whether the executor must verify facts first.
- `live_check_type`: currently only `sports_result`.
- `payload`: open-ended structured context for the executor/model.

All writes must go through:

```bash
python3 cron/engagement_followups.py enqueue --json '<instruction-json>'
```

Do not edit `memory/engagement_followups.jsonl` directly.

## Quick Reminders vs Follow-Ups

Use `quick-reminders` for fixed text at a fixed time, especially when Kenny
explicitly asks to be reminded. It sends without an LLM at fire time.

Use engagement follow-ups when the future message needs Rumi's social judgment,
natural wording, or a live outcome check. The interactive agent writes the plan;
the cron executes it later.
