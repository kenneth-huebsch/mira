---
cron_id: morning_brief
dynamic:
  - rolling_summary
  - active_priorities
---

# MORNING BRIEF

You are generating Kenny's morning brief.

Follow standing execution rules from `AGENTS.md` (silent execution, no preamble,
output discipline). Use `gog` and Todoist conventions from `TOOLS.md` directly —
do not restate calendar IDs, account names, or query syntax in this prompt.

---

## INPUT

Read:
- `memory/medium_memory.jsonl`

---

## TASK

1. Get the current time in Eastern (`America/New_York`).
2. Determine today's ET window (`00:00` to `23:59:59`).
3. Query BOTH of Kenny's calendars (Personal + Work — see `TOOLS.md`) for that window. Querying only one calendar is a defect. Tag each event with which calendar it came from when it adds clarity.
4. Query Todoist for tasks from `Kennys Personal Tasks` and `Kennys Work Todo List`.
5. Summarize before reasoning:
   - List key events with time and title only. Highlight anything important or unusual.
   - For tasks, include those due today, high priority (`P1` / `P2`), and important upcoming items.
   - Apply the calendar failure handling from `TOOLS.md`. Never claim "no events" when retrieval failed.
6. Generate the brief:
   - Key priorities for today.
   - Important events.
   - Urgent tasks.
   - Suggested focus.
   - If calendar retrieval failed for either calendar, include one short line noting the access issue.

---

## OUTPUT RULES

- Keep it concise and friendly. Use emojis.
- Do not include raw tool output, IDs, or metadata.
- Do not narrate progress.
