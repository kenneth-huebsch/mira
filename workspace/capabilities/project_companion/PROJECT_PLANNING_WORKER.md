---
capability_id: project_planning_worker
---

# Project Planning Worker

Use this worker for large, tool-heavy project planning. It should run in an
isolated context, produce a compact planning artifact, and avoid making
external changes until Kenny confirms the proposal.

## Workflow

1. Claim exactly one queued planning run with:

```bash
python3 capabilities/project_companion/project_companion.py next-worker-run
```

If the helper prints exactly `NO_REPLY`, return exactly `NO_REPLY`.

2. If the helper returns JSON with `"status":"OK"`, use only that compact JSON
   as the worker input. It contains the project, any active project details,
   the run, and the rules.

3. Produce a practical planning artifact:

- A short summary.
- Proposed Todoist tasks.
- Proposed calendar events.
- Questions or missing information.
- Any errors that should be visible to Kenny.

Use `project_details` as remembered project facts. They are generic scoped
memory, not travel-only state, so apply them to launches, home projects, medical
prep, moves, job searches, and any other tracked project. Do not invent missing
details; ask questions instead.

4. Save the artifact with:

```bash
python3 capabilities/project_companion/project_companion.py complete-run --run-id <run_id> --json '<worker-result-json>'
```

The JSON must be an object with any of:

```json
{
  "summary": "Compact result for Kenny",
  "task_home": "personal",
  "proposed_tasks": [],
  "proposed_calendar_events": [],
  "questions": [],
  "errors": []
}
```

5. Return one concise Rumi message for Kenny. The message should say what is
   ready or what information is needed. Do not include raw JSON, run ids, file
   paths, command names, or internal process unless Kenny asks.

If saving fails, run:

```bash
python3 capabilities/project_companion/project_companion.py fail-run --run-id <run_id> --error "<short error>"
```

Then return a short failure note for Kenny.

## Todoist Rules

Do not create Todoist projects in this workflow.

All proposed tasks must target one of:

- `personal` -> `Kennys Personal Tasks`
- `work` -> `Kennys Work Todo List`

The project helper validates `task_home`; use that field instead of arbitrary
Todoist project names.

## External Write Rules

- Project state writes are allowed through the helper.
- Project detail writes are allowed through the helper when the worker learns or
  normalizes a useful scoped fact, but do not store secrets, confirmation codes,
  passport numbers, payment details, tokens, or private document contents.
- Calendar and Todoist writes are preview-first.
- Calendar events may only be created after a confirmed apply call.
- Todoist is MCP-only in this workspace. The helper returns validated Todoist
  apply instructions; Rumi should execute them with Todoist MCP only after
  Kenny confirms the exact proposed task list.
- Record per-item failures so retries do not duplicate successful work.

## Message Rules

- Return `NO_REPLY` only when no queued run exists.
- If a proposal, question, or useful failure was written, return a short
  Telegram-ready update.
- If questions exist, tell Kenny what kind of reply would unblock the run.
- Do not mention prompts, files, tools, cron, JSON, or internal state.
