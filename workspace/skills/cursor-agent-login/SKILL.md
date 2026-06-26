---
name: cursor-agent-login
description: Authenticate or verify Cursor CLI inside Mira's OpenClaw gateway container. Use when coding-harness preflight reports Cursor auth missing, when `agent status` says not logged in, or when Kenny asks to log Mira into Cursor.
---

# Cursor Agent Login

Use this skill to authenticate Cursor CLI for Mira's coding harness runtime.
This is specific to Mira's gateway container.

## Check Status

Run from the host:

```bash
docker exec --user node openclaw-mira-openclaw-gateway-1 sh -lc 'agent status'
```

If logged in, verify the harness preflight:

```bash
docker exec --user node openclaw-mira-openclaw-gateway-1 \
  python3 /home/node/.openclaw/workspace/capabilities/coding_harness/coding_harness.py check-config
```

## Start Login

Start the browser-based login flow without trying to open a browser inside the
container:

```bash
docker exec --user node openclaw-mira-openclaw-gateway-1 sh -lc 'NO_OPEN_BROWSER=1 agent login'
```

The command prints a Cursor login URL and waits. Send the URL to Kenny and ask
him to complete it in his browser.

After the command exits, rerun `agent status` and the coding-harness preflight.

## Notes

- Do not paste Cursor tokens or auth files into chat.
- Do not commit Cursor auth state. It lives under Mira's ignored `.openclaw`
  runtime.
- If the browser flow is not practical, Kenny can configure `CURSOR_API_KEY` as
  an ignored runtime secret and restart Mira.
