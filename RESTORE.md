# Restore Rumi

This restores Rumi's behavior, not her exact runtime state or memory history.

## Fresh Host Flow

1. Clone OpenClaw:

```bash
git clone https://github.com/openclaw/openclaw.git ~/openclaw
```

2. Install and run OpenClaw setup/onboarding using the current upstream docs.

3. Clone this blueprint:

```bash
git clone git@github.com:<your-github-user-or-org>/rumi.git ~/rumi
```

4. Copy behavior files into the new workspace:

```bash
cd ~/rumi
./scripts/restore-to-live.sh
```

5. Manually configure credentials and runtime secrets:

- OpenClaw provider auth and model credentials.
- Telegram bot token.
- Gateway token.
- Gmail/Google OAuth credentials for `gog`.
- Todoist MCP credentials.
- Device pairing/auth state as needed.

Use `templates/openclaw.friend-safe.example.json` and `templates/cron-jobs.friend-safe.example.json` as structure references, but do not copy placeholder credential values into production.

6. Recreate or import cron jobs using the schedules and delivery shape in `templates/cron-jobs.friend-safe.example.json`.

7. Verify behavior:

- Interactive chat loads `AGENTS.md`, `SOUL.md`, `IDENTITY.md`, `USER.md`, `TOOLS.md`, and `HEARTBEAT.md`.
- Cron prompts exist under `workspace/cron/`.
- Required cron dependency files exist under `workspace/memory/`.
- The memory plugin is installed and can read `skills/memory_manager.md` and `skills/engagement_priorities_manager.md`.
- Gmail, Calendar, Todoist, and Telegram commands work after credentials are restored.

## What This Does Not Restore

- Live memory history.
- Existing reminders.
- Gmail OAuth tokens or Google credentials.
- Telegram bot token or gateway token.
- Device auth, sessions, logs, browser state, or cron run history.

Those are intentionally excluded so the repo can be shared with trusted friends without exposing credentials.
