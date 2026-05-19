# Run Mira

This folder is Mira's self-contained OpenClaw home.

Tracked files are the friend-safe blueprint: behavior docs, scripts, templates,
plugins, skills, and restore docs. Local runtime infrastructure is
kept beside it but ignored by git:

- `openclaw-src/` - Mira's OpenClaw source checkout.
- `.openclaw/` - Mira's live OpenClaw state, config, credentials, sessions,
  cron state, QMD runtime, Telegram state, and workspace.

## Commands

Start Mira:

```bash
cd /home/kenny/mira
./scripts/start-openclaw.sh
```

Stop Mira:

```bash
cd /home/kenny/mira
./scripts/stop-openclaw.sh
```

Run OpenClaw CLI commands in Mira's compose project:

```bash
cd /home/kenny/mira
./scripts/openclaw-cli.sh dashboard --no-open
```

## Defaults

- Compose project: `openclaw-mira`
- OpenClaw source: `/home/kenny/mira/openclaw-src`
- OpenClaw state: `/home/kenny/mira/.openclaw`
- Workspace: `/home/kenny/mira/.openclaw/workspace`
- Gateway port: `18791`
- Bridge port: `18792`
- UI/dev port: `3501`

Override these with environment variables only for recovery or migration work.
