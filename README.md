# rumi

Friend-safe OpenClaw blueprint for recreating Rumi on a fresh host.

This repo is allowed to contain personalized behavior, account conventions, chat IDs, calendar IDs, and cron prompts. It must not contain credentials, provider API keys, OAuth tokens, bot tokens, gateway tokens, device auth, live sessions, or logs.

## Layout

- `workspace/` mirrors the behavior-bearing parts of `~/.openclaw/workspace/`.
- `templates/` contains friend-safe examples of runtime config and cron jobs with credential fields redacted.
- `scripts/sync-from-live.sh` updates the blueprint from the running host.
- `scripts/restore-to-live.sh` copies the blueprint into a new OpenClaw workspace.
- `docs/cron-dependencies.md` tracks files that cron prompts or context loaders depend on.
- `docs/source-change-audit.md` records whether local OpenClaw source changes matter for restore.

## Update The Backup

After changing Rumi behavior on the live host:

```bash
cd ~/rumi
./scripts/sync-from-live.sh
git diff
git status
```

If the diff looks right, commit and push.

## Safety Line

The sync script is allowlist-based. It copies known behavior files and seeds required memory files, but it does not copy accumulated memory history, runtime logs, sessions, device state, credentials, or tokens.
