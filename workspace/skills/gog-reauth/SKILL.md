---
name: gog-reauth
description: Re-authorize a Gmail OAuth token for mira.agentops@gmail.com when the token is expired or revoked. Use when inbox triage fails with an auth error, or when Kenny asks to re-run the Gmail OAuth flow.
---

# Gmail OAuth Reauthorization

Use this skill when `gog` Gmail commands fail with auth/token errors, or when
Kenny asks to reauthenticate the Gmail account.

## Flow

### Step 1 — Generate the auth URL

```bash
gog auth add mira.agentops@gmail.com --remote --step 1 --services gmail --force-consent --no-input 2>&1
```

This prints an `auth_url`. Send it to Kenny and ask him to:
1. Open the URL in his browser
2. Sign in as `mira.agentops@gmail.com`
3. Approve the permissions
4. Copy the full redirect URL from the browser address bar (it will be a `127.0.0.1` URL that fails to load — that's expected) and paste it back

### Step 2 — Exchange the code

Once Kenny pastes the redirect URL, run:

```bash
gog auth add mira.agentops@gmail.com --remote --step 2 --services gmail --force-consent --no-input --auth-url "<paste redirect URL here>" 2>&1
```

Expected success output:
```
email   mira.agentops@gmail.com
services        gmail
client  default
```

### Step 3 — Verify

```bash
gog gmail messages search "in:inbox" --max 1 --account mira.agentops@gmail.com --json 2>&1
```

A valid JSON response with a message (or empty messages array) confirms auth is working. An error confirms it failed.

## Notes

- The redirect URL will start with `http://127.0.0.1:45713/oauth2/callback?...` — the port may vary but the pattern is the same.
- If step 2 fails with a stale/invalid code, start over from step 1 (codes expire quickly).
- After successful reauth, inbox triage will resume at its next scheduled run automatically.
