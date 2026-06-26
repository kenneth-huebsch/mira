# Configure Mira

Use this playbook when changing Mira's persona, identity, coding-agent behavior,
workspace skills, memory policy, Gmail access conventions, Telegram control
surface, or restore shape.

## Source Of Truth

Live behavior usually starts in `/home/kenny/mira/.openclaw/workspace/`.

Important files:

- `IDENTITY.md` - Mira's name, role, voice, and operating style.
- `SOUL.md` - Mira's core stance and durable behavior principles.
- `USER.md` - Kenny's coding collaboration preferences and durable non-tool, non-rule context.
- `AGENTS.md` - hard rules, coding workflow, review policy, Gmail handling, Telegram boundaries, and cron policy.
- `TOOLS.md` - tool-specific conventions for coding tools, GitHub, on-demand Gmail, Telegram, and future crons. Do not put user preferences here.
- `HEARTBEAT.md` - heartbeat behavior.
- `cron/*.md` - scheduled behavior, if Kenny explicitly adds any. Mira has no cron prompts by default.
- `skills/` - workspace-local skills.
- `assets/` - local persona assets such as `assets/mira.jpg`.
- `templates/openclaw.friend-safe.example.json` - restore-safe config shape.
- `openclaw/entrypoint.sh` - host-level Docker entrypoint restored into the
  OpenClaw checkout; currently installs/links coding tools, GitHub CLI, Cursor
  CLI, and `gog`.

## Editing Rules

1. Put durable behavior in persona/config docs, not only in memory.
2. Put durable non-tool, non-rule preferences in `USER.md`.
3. Mira has no workspace memory files or QMD enabled by default. If Kenny later asks to add memory back, use explicit tracked policy and keep runtime indexes/history out of the repo.
4. Keep tool mechanics in `TOOLS.md`: command shapes, Gmail account conventions, GitHub notes, Telegram boundaries, and workspace-local skill notes. Do not put user preferences in `TOOLS.md`.
5. Keep hard rules and workflow policy in `AGENTS.md`: safety lines, coding workflow, review policy, Gmail mutation confirmation rules, and cron policy.
6. Mira has no cron jobs by default. If Kenny adds one later, include its prompt/supporting files in `scripts/workspace-manifest.txt`, regenerate derived docs, and verify the schedule through the OpenClaw CLI.
7. When adding a new local asset, helper script, skill, or host-level OpenClaw file, update `scripts/workspace-manifest.txt` or the restore script as appropriate.
8. Keep Mira's persona consistent with `IDENTITY.md` and `SOUL.md`: she should speak as Mira, with continuity and judgment, not as a generic tool.
9. Preserve explicit confirmation rules around external actions such as sending email, pushing code, deploying, or mutating production systems.

## After Changes

After changing live behavior:

```bash
cd /home/kenny/mira
./scripts/sync-from-live.sh
git diff
```

Then follow `docs/agent-playbooks/mira-backup.md` before committing or pushing.
