# Agent Instructions

This repo is the friend-safe blueprint for Rumi, Kenny's OpenClaw assistant.
It should be usable by any coding agent, not only Cursor.

## Core Rules

- Preserve the safety line: personalized instructions, account conventions, chat IDs, calendar IDs, cron prompts, and Rumi's visual/persona details are allowed; credentials and tokens are not.
- Never commit or copy provider API keys, OAuth tokens, bot tokens, gateway tokens, device auth, sessions, logs, browser state, cron run history, or accumulated private memory history.
- When changing Rumi's live behavior, update the live workspace first when possible, then sync this repo with `scripts/sync-from-live.sh`.
- Do not treat `workspace/memory/*.jsonl` in this repo as real memory. They are restore seed files unless Kenny explicitly says otherwise.
- Treat QMD as a read-only recall backend over selected markdown docs, not as
  Rumi's source of truth. Do not backfill historical JSONL memory into QMD
  unless Kenny explicitly asks. Never copy QMD indexes, session exports, or
  `~/.openclaw/agents/*/qmd/` runtime state into this repo.
- Put durable non-tool, non-rule preferences in `workspace/USER.md`; keep tool mechanics in `workspace/TOOLS.md`; keep hard rules and workflow policy in `workspace/AGENTS.md`.

## When Configuring Rumi

Read `docs/agent-playbooks/configure-rumi.md` before changing Rumi's persona,
identity, cron behavior, workspace skills, plugins, memory policy, or assets.

## When Backing Rumi Up

Read `docs/agent-playbooks/rumi-backup.md` before syncing, committing, pushing,
or restoring this blueprint.

## Tool Adapters

- Cursor users can load `.cursor/skills/configure-rumi/SKILL.md` and `.cursor/skills/rumi-backup/SKILL.md`.
- Claude, Codex, Gemini, and other agents should follow this root `AGENTS.md` and the playbooks in `docs/agent-playbooks/`.
