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

Run the collector helper below. It gathers deterministic facts cheaply and
leaves final wording to you so the brief still feels like Rumi.

```bash
python3 cron/morning_brief_collect.py
```

---

## TASK

1. Use the collector JSON as the source of truth for current time, calendar
   events, calendar failures, current medium-memory context, and active project
   companion context.
2. Query Todoist for tasks from `Kennys Personal Tasks` and `Kennys Work Todo List`.
3. Summarize before reasoning:
   - List key events with time and title only. Highlight anything important or unusual.
   - For tasks, include those due today, high priority (`P1` / `P2`), and important upcoming items.
   - For projects, include only active project context that is useful today; do
     not turn every project into a task unless Todoist also supports it.
   - Apply the calendar failure handling from `TOOLS.md`. Never claim "no events" when retrieval failed.
4. Generate the brief:
   - Key priorities for today.
   - Important events.
   - Urgent tasks.
   - Active project next steps when relevant.
   - Suggested focus.
   - If calendar retrieval failed for either calendar, include one short line noting the access issue.

---

## OUTPUT RULES

- Keep it concise and friendly. Use emojis.
- Do not include raw tool output, IDs, or metadata.
- Do not narrate progress.
