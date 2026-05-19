# Restore Mira

This restores Mira's behavior, not her exact runtime state or memory history.

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
Docker gateway can install/link `gog`, QMD, and `agent-browser` at startup when
the compose file mounts that entrypoint.

5. Manually configure credentials and runtime secrets:

- OpenClaw provider auth and model credentials.
- Telegram bot token.
- Gateway token.
- Gmail/Google OAuth credentials for `gog`.
- Todoist MCP credentials.
- Device pairing/auth state as needed.
- Docker Compose env and volume mounts, including the restored
  `/home/kenny/mira/openclaw-src/entrypoint.sh` if using the container runtime.

Use `templates/openclaw.friend-safe.example.json` as a structure reference, but do not copy placeholder credential values into production.

6. Mira has no cron jobs by default. Only create scheduled behavior if Kenny explicitly asks for it.

7. Verify behavior:

- Interactive chat loads `AGENTS.md`, `SOUL.md`, `IDENTITY.md`, `USER.md`, `TOOLS.md`, and `HEARTBEAT.md`.
- No inherited cron prompts or capability bundles are restored by default.
- No workspace memory files or memory plugin are restored by default.
- QMD memory search is available with `openclaw memory status --agent main` and
  can search selected markdown docs. Historical JSONL memory is not backfilled,
  and session indexing should remain off unless intentionally enabled.
- Gmail, Calendar, Todoist, and Telegram commands work after credentials are restored.

## What This Does Not Restore

- Live memory history.
- QMD indexes, downloaded models, session exports, or `~/.openclaw/agents/*/qmd/`.
- Existing reminders.
- Gmail OAuth tokens or Google credentials.
- Telegram bot token or gateway token.
- Device auth, sessions, logs, browser state, or cron run history.

Those are intentionally excluded so the repo can be shared with trusted friends without exposing credentials.
