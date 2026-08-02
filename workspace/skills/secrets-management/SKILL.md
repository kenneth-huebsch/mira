---
name: secrets-management
description: "Manage secrets for Mira's workspace. Use when adding, updating, rotating, or auditing credentials and API keys."
metadata:
  openclaw:
    emoji: "🔐"
---

# Secrets Management

## Single Source of Truth

Environment-style secrets live in `~/.openclaw/.env` (OpenClaw's native env
fallback). On this host, that container path is backed by
`/home/kenny/mira/.openclaw/.env`. OpenClaw loads it at process startup.

**Never** store secrets in:
- Tracked workspace files (TOOLS.md, MEMORY.md, skills, etc.)
- Shell startup files (~/.bashrc, ~/.profile)
- Git repos (tracked or runtime)
- Memory notes or daily logs
- The old `secrets/*.env` pattern (deprecated)

## Format

```bash
# ~/.openclaw/.env
KEY=value
# No quotes needed for simple values
# No comments mixed with secret lines (keep it clean)
```

## Rules

1. **One file, all secrets.** `~/.openclaw/.env` is the single source. Do not
   create per-service `.env` files under `secrets/`.

2. **Permissions.** The file must be mode `600`. Never print its values.

3. **Restart after changes.** From the host, restart through the instance
   wrappers so Compose and OpenClaw both receive the new environment:
   `cd /home/kenny/mira && ./scripts/stop-openclaw.sh &&
   ./scripts/start-openclaw.sh`.

4. **No secrets in chat.** Never paste secret values into Telegram or any
   channel. Reference them by name only.

5. **Do not display the file.** Audit variable names and syntax with a parser
   that never emits values. Do not rely on redacting a full-file dump after
   reading it into tool output.

6. **Telegram token.** Store it as `TELEGRAM_BOT_TOKEN=...`. For the default
   Telegram account, omit `botToken`, `tokenFile`, and `token` from
   `channels.telegram`; OpenClaw then uses its documented environment fallback.
   `token` is not a valid Telegram channel config key.

7. **Config wiring.** A value in `.env` is useful only if the consuming process
   reads it. OpenClaw reads this file natively; Docker Compose interpolation is
   handled by Mira's host wrappers, which source the same file before startup.
   Add new Compose environment mappings when a service needs a variable in the
   container.

## Common Operations

### Audit current secrets

Verify that the file exists, has mode `600`, contains only valid `KEY=value`
entries, has no duplicate names, and contains the required variable names.
Never emit values.

### Add a new secret

Edit `/home/kenny/mira/.openclaw/.env` locally, add one `KEY=value` line, keep
mode `600`, update Compose wiring if needed, then restart through Mira's host
wrappers.

### Rotate a secret

Replace the existing key exactly once without printing either value, preserve
mode `600`, restart through Mira's host wrappers, and run a service-specific
read-only check.

### Verify a secret is loaded

Check only presence, for example with a script that prints `KEY_NAME=set` or
`KEY_NAME=missing`. Never print the environment value.

## Migration from secrets/*.env

The old `secrets/*.env` pattern (n8n.env, wordpress.env, aws.env, etc.) is
deprecated. All new environment-style secrets go in `~/.openclaw/.env`.

When migrating:
1. Merge each unique `KEY=value` entry into `~/.openclaw/.env` without
   displaying values
2. Update any documentation or scripts that reference `secrets/old-file.env`
3. Update host and Compose wiring for the unified file
4. Restart and run read-only service checks
5. Remove legacy files only after all checks pass

## What Belongs Here

- API keys (OpenRouter, Anthropic, n8n, AWS, etc.)
- Service credentials (WordPress, Telegram, etc.)
- Debug/verbose flags that contain no secrets

## What Does NOT Belong Here

- AWS session tokens (use IAM roles or STS instead)
- OAuth access/refresh tokens managed by OpenClaw or another credential store
- Repository credentials (use gh auth)
- Certificate/private-key or other multiline file credentials (mount as
  mode-`600` files in ignored runtime state)
