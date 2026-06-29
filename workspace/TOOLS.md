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

## Coding Harness

Mira routes non-Mira coding requests through Kenny's private agent harness:

- Harness repo: `https://github.com/kenneth-huebsch/agent`
- Host runtime checkout: `/home/kenny/mira/.openclaw/workspace/runtime/repos/agent`
- Container runtime checkout: `/home/node/.openclaw/workspace/runtime/repos/agent`
- Helper: `python3 skills/coding-harness/coding_harness.py`
- Skill: `skills/coding-harness/SKILL.md`

Core commands:

```bash
python3 skills/coding-harness/coding_harness.py check-config
python3 skills/coding-harness/coding_harness.py refresh-harness
python3 skills/coding-harness/coding_harness.py run --target <path-or-repo> --prompt "<task>"
```

The harness owns implementation policy. Mira should not restate generic coding
rules in core context. For requests to modify Mira herself, do not use this
harness route; self-work belongs to a separate future skill.

Runtime prerequisites: GitHub CLI auth must work, the private harness repo must
be readable, and Cursor CLI must be authenticated. Use
`skills/cursor-agent-login/SKILL.md` when Cursor auth is missing.

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

If Kenny asks for scheduled behavior, create it intentionally through the OpenClaw cron CLI, document the
new prompt and dependencies, and update the sync/restore manifest.
