# Project Companion Capability

Project Companion is Rumi's long-running project support system. It keeps
project context, resumable planning runs, and preview-first external changes
out of the main Telegram turn.

## Files

- `PROJECT_COMPANION.md` - daily lightweight check-in behavior.
- `INTERACTIVE.md` - interactive Project Companion policy injected by the memory plugin.
- `PROJECT_PLANNING_WORKER.md` - isolated worker instructions for larger planning.
- `PROJECT_APPLY_WORKER.md` - isolated worker instructions for confirmed Todoist and Calendar writes.
- `project_companion.py` - deterministic state, queued worker run, proposal, audit, and apply helper.
- `schema.md` - project and planning-run schemas.

## State

- `memory/projects.jsonl` stores active project context and links.
- `memory/project_details.jsonl` stores scoped practical facts for tracked
  projects, such as constraints, links, reservations, contacts, travel details,
  decisions, and open questions.
- `memory/project_runs.jsonl` stores resumable planning artifacts and audit history.

These are private runtime state. The Rumi blueprint should seed the files empty,
not copy accumulated live history.

## Todoist Policy

Do not create Todoist projects in this capability.

All confirmed project tasks go into one of:

- `Personal Tasks`
- `Work Tasks`

Use `task_home: "personal"` or `task_home: "work"` in proposals and store
Todoist task IDs after creation.

Every task created through Project Companion must include the project label from
the helper, e.g. `project:family_trip_to_portugal`. The label is the stable
audit/dedupe handle across Todoist and project state.

## Cron Boundary

`workspace/cron/` remains the scheduler entrypoint folder. Cron files should be
thin wrappers that call capability-owned prompts/helpers.

Project Companion uses two worker boundaries:

- **Project Planning Worker** - proposal-only. It writes planning artifacts and
  never mutates Todoist or Calendar.
- **Project Apply Worker** - confirmation-only. It claims already-confirmed
  apply runs, uses the narrow Todoist/Calendar tool surface, records created IDs
  and per-item failures, and returns one Telegram-ready update.

Cron wrappers should declare capability-owned behavior through frontmatter
instead of duplicating instructions:

```yaml
---
cron_id: project_companion
system_files:
  - capabilities/project_companion/PROJECT_COMPANION.md
dynamic:
  - active_projects
---
```

The workspace memory plugin resolves OpenClaw launcher messages such as
`Run this prompt file: cron/PROJECT_COMPANION.md`, reads the referenced cron
prompt, and injects `system_files` plus dynamic context before the cron run.
Keep cron wrappers focused on scheduler plumbing, helper command order,
`NO_REPLY`, and final output shape.

## Runtime Wiring

Interactive Project Companion behavior depends on the Rumi workspace context
plugin:

- Source: `workspace/plugins/memory-plugin.ts`
- Installed extension: `~/.openclaw/extensions/workspace-medium-memory/`
- Plugin id: `workspace-medium-memory`
- Required OpenClaw config:
  - `plugins.entries.workspace-medium-memory.enabled: true`
  - `plugins.entries.workspace-medium-memory.hooks.allowPromptInjection: true`
  - `plugins.load.paths` includes `~/.openclaw/extensions/workspace-medium-memory`

The plugin must use OpenClaw's typed plugin hook API:

```ts
api.on("before_prompt_build", ...)
api.on("agent_end", ...)
```

Do not use `api.registerHook(...)` for this plugin's prompt injection path; that
registers the older internal hook surface and will not inject `INTERACTIVE.md`
into agent prompt context.

`restore-to-live.sh` installs this extension from `workspace/plugins/memory-plugin.ts`.
Installed extension files should be owned by `root:root`; OpenClaw's plugin trust
check can block config-loaded plugins with suspicious ownership.

## Debugging Checklist

Use these checks when Project Companion behavior does not appear in interactive
Rumi:

```bash
docker exec openclaw-openclaw-gateway-1 openclaw plugins inspect workspace-medium-memory
```

Expected:

- `Status: loaded`
- `Typed hooks:` includes `before_prompt_build` and `agent_end`
- `Policy:` includes `allowPromptInjection: true`

Then verify actual prompt injection with a non-delivered probe:

```bash
docker exec openclaw-openclaw-gateway-1 openclaw agent \
  --session-id plugin-injection-probe \
  --message "Diagnostic probe only: if your current context includes the exact heading Project Companion Interactive Policy, reply exactly HAS_PROJECT_COMPANION_POLICY. If it does not, reply exactly MISSING_PROJECT_COMPANION_POLICY. Do not use tools." \
  --json --timeout 120
```

Expected payload text: `HAS_PROJECT_COMPANION_POLICY`.

If the plugin fails with `EACCES` for `/tmp/jiti/workspace-medium-memory-index...`,
clear the stale root-owned cache file and restart OpenClaw:

```bash
docker exec -u root openclaw-openclaw-gateway-1 sh -lc \
  'rm -f /tmp/jiti/workspace-medium-memory-index.*.cjs && chown -R node:node /tmp/jiti'
docker restart openclaw-openclaw-gateway-1
```

After plugin or config changes, restart OpenClaw and re-run the checks above.
