---
name: cursor-agent-login
description: Configure or verify Cursor CLI authentication inside Mira's OpenClaw gateway container. Use when coding-harness preflight reports Cursor auth missing, when `agent status` says not logged in, or when Kenny asks to set up or rotate Mira's Cursor API key.
---

# Cursor Agent Auth

Mira authenticates Cursor CLI with `CURSOR_API_KEY` from the ignored
`.openclaw/.env` file. Do not use browser-based `agent login` for Mira.

## Configure

1. Put `CURSOR_API_KEY=...` in `/home/kenny/mira/.openclaw/.env` at mode `600`.
2. Restart this OpenClaw home so Compose passes the key into the gateway:

```bash
cd /home/kenny/mira
./scripts/stop-openclaw.sh
./scripts/start-openclaw.sh
```

3. If Mira previously used browser login, clear the stored session once:

```bash
docker exec --user node openclaw-mira-openclaw-gateway-1 sh -lc 'agent logout'
```

## Check Status

Run from the host:

```bash
docker exec --user node openclaw-mira-openclaw-gateway-1 sh -lc 'agent status'
```

If authenticated, verify the harness preflight:

```bash
docker exec --user node openclaw-mira-openclaw-gateway-1 \
  python3 /home/node/.openclaw/workspace/skills/coding-harness/coding_harness.py check-config
```

## Rotate

Replace `CURSOR_API_KEY` in `.openclaw/.env` without printing the value,
restart OpenClaw, then rerun `agent status` and the coding-harness preflight.

## Notes

- Do not paste Cursor API keys or auth files into chat.
- Do not commit `CURSOR_API_KEY` or Cursor auth state. Both belong in ignored
  runtime only.
- The coding harness forwards `CURSOR_API_KEY` to Cursor CLI children through
  `policy.json` and `openclaw/provider-auth.compose.yml`.
