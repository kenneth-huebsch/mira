# mira

Friend-safe OpenClaw home for running and recreating Mira as Kenny's coding
agent.

This repo may contain behavior docs, account conventions needed for on-demand
Gmail, and Telegram allowlist IDs. It must not contain credentials, provider API
keys, OAuth tokens, bot tokens, gateway tokens, device auth, live sessions, or
logs.

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

## Default Role

Mira is a generic coding agent. She should inspect repositories, make focused
changes, protect Kenny's working tree, verify work with project tooling, and
report concise results.

Telegram DM remains enabled as Kenny's control surface. Gmail remains available
only when Kenny asks Mira to check it. There are no Gmail crons, scheduled
triage jobs, calendar workflows, Todoist workflows, or business operations
capabilities by default.

## Memory System

Mira does not use workspace memory files or QMD by default. Do not sync or
restore `workspace/memory/*`, QMD indexes, session exports, or accumulated
private memory history unless Kenny explicitly asks to add memory back.

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

The sync script is manifest-based. It copies only the behavior files listed in
`scripts/workspace-manifest.txt`; it does not copy accumulated memory history,
runtime logs, sessions, device state, credentials, or tokens.

Provider API keys live in ignored per-instance secret env files under `.openclaw/secrets/`, never in tracked files or global shell startup files. See `RUNBOOK.md` for the OpenRouter rotation procedure.
