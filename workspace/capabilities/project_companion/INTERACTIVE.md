---
capability_id: project_companion_interactive
---

# Project Companion Interactive Policy

Use this capability when Kenny wants ongoing help with a real multi-step effort
over days or weeks: vacation prep, launches, moves, medical or appointment prep,
home projects, job searches, and other work with phases, blockers, or next
actions.

Do not create project records for jokes, passive trivia, one-off reminders,
guest-sourced requests, or vague topics with no actionable follow-through.

## Project State

Create or update project state only through the helper:

```bash
python3 capabilities/project_companion/project_companion.py upsert --json '<project-json>'
```

Keep project state practical: title, phase, next actions, blockers, cadence,
target dates, and tone. Use Todoist and Calendar for actual tasks and events;
project state is the narrative/context layer.

## Project Details

Use project details for practical facts that belong to one tracked project but
should not be global medium/long memory: flights, lodging, reservations,
contacts, links, constraints, preferences, decisions, open questions, and other
project-specific notes.

Write details only through the helper:

```bash
python3 capabilities/project_companion/project_companion.py detail-upsert --json '<detail-json>'
```

The detail JSON must include `project_id` and either `title` or `value`.
Recommended generic fields are `kind`, `title`, `value`, optional `starts_at`,
`ends_at`, `url`, `tags`, and `metadata`. Keep details useful across project
types; do not make travel-only assumptions.

Do not store secrets, confirmation codes, passport numbers, payment details,
tokens, or private document contents in project details. Store a pointer such as
"hotel confirmation is in Gmail" instead.

Inspect details with:

```bash
python3 capabilities/project_companion/project_companion.py detail-list --id <project_id>
```

Before creating a project, make sure Kenny actually wants ongoing help. If he
explicitly asks to track it, proceed. If he only mentions the situation, offer
lightly or ask at most one or two missing essentials such as target date,
desired cadence, or the first next action.

## Large Project Gate

Keep the main Telegram turn small. If the request needs more than 2-3 tool
calls, broad research, or external writes:

1. Identify or create the project.
2. Queue a planning run:

```bash
python3 capabilities/project_companion/project_companion.py plan --id <project_id> --request "<short request>" --task-home <personal|work>
```

3. Stop tool-heavy work in the main session.
4. Tell Kenny briefly that the planning run is queued and Rumi will come back
   with a proposal.

Do not keep adding tools in Telegram just because progress is possible.

## Pending Worker Output

The Project Planning Worker runs in an isolated cron session. Its Telegram
announcement is only a notification; the durable source of truth is
`memory/project_runs.jsonl`, surfaced in interactive context as pending project
planning runs.

When Kenny replies to a worker announcement, first inspect pending run context.
Short replies such as "AA123" or "yes, do the house-sitter task" may be answers
to the latest pending project run. If multiple pending runs could match, ask a
brief disambiguating question before applying or updating anything.

Useful commands:

```bash
python3 capabilities/project_companion/project_companion.py audit --id <project_id>
python3 capabilities/project_companion/project_companion.py propose --id <project_id>
python3 capabilities/project_companion/project_companion.py propose --run-id <run_id>
```

## External Changes

Project planning may write project state through the helper, but Todoist and
Calendar writes are preview-first. Do not create Todoist tasks or calendar
events for a project until Kenny has explicitly confirmed the exact proposed
changes in the current turn.

Todoist tasks must go into one of the existing task homes:

- `personal` -> `Kennys Personal Tasks`
- `work` -> `Kennys Work Todo List`

Do not create new Todoist projects in this workflow.

After Kenny confirms exact changes, use the helper to apply or record the
confirmed subset:

```bash
python3 capabilities/project_companion/project_companion.py apply --run-id <run_id> --confirmed-json '<confirmation-json>'
```

Todoist is MCP-only in this workspace. If the helper returns Todoist apply
instructions, execute those with Todoist MCP after confirmation and record
per-item failures so retries do not duplicate successful work.
