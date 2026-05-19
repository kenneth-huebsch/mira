# mira

Friend-safe OpenClaw home for running and recreating Mira.

This repo is allowed to contain personalized behavior, account conventions, chat IDs, and calendar IDs. It must not contain credentials, provider API keys, OAuth tokens, bot tokens, gateway tokens, device auth, live sessions, or logs.

## Layout

- `workspace/` mirrors the behavior-bearing parts of `.openclaw/workspace/`.
  Use `workspace/USER.md` for durable non-tool preferences/context, `workspace/TOOLS.md` for tool mechanics, and `workspace/AGENTS.md` for hard rules and workflow policy.
- `.openclaw/` is the ignored live runtime state for this Mira instance.
- `openclaw-src/` is the ignored OpenClaw source checkout for this Mira instance.
- `RUNBOOK.md` documents how to start, stop, and run CLI commands for Mira.
- `templates/` contains friend-safe examples of runtime config with credential fields redacted. Mira has no cron jobs configured by default.
- `openclaw/` contains host-level OpenClaw files needed to recreate this Docker
  setup, currently `entrypoint.sh`.
- `scripts/sync-from-live.sh` updates the blueprint from the running host.
- `scripts/restore-to-live.sh` copies the blueprint into a new OpenClaw workspace.
- `AGENTS.md`, `CLAUDE.md`, and `GEMINI.md` give coding agents tool-agnostic operating instructions.
- `.cursor/skills/` contains Cursor adapters that point to the same tool-agnostic playbooks.
- `docs/agent-playbooks/` contains the source-of-truth agent workflows for configuring and backing up Mira.
- `docs/cron-dependencies.md` records that no recurring cron prompts are configured by default.
- `docs/source-change-audit.md` records whether local OpenClaw source changes matter for restore.

## Memory System

Mira does not use workspace memory files for now. Do not sync or restore
`workspace/memory/*` unless Kenny explicitly asks to add memory back.

QMD is enabled in `templates/openclaw.friend-safe.example.json` as a local
read-only recall/search backend for selected markdown docs and workspace skills.
It is intentionally not backfilled from historical JSONL memory, and session
transcript indexing is off by default.

Do not commit QMD runtime state: `~/.openclaw/agents/*/qmd/`, QMD indexes,
session exports, and accumulated memory history are private runtime data.

## Update The Backup

After changing Mira behavior on the live host:

```bash
cd ~/mira
./scripts/sync-from-live.sh
git diff
git status
```

If the diff looks right, commit and push.

## Safety Line

The sync script is allowlist-based. It copies known behavior files and seeds required memory files, but it does not copy accumulated memory history, runtime logs, sessions, device state, credentials, or tokens.
