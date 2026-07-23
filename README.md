# mira

Friend-safe OpenClaw home for running and recreating Mira as Kenny's
coding-harness router.

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
- `templates/` contains friend-safe examples of runtime config with credential
  fields redacted and empty memory scaffold files under
  `templates/memory-scaffold/`. Mira has no cron jobs configured by default.
- `openclaw/` contains the hardened derived-image Dockerfile, pinned toolchain
  metadata, validation-only entrypoint, and Compose definition.
- `scripts/sync-from-live.sh` updates the blueprint from the running host.
- `scripts/restore-to-live.sh` copies the blueprint into a new OpenClaw workspace.
- `AGENTS.md`, `CLAUDE.md`, and `GEMINI.md` give coding agents tool-agnostic operating instructions.
- `.cursor/skills/` contains Cursor adapters that point to the same tool-agnostic playbooks.
- `docs/agent-playbooks/` contains the source-of-truth agent workflows for configuring and backing up Mira.
- `docs/cron-dependencies.md` records that no recurring cron prompts are configured by default.
- `docs/source-change-audit.md` records whether local OpenClaw source changes matter for restore.

## Default Role

Mira routes non-Mira coding requests through Kenny's private agent harness at
`https://github.com/kenneth-huebsch/agent`. Her core files should not carry
generic implementation policy; the harness is the source of truth for coding
behavior.

Telegram DM remains enabled as Kenny's control surface. Gmail remains available
only when Kenny asks Mira to check it. There are no Gmail crons, scheduled
triage jobs, calendar workflows, Todoist workflows, or business operations
capabilities by default.

## Harness Runtime

For coding requests in other repos, Mira materializes the reviewed immutable
harness revision into ignored runtime and runs Cursor CLI against the target:

- Harness repo: `https://github.com/kenneth-huebsch/agent`
- Host runtime checkout: `/home/kenny/mira/.openclaw/workspace/runtime/repos/agent`
- Container runtime checkout: `/home/node/.openclaw/workspace/runtime/repos/agent`
- Helper: `workspace/skills/coding-harness/coding_harness.py`
- Skill: `workspace/skills/coding-harness/SKILL.md`
- Pin: `workspace/skills/coding-harness/harness.lock.json`
- Policy: `workspace/skills/coding-harness/policy.json`

Mira self-work is intentionally out of scope for this harness skill.
Target clones use collision-free `owner--repo` paths and are not auto-pulled.
Run records and phase specs remain under ignored `workspace/runtime/`.
Restore replaces only manifest-managed files and never deletes runtime.

Update the harness pin only after reviewing and testing a specific revision.
The lock accepts only the canonical repository, contract version 2, and a full
lowercase 40-character SHA; `refresh-harness` checks out that SHA detached.

The adapter explicitly forwards the 3000-second policy timeout for `run` and
`run-plan`; cancellation cleanup is 15 seconds and the friend-safe OpenClaw
outer timeout remains 3600 seconds. Phase-spec paths are canonical files below
the runtime plans directory. Path, pin, environment, Git,
and record checks are enforced; prompts, hooks, and wrappers are advisory
defense in depth and do not provide hard network isolation.

## Infrastructure

- Blueprint repo: `/home/kenny/mira`
- Live OpenClaw state: `/home/kenny/mira/.openclaw`
- Live workspace: `/home/kenny/mira/.openclaw/workspace`
- OpenClaw source checkout: `/home/kenny/mira/openclaw-src`
- Compose project: `openclaw-mira`
- Gateway container: `openclaw-mira-openclaw-gateway-1`

For Mira behavior changes, edit the live workspace first when practical, then
run `scripts/sync-from-live.sh` and review the diff. For restore scripts,
templates, playbooks, and blueprint-only docs, edit the repo directly.

## Memory System

Mira uses a local-first memory stack for continuity:

- `SESSION-STATE.md` for hot working state.
- `MEMORY.md` for curated durable summaries.
- `memory/YYYY-MM-DD.md` for daily working notes.
- `DREAMS.md` for optional consolidation review.
- OpenClaw `memorySearch` and `active-memory` for bounded recall in direct sessions.
- `memory-lancedb` under ignored runtime storage for vector-backed warm memory.
- `workspace/skills/memory-cold-store/` for high-value git-notes cold storage.
- `workspace/skills/mira-memory/` for memory policy and health checks.

The blueprint tracks policy and empty restore scaffolding only.
`scripts/restore-to-live.sh` creates missing live memory files from
`templates/memory-scaffold/` without overwriting existing runtime memory. Do not
sync accumulated memory files, vector indexes, git-notes stores, cloud memory
exports, QMD indexes, session exports, or private memory history unless Kenny
explicitly asks for that data.

Memory debugging commands and privacy boundaries live in `RUNBOOK.md` and
`workspace/TOOLS.md`. Mira does not use third-party cloud memory by default.

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

Sync and restore use fsync-backed intent/applied journals. A later invocation
reconciles an incomplete transaction before staging new work; normalized
manifest duplicates, non-canonical roots, symlink roots, and root escapes fail
closed.

Provider API keys live in ignored per-instance secret env files under `.openclaw/secrets/`, never in tracked files or global shell startup files. See `RUNBOOK.md` for the OpenRouter rotation procedure.
