# Configure Rumi

Use this playbook when changing Rumi's persona, identity, appearance, assistant
behavior, cron behavior, workspace skills, plugins, memory policy, or restore
shape.

## Source Of Truth

Live behavior usually starts in `/home/kenny/.openclaw/workspace/`.

Important files:

- `IDENTITY.md` - Rumi's name, role, appearance, persona, and relational presence.
- `SOUL.md` - Rumi's core stance and durable behavior principles.
- `USER.md` - Kenny context.
- `AGENTS.md` - mode policy, hard rules, memory policy, and email handling.
- `TOOLS.md` - tool-specific conventions, accounts, calendars, Todoist, Telegram, and skills.
- `HEARTBEAT.md` - heartbeat behavior.
- `cron/*.md` - scheduled behavior.
- `plugins/` - workspace plugin code.
- `skills/` - workspace-local skills.
- `assets/` - local persona assets such as `assets/rumi.jpg`.

## Editing Rules

1. Put durable behavior in persona/config docs, not only in memory.
2. Use `memory/*.jsonl` for remembered facts and evolving context, not canonical behavior policy.
3. If a cron prompt references a file, make sure the backup includes that path or a restore seed for it.
4. When adding a new local asset, update both `scripts/sync-from-live.sh` and `scripts/restore-to-live.sh`.
5. Keep Rumi's persona consistent with `IDENTITY.md` and `SOUL.md`: she should speak as Rumi, with continuity and personality, not as a generic tool.
6. Preserve explicit confirmation rules around external actions such as sending email.

## After Changes

After changing live behavior:

```bash
cd /home/kenny/rumi
./scripts/sync-from-live.sh
git diff
```

Then follow `docs/agent-playbooks/rumi-backup.md` before committing or pushing.
