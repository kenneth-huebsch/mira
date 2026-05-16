---
capability_id: project_apply_worker
---

# Project Apply Worker

Use this worker only for confirmed Project Companion changes. The planning
worker proposes; interactive Rumi confirms with Kenny in Telegram; this worker
applies exactly that confirmed subset and records the result.

## Workflow

1. Claim exactly one confirmed apply run with:

```bash
python3 /home/node/.openclaw/workspace/capabilities/project_companion/project_companion.py next-apply-run
```

If the helper prints exactly `NO_REPLY`, return exactly `NO_REPLY`.

2. If the helper returns JSON with `"status":"OK"`, use only that compact JSON
   as the apply input. It contains `todoist_tasks`, `calendar_events`, and
   `rules`.

Do not add tasks or events that are not in the confirmed payload. Do not browse,
research, rewrite the plan, or infer extra work.

3. Apply Todoist tasks with Todoist MCP:

- Use the existing task home from each task.
- Resolve task homes through the helper-provided `todoist_task_homes`.
- Do not create Todoist projects.
- Include every task's labels. Every Project Companion task must carry the
  helper-provided `project_label`, e.g. `project:family_trip_to_portugal`.
- Preserve due dates and priorities from the task payload.
- If this is a retry (`attempt_count` greater than 1), search Todoist for an
  existing matching task with the same project label and content before creating
  a new task. Record the existing task id instead of duplicating it.
- Record each created task's id. If one task fails, continue with the remaining
  tasks and record the failure.

4. Apply calendar events with `gog` via direct `exec` commands only:

```bash
gog calendar create <calendar-id> --summary "<title>" --from "<starts_at>" --to "<ends_at>" --account rumi.openclaw@gmail.com --json
```

Add `--all-day` only when the event payload has `all_day: true`.

Do not create a calendar event if it lacks either `starts_at` or `ends_at`.
Record a per-event failure instead.

5. Save results with:

```bash
python3 /home/node/.openclaw/workspace/capabilities/project_companion/project_companion.py complete-apply-run --run-id <run_id> --json-stdin <<'JSON'
{
  "todoist_tasks": [],
  "calendar_events": [],
  "errors": []
}
JSON
```

Result item shapes:

```json
{
  "todoist_tasks": [
    {"content": "Task title", "external_id": "todoist_task_id", "status": "created", "error": ""}
  ],
  "calendar_events": [
    {"title": "Event title", "calendar": "calendar_id", "external_id": "calendar_event_id", "status": "created", "error": ""}
  ],
  "errors": []
}
```

Use `status: "failed"` and an `error` string for failed items.

6. Return one concise Telegram-ready update for Kenny. Mention what was created
and any failures in normal language. Do not include raw JSON, run ids, command
names, file paths, or internal process unless Kenny asks.

## Safety Rules

- This worker runs only after Kenny has confirmed exact changes in Telegram.
- Apply only the confirmed payload from `next-apply-run`.
- Never send email, delete tasks, delete calendar events, or modify unrelated
  Todoist/Calendar objects.
- If you are unsure whether a task/event is confirmed, do not apply it; record a
  failure and say what needs clarification.
