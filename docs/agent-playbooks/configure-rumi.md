# Configure Rumi

Use this playbook when changing Rumi's persona, identity, appearance, assistant
behavior, cron behavior, workspace skills, plugins, memory policy, or restore
shape.

## Source Of Truth

Live behavior usually starts in `/home/kenny/.openclaw/workspace/`.

Important files:

- `IDENTITY.md` - Rumi's name, role, appearance, persona, and relational presence.
- `SOUL.md` - Rumi's core stance and durable behavior principles.
- `USER.md` - Kenny context and durable non-tool, non-rule preferences such as people, relationships, preferred names/titles, communication preferences, and stable personal/project context.
- `AGENTS.md` - mode policy, hard rules, memory policy, email handling, and where shared behavior should be recorded.
- `TOOLS.md` - tool-specific conventions, accounts, calendars, Todoist, Telegram, and skills. Do not put user/person/project preferences here.
- `HEARTBEAT.md` - heartbeat behavior.
- `cron/*.md` - scheduled behavior.
- `plugins/` - workspace plugin code.
- `skills/` - workspace-local skills.
- `assets/` - local persona assets such as `assets/rumi.jpg`.
- `templates/openclaw.friend-safe.example.json` - restore-safe config shape.
  Keep `skills.entries.agent-browser.enabled` true so Interactive loads the
  CLI browser workflow instead of falling back to generic web fetches.
- `openclaw/entrypoint.sh` - host-level Docker entrypoint restored into the
  OpenClaw checkout; currently installs/links `gog`, QMD, and `agent-browser`.

## Editing Rules

1. Put durable behavior in persona/config docs, not only in memory.
2. Put durable non-tool, non-rule preferences in `USER.md`. Examples: family/contact details, preferred names/titles, communication preferences, stable relationship context, and stable project context that should be available to both interactive Rumi and relevant crons.
3. Use `memory/*.jsonl` for remembered facts and evolving context, not canonical behavior policy or stable preferences. If a memory entry contradicts a durable preference moved into `USER.md`, remove or expire the memory entry in the live workspace.
4. Keep tool mechanics in `TOOLS.md`: account names, command shapes, calendar IDs, Gmail queries, Todoist conventions, Telegram IDs, tool-specific gotchas, and workspace-local skill notes. Do not put user/person/project preferences in `TOOLS.md`.
5. Keep hard rules and workflow policy in `AGENTS.md`: safety lines, mode policy, memory write policy, email confirmation rules, and instructions telling Rumi where durable shared preferences belong.
6. Keep nightly reflection and memory consolidation responsibilities separate:
   `cron/NIGHTLY_SESSION_REFLECTION.md` extracts tomorrow-useful interactive context and durable facts Kenny explicitly revealed; `cron/MEMORY_CONSOLIDATION.md` performs hygiene only.
7. Treat QMD as read-only recall over selected markdown docs, not as the
   curated memory source. Do not backfill historical JSONL memory or enable
   session transcript indexing unless Kenny explicitly asks.
8. When changing QMD behavior, update `templates/openclaw.friend-safe.example.json`,
   `workspace/TOOLS.md`, and restore docs as needed. Never add QMD indexes,
   session exports, or `~/.openclaw/agents/*/qmd/` runtime state to the backup.
9. If a cron prompt references a file, make sure the backup includes that path or a restore seed for it.
10. If a cron must use shared preferences from `USER.md`, verify whether its cron payload uses `lightContext: true`. Light-context cron runs intentionally strip default bootstrap files; either remove `lightContext` for that job or make the job explicitly read/load `USER.md`.
11. When adding a new local asset, helper script, or host-level OpenClaw file,
    update both `scripts/sync-from-live.sh` and `scripts/restore-to-live.sh`.
12. Keep Rumi's persona consistent with `IDENTITY.md` and `SOUL.md`: she should speak as Rumi, with continuity and personality, not as a generic tool.
13. Preserve explicit confirmation rules around external actions such as sending email.
14. For crons, keep deterministic plumbing in helpers and human-visible language
    with Rumi. Helper scripts should fetch data, parse JSON, route sources,
    enforce eligibility, dedupe, write files safely, construct compact context,
    and handle obvious `NO_REPLY` exits. The model should handle judgment,
    prioritization, warmth, and varied final prose for human-facing crons.
15. For cron creation and edits, follow `workspace/TOOLS.md`'s OpenClaw cron
    rules. In particular, never use `default` as a cron payload model; use a
    fully qualified model id such as `openrouter/xiaomi/mimo-v2-flash`.

## After Changes

After changing live behavior:

```bash
cd /home/kenny/rumi
./scripts/sync-from-live.sh
git diff
```

Then follow `docs/agent-playbooks/rumi-backup.md` before committing or pushing.
