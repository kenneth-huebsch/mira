# TOOLS.md

Canonical reference for Mira's tool conventions. This file is loaded into agent
runs, so put tool mechanics here instead of scattering command details across
prompts.

## OpenClaw Exec Runtime

Mira's OpenClaw `exec` tool runs inside the gateway container with workspace
paths rooted at `/home/node/.openclaw/workspace`.

Runtime dependencies belong in `openclaw/entrypoint.sh` so restored containers
prepare the same command surface. Live credentials and tokens remain under
`.openclaw` secrets/state and must not be copied into tracked files.

## Coding Tools

- Inspect the repository before changing it.
- Use project-native package managers and test commands when they are clear from the repo.
- Use `git status` and `git diff` to separate Mira's changes from Kenny's existing work.
- Use `gh` for GitHub work when Kenny asks for GitHub issues, PRs, checks, or releases.
- Do not push, force-push, deploy, change secrets, or delete work unless Kenny explicitly asks.
- If Cursor CLI is available as `agent`, use it only for explicitly delegated coding-agent workflows.

## Gmail With `gog`

Mira may check her Gmail on demand when Kenny asks. There are no Gmail crons by
default.

Mira's Gmail account is `mira.agentops@gmail.com`. Use one of the following on
every Gmail call:

- Set `GOG_ACCOUNT=mira.agentops@gmail.com` in the environment, or
- Pass `--account mira.agentops@gmail.com` explicitly.

Useful read-only patterns:

```bash
gog gmail messages search "in:inbox newer_than:30d" --max 20 --account mira.agentops@gmail.com --json
gog gmail get <messageId> --account mira.agentops@gmail.com --json
```

Do not send email, mark messages read, archive, delete, label, create filters,
or otherwise mutate the mailbox unless Kenny explicitly asks for that action.

Use `skills/gog-reauth/SKILL.md` when `gog` reports an expired or revoked Gmail
OAuth token, or when Kenny asks to re-run the Gmail OAuth flow.

## Telegram

Telegram DM is enabled as a Kenny control surface. Keep replies concise and do
not include raw tool output, credentials, internal IDs, transcript paths, or
hidden reasoning.

## Cron

Mira has no recurring cron jobs by default. If Kenny later asks for scheduled
behavior, create it intentionally through the OpenClaw cron CLI, document the
new prompt and dependencies, and update the sync/restore manifest.
