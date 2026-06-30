# Restore Mira

This restores Mira's coding-harness routing behavior, not her exact runtime state,
credentials, sessions, or memory history.

## Fresh Host Flow

1. Clone OpenClaw:

```bash
git clone https://github.com/openclaw/openclaw.git /home/kenny/mira/openclaw-src
```

2. Install and run OpenClaw setup/onboarding using the current upstream docs.

3. Clone this blueprint:

```bash
git clone git@github.com:<your-github-user-or-org>/mira.git ~/mira
```

4. Copy behavior files into the new workspace:

```bash
cd ~/mira
./scripts/restore-to-live.sh
```

This also restores `openclaw/entrypoint.sh` into the OpenClaw checkout so the
Docker gateway can install/link GitHub CLI, Cursor CLI, `gog`, `jq`,
`ripgrep`, `python3-pip`, and basic runtime tools for harness routing,
on-demand Gmail access, session-log search, and memory checks when the compose
file mounts that entrypoint.

5. Manually configure credentials and runtime secrets:

- OpenClaw provider auth and model credentials.
- Telegram bot token.
- Gateway token.
- Gmail/Google OAuth credentials for `gog`.
- Device pairing/auth state as needed.
- OpenRouter secret env at `.openclaw/secrets/openrouter.env` for model and
  memory embeddings.
- Docker Compose env and volume mounts, including the restored
  `/home/kenny/mira/openclaw-src/entrypoint.sh` if using the container runtime.

Use `templates/openclaw.friend-safe.example.json` as a structure reference for
`memorySearch`, `active-memory`, `memory-lancedb`, and enabled skills, but do not
copy placeholder credential values into production.

6. Ensure the runtime memory plugin is installed if the fresh OpenClaw home does
not already have it:

```bash
cd ~/mira
./scripts/openclaw-cli.sh plugins install @openclaw/memory-lancedb
./scripts/openclaw-cli.sh config validate
```

7. Mira has no cron jobs by default. Only create scheduled behavior if Kenny explicitly asks for it.

8. Verify behavior:

- Interactive chat loads `AGENTS.md`, `SOUL.md`, `IDENTITY.md`, `USER.md`, `TOOLS.md`, and `HEARTBEAT.md`.
- No inherited cron prompts or capability bundles are restored by default.
- Missing workspace memory scaffold files are created from `templates/memory-scaffold/`; existing live memory files are preserved.
- No accumulated memory history, QMD indexes, LanceDB databases, git-notes stores, or cloud memory exports are restored by default.
- Telegram DM works for Kenny after credentials are restored.
- On-demand Gmail reads work through `gog` after Gmail OAuth is restored.
- The `coding-harness` skill and helper are restored.
- The `mira-memory` and `memory-cold-store` skills and helpers are restored.
- `python3 skills/mira-memory/mira_memory_check.py` passes from the workspace.
- `python3 skills/memory-cold-store/memory_cold_store.py doctor` passes.
- `git`, `gh`, and Cursor CLI are available in the gateway container.
- `jq` and `rg` are available in the gateway container for bundled skills such
  as `session-logs`.
- `python3 skills/coding-harness/coding_harness.py check-config` passes after GitHub CLI, private harness repo access, and Cursor CLI auth are configured.

## What This Does Not Restore

- Live memory history.
- LanceDB vector databases, git-notes cold stores, or session memory exports.
- QMD indexes, downloaded models, session exports, or `~/.openclaw/agents/*/qmd/`.
- Gmail OAuth tokens or Google credentials.
- Telegram bot token or gateway token.
- Device auth, sessions, logs, browser state, or cron run history.

Those are intentionally excluded so the repo can be shared with trusted friends without exposing credentials.
