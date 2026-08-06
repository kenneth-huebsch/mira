---
name: safe-openclaw-config
description: Safely edit, validate, restart, and recover OpenClaw configuration for Mira. Use when changing openclaw.json, default models, gateway settings, auth-safe config, container state, or when the OpenClaw gateway is unhealthy after a config change.
---

# Safe OpenClaw Config

Use this skill for live OpenClaw configuration changes.

## Prefer The CLI

Prefer:

```bash
docker exec --user node openclaw-mira-openclaw-gateway-1 openclaw config set <path> <value>
docker exec --user node openclaw-mira-openclaw-gateway-1 openclaw config validate
```

For cron changes, use `openclaw cron edit` instead of config editing.

## Restart And Verify

If the CLI says a restart is required:

```bash
docker restart openclaw-mira-openclaw-gateway-1
docker ps --format '{{.Names}} {{.Status}}'
docker exec --user node openclaw-mira-openclaw-gateway-1 openclaw health
```

Wait until the container is healthy before calling the work done.

## Config Ownership Recovery

Container-side config writes can accidentally leave `/home/node/.openclaw/openclaw.json` unreadable by the gateway process.

If logs show `EACCES: permission denied, open '/home/node/.openclaw/openclaw.json'`, fix ownership exactly as OpenClaw recommends:

```bash
docker exec -u root openclaw-mira-openclaw-gateway-1 chown 1000 /home/node/.openclaw/openclaw.json
docker restart openclaw-mira-openclaw-gateway-1
```

Then verify health again.

## Verification

After changing config, verify from inside the container:

```bash
docker exec --user node openclaw-mira-openclaw-gateway-1 sh -lc 'python3 - <<'"'"'PY'"'"'
import json
with open("/home/node/.openclaw/openclaw.json") as f:
    data = json.load(f)
print(data["agents"]["defaults"]["model"]["primary"])
PY'
```

Also inspect the host-mounted file when permissions allow:

```bash
/home/kenny/mira/.openclaw/openclaw.json
```

## Environment Secrets

- Environment-style secrets live only in
  `/home/kenny/mira/.openclaw/.env`, with mode `600`.
- Audit names, syntax, duplicates, and presence without printing values.
- Restart through `/home/kenny/mira/scripts/stop-openclaw.sh` and
  `start-openclaw.sh` after changes so both Compose and OpenClaw reload them.
- For the default Telegram account, set `TELEGRAM_BOT_TOKEN` in `.env` and
  omit `botToken`, `tokenFile`, and `token` from `channels.telegram`.
- Keep OpenClaw-managed OAuth/device state and file-shaped private keys in
  their native ignored runtime stores.

## Safety Notes

- Never expose or commit gateway tokens, bot tokens, OAuth tokens, credentials, sessions, logs, or private memory history.
- Keep live behavior changes synced back to the Mira blueprint repo when appropriate.
- If the gateway does not become healthy, inspect recent logs before making further changes:

```bash
docker logs --since 2m openclaw-mira-openclaw-gateway-1
```
