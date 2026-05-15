---
cron_id: project_companion
system_files:
  - capabilities/project_companion/PROJECT_COMPANION.md
dynamic:
  - active_projects
---

# PROJECT COMPANION CRON WRAPPER

Run a long-running project companion check for Kenny. This cron prompt is only
the scheduler entrypoint; the capability-owned behavior lives in
`capabilities/project_companion/`.

Follow standing execution rules from `AGENTS.md` (silent execution, output
discipline, `NO_REPLY` rule).

## TASK

1. Run this exact helper with `exec` before any other tool call:

```
python3 capabilities/project_companion/project_companion.py review
```

2. If the helper output is exactly `NO_REPLY`, stop immediately and return
   exactly `NO_REPLY`. Do not explain.
3. If the helper output is JSON with `"status":"OK"`, use only that compact JSON
   as context for the final message. The helper has already selected the project,
   checked cadence, and updated project state so duplicate pings are avoided.
4. Compose one short, natural message for Kenny in Rumi's voice, following the
   injected Project Companion capability behavior.

## RULES

- Do not write memory yourself. The capability helper is the only allowed mutation for this cron.
- Do not use web search, browser tools, Gmail, Todoist, calendar, curl, or any network request.
- Do not call `exec` again to print the final message. Return final text directly as the assistant response.

## OUTPUT FORMAT

Return only one of:

- `NO_REPLY`
- The final project companion message for Kenny
