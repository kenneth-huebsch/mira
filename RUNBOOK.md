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


## Provider Credentials

Mira's OpenRouter auth is per-instance, not global shell state. The live auth
profile references `OPENROUTER_API_KEY` through a SecretRef-style env reference,
and `scripts/start-openclaw.sh` plus `scripts/openclaw-cli.sh` load it from:

```bash
/home/kenny/mira/.openclaw/secrets/openrouter.env
```

The scripts pass those values into Docker through `openclaw/provider-auth.compose.yml`, so the setup does not depend on global shell exports or source checkout defaults.

That file is ignored runtime state and must not be committed. To rotate the
OpenRouter token, edit `OPENROUTER_API_KEY` in that file, keep permissions at
`600`, then restart this OpenClaw home:

```bash
cd /home/kenny/mira
./scripts/stop-openclaw.sh
./scripts/start-openclaw.sh
```

Do not put provider API keys in `~/.bashrc`, tracked docs, templates, or
`auth-profiles.json`. The expected live auth profile shape is a `keyRef` to
`OPENROUTER_API_KEY`; the token value belongs only in the ignored secret env
file.

## Runtime Boundary

Mira's scheduled helpers run through OpenClaw `exec` in the gateway container,
with workspace paths rooted at `/home/node/.openclaw/workspace`. Container
runtime dependencies are prepared by `openclaw/entrypoint.sh`; live credentials
stay under `/home/kenny/mira/.openclaw` on the host and map into
`/home/node/.openclaw` inside the container.
