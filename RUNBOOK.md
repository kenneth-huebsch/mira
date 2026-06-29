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

Upgrade Mira's OpenClaw source:

```bash
cd /home/kenny/mira/openclaw-src
git status --short
GIT_TERMINAL_PROMPT=0 git fetch origin main
git merge --ff-only FETCH_HEAD
git status --short
```

If source files under `src/` are dirty, report them before upgrading. Mira's
managed OpenClaw source-local files are `docker-compose.yml` and
`entrypoint.sh`; keep those local changes and sync them back to the blueprint
with `cd /home/kenny/mira && ./scripts/sync-from-live.sh`.

Rebuild and recreate Mira's gateway after the source update:

```bash
cd /home/kenny/mira/openclaw-src
docker build -t openclaw:local .
cd /home/kenny/mira
./scripts/start-openclaw.sh
```

The Docker build may be slow after a large upstream jump because the OpenClaw
image runs dependency install, server build, UI build, and production pruning.

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

Mira's harness routing and on-demand Gmail commands run through OpenClaw `exec`
in the gateway container, with workspace paths rooted at
`/home/node/.openclaw/workspace`. Container runtime dependencies are prepared by
`openclaw/entrypoint.sh`; live credentials stay under
`/home/kenny/mira/.openclaw` on the host and map into `/home/node/.openclaw`
inside the container.

Mira has no cron jobs by default. If scheduled behavior is added later, document
the prompt and dependencies in the blueprint before relying on it.

## Coding Harness

Mira routes non-Mira coding requests through Kenny's private agent harness:

- Harness repo: `https://github.com/kenneth-huebsch/agent`
- Host runtime checkout: `/home/kenny/mira/.openclaw/workspace/runtime/repos/agent`
- Container runtime checkout: `/home/node/.openclaw/workspace/runtime/repos/agent`
- Helper: `/home/node/.openclaw/workspace/skills/coding-harness/coding_harness.py`

Useful checks:

```bash
cd /home/kenny/mira
docker exec --user node openclaw-mira-openclaw-gateway-1 \
  python3 /home/node/.openclaw/workspace/skills/coding-harness/coding_harness.py check-config
```

The preflight requires GitHub CLI auth, private harness repo access, and Cursor
CLI auth. If Cursor auth is missing, use
`workspace/skills/cursor-agent-login/SKILL.md` or provide `CURSOR_API_KEY`
through ignored runtime secrets before expecting coding runs to execute.

Mira self-work is intentionally out of scope for this harness skill.

## Infrastructure Paths

Use these paths when maintaining Mira's setup outside the harness route:

- Blueprint repo: `/home/kenny/mira`
- Live workspace: `/home/kenny/mira/.openclaw/workspace`
- Live config/state: `/home/kenny/mira/.openclaw`
- OpenClaw source checkout: `/home/kenny/mira/openclaw-src`
- Gateway container: `openclaw-mira-openclaw-gateway-1`

Behavior changes should usually start in the live workspace and then be synced
back:

```bash
cd /home/kenny/mira
./scripts/sync-from-live.sh
git diff
```

Restore and runtime verification:

```bash
cd /home/kenny/mira
./scripts/restore-to-live.sh
./scripts/openclaw-cli.sh cron list --json
```
