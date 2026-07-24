# Configure Mira

Use this playbook when changing Mira's persona, identity, harness routing
behavior, workspace skills, memory policy, Gmail access conventions, Telegram
control surface, or restore shape.

## Source Of Truth

Live behavior usually starts in `/home/kenny/mira/.openclaw/workspace/`.

Important files:

- `IDENTITY.md` - Mira's name, role, voice, and operating style.
- `SOUL.md` - Mira's core stance and durable behavior principles.
- `USER.md` - Kenny's interaction preferences and durable non-tool, non-rule context.
- `AGENTS.md` - hard rules, coding-harness routing, Gmail handling, Telegram boundaries, and cron policy.
- `TOOLS.md` - tool-specific conventions for harness routing, GitHub, memory,
  on-demand Gmail, Telegram, and future crons. Do not put user preferences here.
- `HEARTBEAT.md` - heartbeat behavior.
- `SESSION-STATE.md`, `MEMORY.md`, `memory/YYYY-MM-DD.md`, and `DREAMS.md` -
  live runtime memory files. Track policy and empty templates, not accumulated
  memory contents.
- `cron/*.md` - scheduled behavior, if Kenny explicitly adds any. Mira has no cron prompts by default.
- `skills/` - workspace-local skills and their helper scripts. Current
  memory-related skills are `mira-memory` for policy and health checks and
  `memory-cold-store` for ignored git-notes storage. `wordpress-page-updater`
  provides the manual, approval-gated helper for existing WordPress pages;
  `addicks-barker-case-updates` stages PDF-derived updates for its fixed page.
- `templates/openclaw.friend-safe.example.json` - restore-safe config shape.
- `templates/memory-scaffold/` - empty restore-only memory file templates used
  when live memory files are missing.
- `openclaw/docker-compose.yml` - Mira's source-local Docker Compose overrides
  for the OpenClaw gateway and CLI runtime.
- `openclaw/entrypoint.sh` - Mira's source-local runtime tool setup.

Mira's own infrastructure:

- Blueprint repo: `/home/kenny/mira`
- Live OpenClaw state: `/home/kenny/mira/.openclaw`
- Live workspace: `/home/kenny/mira/.openclaw/workspace`
- OpenClaw source checkout: `/home/kenny/mira/openclaw-src`
- Gateway container: `openclaw-mira-openclaw-gateway-1`

## Editing Rules

1. Put durable behavior in persona/config docs, not only in memory.
2. Put durable non-tool, non-rule preferences in `USER.md`.
3. Mira uses local-first workspace memory plus OpenClaw memory search,
   `active-memory`, LanceDB, and git-notes cold storage. Keep memory policy in
   `AGENTS.md` and memory mechanics in `TOOLS.md`; keep runtime memory files,
   indexes, git-notes stores, service keys, and session history out of the repo.
   `memorySearch` and LanceDB embeddings use `OPENROUTER_API_KEY` loaded from
   ignored `openrouter.env`. Mira does not use third-party cloud memory by
   default.
4. Keep tool mechanics in `TOOLS.md`: command shapes, Gmail account conventions, GitHub notes, Telegram boundaries, harness helper paths, and workspace-local skill notes. Do not put user preferences in `TOOLS.md`.
5. Keep hard rules and workflow policy in `AGENTS.md`: safety lines, coding-harness routing, Gmail mutation confirmation rules, and cron policy.
6. Mira has no cron jobs by default. If Kenny adds one later, include its prompt/supporting files in `scripts/workspace-manifest.txt`, regenerate derived docs, and verify the schedule through the OpenClaw CLI.
7. When adding a new helper script, skill, or host-level OpenClaw file, update `scripts/workspace-manifest.txt` or the restore script as appropriate.
8. Keep Mira's persona consistent with `IDENTITY.md` and `SOUL.md`: she should speak as Mira, with continuity and judgment, not as a generic tool.
9. Preserve explicit confirmation rules around external actions such as sending email, pushing code, deploying, or mutating production systems.
10. Harness locks use only a reviewed full lowercase 40-character SHA and a
    matching numeric contract version. Keep adapter denied roots in the tracked
    policy aligned with its allowed runtime roots. The adapter emits a runner-only projection
    because the runner correctly rejects adapter-specific unknown fields.
11. Keep the OpenClaw outer timeout at 3600 seconds while the runner default is
    3000 seconds plus cancellation grace. The adapter must explicitly forward
    the policy default when `run` or `run-plan` omits `--timeout`.
12. Sync and restore transactions must retain durable fsync-backed
    intent/applied journals and reconcile incomplete transactions before new
    work. Do not weaken canonical-root, non-symlink, duplicate-manifest, or
    beneath-root validation.

## Memory Restore Notes

Live memory files are restore-only scaffolds, not manifest-synced behavior.
`scripts/restore-to-live.sh` creates missing `SESSION-STATE.md`, `MEMORY.md`,
`DREAMS.md`, and `memory/YYYY-MM-DD.md` from `templates/memory-scaffold/` but
does not overwrite accumulated runtime memory.

For debugging memory behavior, verify `active-memory` and `memory-lancedb` with
`openclaw plugins list`, `python3 skills/mira-memory/mira_memory_check.py`, and
a fresh Mira DM before assuming a host-side wrapper reflects the in-agent command
surface.

## After Changes

After changing live behavior:

```bash
cd /home/kenny/mira
./scripts/sync-from-live.sh
git diff
```

Then follow `docs/agent-playbooks/mira-backup.md` before committing or pushing.
