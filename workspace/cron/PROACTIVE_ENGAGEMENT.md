---
cron_id: proactive_engagement
dynamic:
  - proactive_engagement_priorities
  - proactive_engagement_history
  - proactive_medium_memory
---

# PROACTIVE ENGAGEMENT

Run a proactive engagement check for Kenny.

Follow standing execution rules from `AGENTS.md` (silent execution, output discipline).

## INPUT

Read:
- `memory/engagement_memory.jsonl`
- `memory/engagement_priorities.jsonl`
- `memory/medium_memory.jsonl`

## TASK

1. Parse each JSONL line in `memory/engagement_memory.jsonl` as one prior engagement record.
2. Parse each JSONL line in `memory/engagement_priorities.jsonl` as one engagement priority record with fields:
   - `topic`
   - `kind`
   - `prompt`
   - `created_at`
   - `expires_at`
3. Ignore engagement-priority records whose `expires_at` is before today.
4. Parse each JSONL line in `memory/medium_memory.jsonl` as one memory record.
5. If `engagement_priorities.jsonl` is empty, continue using `medium_memory.jsonl` only.
6. Get the current time in Eastern time (`America/New_York`).
7. Only allow outreach during active hours: 9:00am-10:00pm ET.
8. Enforce daily cap: maximum 2 engagements per calendar day in ET.
9. Keep outreach time varied day-to-day:
   - Use spread-out check slots: 10, 12, 15, 17, 21.
   - Prefer slots not used yesterday when choosing whether to engage now.
   - If today already has one engagement, avoid the same slot for the second engagement.
   - If today already has one engagement, only allow a second one if at least 4 hours have passed since the first.
10. Choose one topic from these sources with priority:
   - `engagement_priorities.jsonl`
   - `medium_memory.jsonl`
11. Extract normalized topics:
   - From `engagement_priorities.jsonl`, use `topic` as topic id, `kind` as topic family, and `prompt` as the guidance for what to engage about.
   - From `medium_memory.jsonl`, use concise stable topic text from `summary`.
12. Apply selection policy:
   - Avoid repeating the same `topic` in the last 3 engagements.
   - If there was already one engagement today, prefer a different `topic_family` for the second one.
   - Prefer the least recently used topic family (`accountability`, `relationship`, `general`, `medium_memory`) from recent history.
13. Rotate message style:
   - Use one style per engagement: `question`, `encouragement`, or `playful`.
   - Avoid using the same `style` in consecutive engagements when alternatives exist.
14. Compose one short, human message for Kenny that sounds warm and natural.
15. Use the selected engagement-priority `prompt` as guidance, not as a script to copy verbatim.
16. If no engagement should be sent now, return exactly `NO_REPLY`.
17. If an engagement is sent, append one JSON object to `memory/engagement_memory.jsonl` with this schema:
   - `at` (ISO timestamp, ET-aware)
   - `date_et` (`YYYY-MM-DD`)
   - `slot_et` (`10|12|15|17|21`)
   - `topic_family` (`accountability|relationship|general|medium_memory`)
   - `topic`
   - `style` (`question|encouragement|playful`)
18. Append the new record before returning the final message. If the append fails, return `NO_REPLY`.

## APPENDING THE RECORD

Do NOT use the `edit` tool to append to `memory/engagement_memory.jsonl`. Use the `exec` tool with a single shell append, like:

```
printf '%s\n' '<one-line JSON object>' >> /home/node/.openclaw/workspace/memory/engagement_memory.jsonl
```

Requirements for the append:
- The JSON object must be on a single line (no embedded newlines).
- Single-quote the JSON argument to `printf` so inner double-quotes are preserved.
- Use `>>` (append), never `>` (overwrite).
- Use the absolute path `/home/node/.openclaw/workspace/memory/engagement_memory.jsonl`.

If you do choose to use the `edit` tool instead, you MUST pass an `edits` array, e.g. `{ "path": "...", "edits": [{ "oldText": "...", "newText": "..." }] }`. Top-level `oldText`/`newText` is not a valid schema and will fail.

## RULES

- Keep `memory/engagement_memory.jsonl` valid JSONL (one JSON object per line).
- Do not output progress narration, tool chatter, or internal reasoning.
- Do not mention prompts, files, cron, or system internals.
- Keep message concise and human.
- No guilt, pressure, or repetitive checklist tone.

## OUTPUT FORMAT

Return only one of:
- `NO_REPLY`
- The final engagement message for Kenny
