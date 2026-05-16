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
python3 /home/node/.openclaw/workspace/capabilities/project_companion/project_companion.py upsert --json '<project-json>'
```

Keep project state practical: title, phase, next actions, blockers, cadence,
target dates, and tone. Use Todoist and Calendar for actual tasks and events;
project state is the narrative/context layer.

For travel projects with known date ranges, set project-level `starts_at` to the
earliest known trip date and `ends_at` to the latest known trip date. Keep the
detailed lodging, flight, rental, and constraint facts in project details too.

Use a direct helper command exactly like the examples here: `python3
/home/node/.openclaw/workspace/capabilities/project_companion/project_companion.py
<command> ...`. Do not prefix helper calls with `cd`, shell pipelines, `cat`,
`grep`, `find`, temporary wrapper scripts, or Python subprocess wrappers. If exec
preflight rejects a helper call as a complex interpreter invocation, retry once
with the absolute direct command form above.

When creating or updating a project:

1. Upsert the canonical project record.
2. Immediately write any known scoped facts with `detail-upsert` or
   `details-upsert`.
3. Only then reply to Kenny with ordinary visible assistant text. Do not put the
   final user-facing reply in thinking/reasoning content.

## Project Details

Use project details for practical facts that belong to one tracked project but
should not be global medium/long memory: flights, lodging, reservations,
contacts, links, constraints, preferences, decisions, open questions, and other
project-specific notes.

Write details only through the helper:

```bash
python3 /home/node/.openclaw/workspace/capabilities/project_companion/project_companion.py detail-upsert --json '<detail-json>'
python3 /home/node/.openclaw/workspace/capabilities/project_companion/project_companion.py details-upsert --json '<detail-json-array>'
```

The detail JSON must include `project_id` and either `title` or `value`.
Recommended generic fields are `kind`, `title`, `value`, optional `starts_at`,
`ends_at`, `url`, `tags`, and `metadata`. Keep details useful across project
types; do not make travel-only assumptions.

After upserting a project, if current context or memory already contains scoped
facts for that project, write them immediately. Examples include `lodging` like
"Porto Airbnb May 24-30", `lodging` like "Lisbon Airbnb May 30-Jun 2",
`lodging` like "Martinhal resort Jun 2-8", or a `constraint` like
"prescriptions must be filled before departure".

If you mention a project fact in the user-visible reply as something you know,
and that fact belongs to a tracked project, it should already have been written
with `detail-upsert` or `details-upsert` unless it is unsafe to store. Do not
promise to remember or add details in prose. Perform the helper write first,
then confirm naturally.

Do not store secrets, confirmation codes, passport numbers, payment details,
tokens, or private document contents in project details. Store a pointer such as
"hotel confirmation is in Gmail" instead.

Inspect details with:

```bash
python3 /home/node/.openclaw/workspace/capabilities/project_companion/project_companion.py detail-list --id <project_id>
```

Before creating a project, make sure Kenny actually wants ongoing help. If he
explicitly asks to track it, proceed. If he only mentions the situation, offer
lightly or ask at most one or two missing essentials such as target date,
desired cadence, or the first next action.

## Large Project Gate

Lightweight onboarding can create or update project state, capture known details,
and ask one focused question or offer a few planning lanes. A first message like
"help me with my planning for my family trip to Portugal" is lightweight
onboarding unless Kenny explicitly asks for a concrete plan, checklist, research,
or asks Rumi to figure out the work. Do not queue a worker for every project
mention.

The word "planning" alone is not a worker trigger. For first-turn requests like
"help me plan my trip" or "help me with planning for my family trip to
Portugal", do not call `plan`. Create/update the project, capture known details,
then stop and reply with a short question or a few lanes Kenny could choose
from.

Keep the main Telegram turn small. If Kenny asks to "make me a plan", "research
options", "build my checklist", or "figure out what I need", or if the request
needs more than 2-3 tool calls, broad research, task generation, or external
writes:

1. Identify or create the project.
2. Capture any known scoped details.
3. Queue a planning run:

```bash
python3 /home/node/.openclaw/workspace/capabilities/project_companion/project_companion.py plan --id <project_id> --request "<short request>" --task-home <personal|work>
```

4. Stop tool-heavy work in the main session.
5. Tell Kenny briefly that the planning run is queued and Rumi will come back
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
python3 /home/node/.openclaw/workspace/capabilities/project_companion/project_companion.py audit --id <project_id>
python3 /home/node/.openclaw/workspace/capabilities/project_companion/project_companion.py propose --id <project_id>
python3 /home/node/.openclaw/workspace/capabilities/project_companion/project_companion.py propose --run-id <run_id>
```

## Confirmed Apply Flow

Project planning may write project state through the helper, but Todoist and
Calendar writes are preview-first. Do not create Todoist tasks or calendar
events for a project until Kenny has explicitly confirmed the exact proposed
changes in the current turn.

Todoist tasks must go into one of the existing task homes:

- `personal` -> `Personal Tasks`
- `work` -> `Work Tasks`

Do not create new Todoist projects in this workflow.

Treat confirmation narrowly. A reply like "the car is rented already" updates
project state only; it is not approval to create every pending task. Before
applying a proposal, Kenny must clearly confirm all proposed tasks/events or name
the exact subset to apply.

After Kenny confirms exact changes, queue the apply worker with:

```bash
python3 /home/node/.openclaw/workspace/capabilities/project_companion/project_companion.py apply --run-id <run_id> --confirmed-json-stdin <<'JSON'
{"confirmed": true, "tasks": [], "calendar_events": []}
JSON
```

Use `--confirmed-json-stdin` for apply payloads. Do not pass long confirmed
task/event lists as single-quoted shell JSON; apostrophes in names and notes can
break the command. Include every confirmed task when Kenny adds items to a
proposal, and include calendar events only when each event has explicit
`starts_at` and `ends_at`.

The `apply` command only queues a confirmed apply run; it does not perform
external writes. After it returns `"apply_status":"apply_queued"`, stop tool
work in the Telegram turn and tell Kenny briefly that the confirmed changes are
queued. The Project Apply Worker owns the Todoist MCP and `gog` calendar writes,
records task/event ids, and reports back.

After queuing a confirmed apply, do not continue into optional project
bookkeeping, Todoist creation, calendar creation, or audit calls in the same
Telegram turn. Do the confirmed queue step, verify the helper accepted it, then
reply.
