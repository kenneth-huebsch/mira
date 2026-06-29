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

## Memory Runtime

Mira's live memory files are in `/home/kenny/mira/.openclaw/workspace`:

- `SESSION-STATE.md` for hot working state.
- `MEMORY.md` for curated durable summaries.
- `memory/YYYY-MM-DD.md` for daily working notes.
- `DREAMS.md` for optional consolidation review.

The blueprint tracks empty scaffold templates under `templates/memory-scaffold/`
and restores them only when the corresponding live memory files are missing.
Existing memory files are preserved by `scripts/restore-to-live.sh`.

Mira's memory search uses OpenRouter's OpenAI-compatible embeddings endpoint via
`OPENROUTER_API_KEY`; the live key is loaded from ignored secret env files, not
tracked config. Useful checks inside Mira's agent runtime:

```bash
openclaw config validate
openclaw plugins list
openclaw memory status
openclaw memory status --deep
openclaw memory search "recent preference"
```

From host-side wrapper checks, command availability can differ from the in-agent
runtime. Prefer testing memory from a fresh Mira DM when validating end-to-end
agent behavior.

The `active-memory` plugin is enabled for direct `main` sessions. It should add
bounded pre-reply recall without persisting raw transcripts. Verify it through
`openclaw plugins list`, config inspection, and a fresh Mira DM that references a
known stored memory.

LanceDB is the active memory plugin. The container path is
`~/.openclaw/memory/lancedb`; on this host it maps to
`/home/kenny/mira/.openclaw/memory/lancedb`.

```bash
openclaw memory status
openclaw memory status --deep
openclaw memory store "durable memory text"
openclaw memory search "recent preference"
openclaw memory index --force
```

In a confirmed fresh DM, `openclaw memory status` should report
`memory-lancedb`, the LanceDB backend path, and tables such as `episodic`,
`semantic`, and `working`.

Host-side debugging checklist:

```bash
cd /home/kenny/mira
./scripts/openclaw-cli.sh config validate
./scripts/openclaw-cli.sh plugins list
MIRA_MEMORY_COLD_STORE_DIR=/home/kenny/mira/.openclaw/memory/git-notes \
  python3 /home/kenny/mira/.openclaw/workspace/skills/memory-cold-store/memory_cold_store.py doctor
python3 /home/kenny/mira/.openclaw/workspace/skills/external-memory/external_memory.py \
  search "communication preferences"
```

If a host-side `openclaw memory ...` command is unavailable or shows different
tool exposure than a real conversation, verify from a fresh Mira DM before
changing config; CLI command surfaces have differed across OpenClaw builds.

Memory service secrets such as embedding provider keys or Mem0
belong in ignored per-instance files under `/home/kenny/mira/.openclaw/secrets/`.
`scripts/start-openclaw.sh` and `scripts/openclaw-cli.sh` source
`scripts/load-openclaw-env.sh`, which loads `openrouter.env` for
`OPENROUTER_API_KEY` and `memory.env` for `MEM0_API_KEY` when those ignored files
exist.
Do not commit live memory contents, vector indexes, git-notes stores, cloud
memory exports, session memory indexes, or service keys.

Git-notes cold memory uses a workspace-local helper and an ignored runtime repo:

```bash
python3 /home/kenny/mira/.openclaw/workspace/skills/memory-cold-store/memory_cold_store.py doctor
python3 /home/kenny/mira/.openclaw/workspace/skills/memory-cold-store/memory_cold_store.py search "query"
```

From the host, use Mira's live runtime path explicitly:

```bash
MIRA_MEMORY_COLD_STORE_DIR=/home/kenny/mira/.openclaw/memory/git-notes \
  python3 /home/kenny/mira/.openclaw/workspace/skills/memory-cold-store/memory_cold_store.py doctor
```

Optional Mem0 keys live in:

```bash
/home/kenny/mira/.openclaw/secrets/memory.env
```

Use `templates/memory.env.example` for the redacted shape. Dry-run verification
does not need keys:

```bash
python3 /home/kenny/mira/.openclaw/workspace/skills/external-memory/external_memory.py \
  add "approved durable summary" --category preference
python3 /home/kenny/mira/.openclaw/workspace/skills/external-memory/external_memory.py \
  search "communication preferences"
```

Live external memory calls require `--live` and the matching key in
`memory.env`. Do not upload raw transcripts, raw emails, logs, credentials,
tokens, browser state, session state, or unreviewed memory exports.

The managed OpenClaw `entrypoint.sh` installs the optional `mem0ai` Python
package for live Mem0 calls when it is missing.

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
