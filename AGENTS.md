# Agent Instructions

This repo is the friend-safe blueprint for Mira, Kenny's OpenClaw assistant.
It should be usable by any coding agent, not only Cursor.

## Core Rules

- Preserve the safety line: personalized instructions, account conventions, chat IDs, calendar IDs, and Mira's visual/persona details are allowed; credentials and tokens are not.
- Never commit or copy provider API keys, OAuth tokens, bot tokens, gateway tokens, device auth, sessions, logs, browser state, cron run history, or accumulated private memory history.
- When changing Mira's live behavior, update the live workspace first when possible, then sync this repo with `scripts/sync-from-live.sh`.
- Do not treat `workspace/memory/*.jsonl` in this repo as real memory. They are restore seed files unless Kenny explicitly says otherwise.
- Treat QMD as a read-only recall backend over selected markdown docs, not as
  Mira's source of truth. Do not backfill historical JSONL memory into QMD
  unless Kenny explicitly asks. Never copy QMD indexes, session exports, or
  `~/.openclaw/agents/*/qmd/` runtime state into this repo.
- Put durable non-tool, non-rule preferences in `workspace/USER.md`; keep tool mechanics in `workspace/TOOLS.md`; keep hard rules and workflow policy in `workspace/AGENTS.md`.

## When Configuring Mira

Read `docs/agent-playbooks/configure-mira.md` before changing Mira's persona,
identity, workspace skills, plugins, memory policy, assets, or future scheduled behavior.

## When Backing Mira Up

Read `docs/agent-playbooks/mira-backup.md` before syncing, committing, pushing,
or restoring this blueprint.

## Tool Adapters

- Cursor users can load `.cursor/skills/configure-mira/SKILL.md` and `.cursor/skills/mira-backup/SKILL.md`.
- Claude, Codex, Gemini, and other agents should follow this root `AGENTS.md` and the playbooks in `docs/agent-playbooks/`.
