# Rumi Backup

Use this playbook when syncing, reviewing, committing, pushing, or restoring the
Rumi blueprint.

## What Belongs Here

Allowed friend-safe content:

- Rumi behavior docs and persona files.
- Cron prompts and cron dependency seed files.
- Workspace-local plugins and skills.
- Local persona assets such as `workspace/assets/rumi.jpg`.
- Host-level OpenClaw restore assets under `openclaw/`, currently
  `openclaw/entrypoint.sh`.
- Friend-safe config templates with credentials redacted.
- Restore docs and agent playbooks.

Never include:

- Provider API keys, OAuth tokens, bot tokens, gateway tokens, or passwords.
- `~/.openclaw/credentials/**`, `gcal-tokens/**`, `gogcli/credentials.json`, device auth, or auth profiles.
- Sessions, logs, browser/chromium state, delivery queues, cron run history, or dependency folders.
- Accumulated private memory history unless Kenny explicitly asks for it.
- QMD runtime state, indexes, downloaded models, or session exports, including
  `~/.openclaw/agents/*/qmd/` and `~/.openclaw/runtime/qmd/`.

## Sync Workflow

```bash
cd /home/kenny/rumi
./scripts/sync-from-live.sh
git status --short
git diff --stat
```

The sync script is allowlist-based. It copies behavior files, local assets, and
approved host-level OpenClaw files, then reseeds required memory paths without
copying live memory history or QMD runtime state.

## Review Checklist

Before committing or pushing:

1. Confirm changed files are behavior, docs, scripts, templates, or allowed assets.
2. Inspect generated templates for real tokens or authorization headers.
3. Run a token scan. At minimum:

```bash
rg -n "(Bearer\\s+[A-Za-z0-9._-]{20,}|AIza[0-9A-Za-z_-]{20,}|ya29\\.[0-9A-Za-z_-]+|gh[pousr]_[0-9A-Za-z_]{20,}|sk-[0-9A-Za-z_-]{20,}|BEGIN (RSA|OPENSSH|PRIVATE) KEY)" /home/kenny/rumi
```

4. If the scan finds a real secret, remove it, fix the generator or allowlist, and regenerate.
5. If the scan only finds documentation examples or redacted placeholders, proceed.

## Commit And Push

Only commit when Kenny asks for it. Use the repo's normal remote:

```bash
cd /home/kenny/rumi
git add .
git commit -m "Update Rumi behavior"
git push
```

## Restore Workflow

On a fresh host, clone upstream OpenClaw, complete onboarding, clone this repo,
then run:

```bash
cd /home/kenny/rumi
./scripts/restore-to-live.sh
```

After restore, manually configure credentials, cron schedules/delivery, provider
auth, Gmail/Google/Todoist/Telegram auth, Docker Compose mounts/env, and device
pairing as needed. QMD is installed at container startup by the restored
entrypoint when Docker is configured to mount it.
