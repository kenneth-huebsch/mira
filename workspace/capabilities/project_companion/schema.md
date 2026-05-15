# Project Companion Schema

## `memory/projects.jsonl`

One JSON object per project. Project state is the narrative/control layer, not a
replacement for Todoist or Calendar.

Required core fields:

```json
{
  "id": "project_id",
  "title": "Human title",
  "status": "active",
  "category": "general",
  "starts_at": "YYYY-MM-DD",
  "ends_at": "YYYY-MM-DD",
  "cadence": "daily_or_when_useful",
  "current_phase": "planning",
  "next_actions": [],
  "blockers": [],
  "last_discussed_at": "YYYY-MM-DD",
  "last_nudged_at": null,
  "next_checkin_after": "YYYY-MM-DD",
  "tone": "helpful, light, not naggy",
  "created_at": "YYYY-MM-DD",
  "updated_at": "YYYY-MM-DD"
}
```

Optional coordination fields:

- `latest_run_id`
- `artifact_summary`
- `todoist_task_ids`
- `calendar_event_ids`
- `pending_confirmation`
- `last_audit_at`

## `memory/project_details.jsonl`

One JSON object per project-scoped detail. Details are the practical memory
layer for any tracked project, not just travel: flights, lodging, launch links,
contacts, constraints, preferences, decisions, reservations, open questions, and
other facts that should stay attached to one project.

```json
{
  "detail_id": "project_id_kind_short_name",
  "project_id": "project_id",
  "kind": "note",
  "title": "Human label",
  "value": "The remembered project fact",
  "starts_at": "optional ISO-ish time or date",
  "ends_at": "optional ISO-ish time or date",
  "source": "kenny",
  "url": "",
  "tags": [],
  "status": "active",
  "metadata": {},
  "created_at": "YYYY-MM-DD",
  "updated_at": "YYYY-MM-DD"
}
```

Detail statuses:

- `active` - available in project context and worker input.
- `archived` - retained for audit, omitted from active context.

Suggested `kind` values are generic and extensible: `flight`, `lodging`,
`reservation`, `calendar_anchor`, `constraint`, `preference`, `contact`, `link`,
`decision`, `note`, and `open_question`. New kinds are allowed when they are
clear, short, and reusable across projects.

Do not store secrets, confirmation codes, passport numbers, payment details,
tokens, or private document contents. Store pointers such as "confirmation is in
Gmail" instead.

## `memory/project_runs.jsonl`

One JSON object per planning run. Runs make long work resumable and auditable.

```json
{
  "run_id": "project_YYYYMMDD_abcd1234",
  "project_id": "project_id",
  "status": "queued",
  "requested_at": "ISO timestamp",
  "claimed_at": "ISO timestamp",
  "completed_at": "ISO timestamp",
  "request": "What Kenny asked for",
  "task_home": "personal",
  "summary": "Compact result",
  "proposed_tasks": [],
  "proposed_calendar_events": [],
  "questions": [],
  "errors": [],
  "applied_changes": [],
  "attempt_count": 0,
  "updated_at": "ISO timestamp"
}
```

Run statuses:

- `queued` - interactive Rumi has handed off work to the worker.
- `in_progress` - the worker has claimed the run.
- `pending_confirmation` - a proposal is ready for Kenny to confirm.
- `needs_input` - the worker needs an answer from Kenny before proposing or applying changes.
- `failed` - the worker hit a useful failure that should be visible/retryable.
- `completed` - the worker finished with no external proposal or open question.
- `applied` / `applied_with_errors` - confirmed changes were applied or recorded.
- `canceled` - the run should no longer be processed.

## Todoist Task Proposal

Todoist tasks must use an existing task home. Do not create Todoist projects.

```json
{
  "content": "Book rental car",
  "description": "",
  "due": "May 18",
  "priority": "",
  "task_home": "personal",
  "todoist_project": "Kennys Personal Tasks",
  "labels": ["project:project_id"],
  "external_id": "",
  "status": "proposed"
}
```

Allowed `task_home` values:

- `personal` -> `Kennys Personal Tasks`
- `work` -> `Kennys Work Todo List`

## Calendar Event Proposal

```json
{
  "title": "Porto Airbnb",
  "calendar": "kenneth.huebsch@gmail.com",
  "starts_at": "2026-05-24",
  "ends_at": "2026-05-30",
  "all_day": true,
  "external_id": "",
  "status": "proposed"
}
```
