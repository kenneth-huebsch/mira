# rumi

Friend-safe OpenClaw blueprint for recreating Rumi on a fresh host.

This repo is allowed to contain personalized behavior, account conventions, chat IDs, calendar IDs, and cron prompts. It must not contain credentials, provider API keys, OAuth tokens, bot tokens, gateway tokens, device auth, live sessions, or logs.

## Layout

- `workspace/` mirrors the behavior-bearing parts of `~/.openclaw/workspace/`.
  Use `workspace/USER.md` for durable non-tool preferences/context, `workspace/TOOLS.md` for tool mechanics, and `workspace/AGENTS.md` for hard rules and workflow policy.
- `workspace/assets/rumi.jpg` is Rumi's local visual reference.
- `templates/` contains friend-safe examples of runtime config and cron jobs with credential fields redacted.
- `openclaw/` contains host-level OpenClaw files needed to recreate this Docker
  setup, currently `entrypoint.sh`.
- `scripts/sync-from-live.sh` updates the blueprint from the running host.
- `scripts/restore-to-live.sh` copies the blueprint into a new OpenClaw workspace.
- `AGENTS.md`, `CLAUDE.md`, and `GEMINI.md` give coding agents tool-agnostic operating instructions.
- `.cursor/skills/` contains Cursor adapters that point to the same tool-agnostic playbooks.
- `docs/agent-playbooks/` contains the source-of-truth agent workflows for configuring and backing up Rumi.
- `docs/cron-dependencies.md` tracks files that cron prompts or context loaders depend on.
- `docs/engagement-followups.md` explains Rumi's short-lived follow-up behavior
  and how it differs from the broad proactive engagement cron.
- `docs/source-change-audit.md` records whether local OpenClaw source changes matter for restore.

## Memory System

Rumi uses two complementary memory layers:

- Curated memory lives in `workspace/memory/*.jsonl` and is governed by
  `workspace/AGENTS.md`, `workspace/plugins/memory-plugin.ts`, nightly
  reflection, and memory consolidation. These files define what Rumi
  intentionally remembers.
- QMD is enabled in `templates/openclaw.friend-safe.example.json` as a local
  read-only recall/search backend for selected markdown docs, cron prompts, and
  workspace skills. It is intentionally not backfilled from historical JSONL
  memory, and session transcript indexing is off by default.

Do not commit QMD runtime state: `~/.openclaw/agents/*/qmd/`, QMD indexes,
session exports, and accumulated memory history are private runtime data.

## Update The Backup

After changing Rumi behavior on the live host:

```bash
cd ~/rumi
./scripts/sync-from-live.sh
git diff
git status
```

If the diff looks right, commit and push.

## Safety Line

The sync script is allowlist-based. It copies known behavior files and seeds required memory files, but it does not copy accumulated memory history, runtime logs, sessions, device state, credentials, or tokens.
