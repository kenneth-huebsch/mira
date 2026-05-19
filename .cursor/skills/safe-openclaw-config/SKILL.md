---
name: safe-openclaw-config
description: Safely edit, validate, restart, and recover OpenClaw configuration for Mira. Use when changing openclaw.json, default models, gateway settings, auth-safe config, container state, or when the OpenClaw gateway is unhealthy after a config change.
---

# Safe OpenClaw Config

Use this skill for live OpenClaw configuration changes.

## Prefer The CLI

Prefer:

```bash
docker exec openclaw-openclaw-gateway-1 openclaw config set <path> <value>
docker exec openclaw-openclaw-gateway-1 openclaw config validate
```

For cron changes, use `openclaw cron edit` instead of config editing.

## Restart And Verify

If the CLI says a restart is required:

```bash
docker restart openclaw-openclaw-gateway-1
docker ps --format '{{.Names}} {{.Status}}'
docker exec openclaw-openclaw-gateway-1 openclaw health
```

Wait until the container is healthy before calling the work done.

## Config Ownership Recovery

Container-side config writes can accidentally leave `/home/node/.openclaw/openclaw.json` unreadable by the gateway process.

If logs show `EACCES: permission denied, open '/home/node/.openclaw/openclaw.json'`, fix ownership exactly as OpenClaw recommends:

```bash
docker exec -u root openclaw-openclaw-gateway-1 chown 1000 /home/node/.openclaw/openclaw.json
docker restart openclaw-openclaw-gateway-1
```

Then verify health again.

## Verification

After changing config, verify from inside the container:

```bash
docker exec openclaw-openclaw-gateway-1 sh -lc 'python3 - <<'"'"'PY'"'"'
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

## Safety Notes

- Never expose or commit gateway tokens, bot tokens, OAuth tokens, credentials, sessions, logs, or private memory history.
- Keep live behavior changes synced back to the Mira blueprint repo when appropriate.
- If the gateway does not become healthy, inspect recent logs before making further changes:

```bash
docker logs --since 2m openclaw-openclaw-gateway-1
```
