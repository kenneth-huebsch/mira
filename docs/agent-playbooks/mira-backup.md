# Mira Backup

Use this playbook when syncing, reviewing, committing, pushing, or restoring the
Mira blueprint.

## What Belongs Here

Allowed friend-safe content:

- Mira behavior docs, persona files, harness-routing skills, and helper scripts.
- Future cron prompts and dependency files, only if Kenny explicitly adds scheduled behavior.
- Workspace-local plugins and skills.
- Host-level OpenClaw restore assets under `openclaw/`, currently
  `openclaw/docker-compose.yml` and `openclaw/entrypoint.sh`.
- Friend-safe config templates with credentials redacted.
- Empty memory scaffold templates and policy docs.
- Workspace-local memory helper skills, such as `mira-memory` and
  `memory-cold-store`, but not their runtime stores.
- Restore docs and agent playbooks.

Never include:

- Provider API keys, OAuth tokens, bot tokens, gateway tokens, or passwords.
- `~/.openclaw/credentials/**`, `gcal-tokens/**`, `gogcli/credentials.json`, device auth, or auth profiles.
- Sessions, logs, browser/chromium state, delivery queues, cron run history, or dependency folders.
- Accumulated private memory history unless Kenny explicitly asks for it,
  including live `SESSION-STATE.md`, `MEMORY.md`, `DREAMS.md`,
  `memory/*`, vector stores, LanceDB databases, git-notes stores, and session
  memory indexes.
- QMD runtime state, indexes, downloaded models, or session exports, including
  `~/.openclaw/agents/*/qmd/` and `~/.openclaw/runtime/qmd/`.

## Sync Workflow

```bash
cd /home/kenny/mira
./scripts/sync-from-live.sh
git status --short
git diff --stat
```

The sync script is manifest-based. It copies only behavior files listed in
`scripts/workspace-manifest.txt` plus approved host-level OpenClaw files. It
does not copy live memory history, vector indexes, git-notes stores, QMD runtime
state, sessions, logs, cron run history, or credentials.
Sync and restore reject traversal and symlink destinations, stage all managed
files before replacement, fsync staged files, backups, journals, replacements,
and parent directories, and retain ignored rollback metadata. Each replacement
has a durable intent/applied journal; the next invocation rolls back an
incomplete transaction before starting new work. Both directions reject
duplicate normalized manifest entries, non-canonical or symlinked roots, and
any source or destination that cannot be proven beneath its declared root.
Restore never
deletes `workspace/runtime`; verify records, phase specs, checkouts, locks,
checkpoints, and existing memory survive two restores.

Memory scaffold templates are intentionally not copied from the live workspace
through `scripts/workspace-manifest.txt`. They live under
`templates/memory-scaffold/` and are used only by `scripts/restore-to-live.sh`
when corresponding live memory files are missing.

## Review Checklist

Before committing or pushing:

1. Confirm changed files are behavior, docs, scripts, templates, workspace skills, or workspace helper scripts.
2. Inspect generated templates for real tokens or authorization headers.
3. Run a token scan. At minimum:

```bash
rg -n "(Bearer\\s+[A-Za-z0-9._-]{20,}|AIza[0-9A-Za-z_-]{20,}|ya29\\.[0-9A-Za-z_-]+|gh[pousr]_[0-9A-Za-z_]{20,}|sk-[0-9A-Za-z_-]{20,}|sk-or-v1-[0-9A-Za-z_-]{20,}|BEGIN (RSA|OPENSSH|PRIVATE) KEY)" /home/kenny/mira
```

4. If the scan finds a real secret, remove it, fix the generator or allowlist, and regenerate.
5. If the scan only finds documentation examples or redacted placeholders, proceed.
6. Validate `harness.lock.json` contains the canonical repository, matching
   numeric contract version, and the reviewed full immutable SHA. Run the
   offline unit suite.

## Commit And Push

Only commit when Kenny asks for it. Use the repo's normal remote:

```bash
cd /home/kenny/mira
git add .
git commit -m "Update Mira behavior"
git push
```

## Restore Workflow

On a fresh host, clone upstream OpenClaw, complete onboarding, clone this repo,
then run:

```bash
cd /home/kenny/mira
./scripts/restore-to-live.sh
```

After restore, manually configure provider auth, Telegram auth, Gmail/Google
OAuth for on-demand `gog` reads, Docker Compose mounts/env, device pairing, and
the ignored OpenRouter env file for memory embeddings. Mira has no cron jobs by
default; keep `~/.openclaw/cron/jobs.json` empty unless Kenny explicitly adds
scheduled behavior later.
