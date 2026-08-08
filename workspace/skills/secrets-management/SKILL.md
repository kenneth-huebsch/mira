---
name: secrets-management
description: "Manage secrets for Mira. Use when adding, updating, rotating, auditing, or wiring credentials and API keys."
metadata:
  openclaw:
    emoji: "🔐"
---

# Secrets Management

## Core rule

Use the consumer's native credential mechanism. Do not force every secret into
one file, and do not bypass OpenClaw's host-environment security policy by
materializing every blocked variable into an agent-readable file.

Never put secret values in tracked files, memory, chat, command output, shell
startup files, logs, or repository-local `.env` files.

## Choose the storage shape

| Secret type | Storage |
|---|---|
| Environment-native API key or password | `/home/kenny/mira/.openclaw/.env`, mode `600` |
| Cursor CLI API key | `/home/kenny/mira/.openclaw/.env` as `CURSOR_API_KEY`, mode `600` |
| AWS access key | `/home/kenny/mira/.openclaw/aws/credentials`, mode `600` |
| AWS profile and role routing | `/home/kenny/mira/.openclaw/aws/config`, mode `600` |
| OpenClaw OAuth/device credential | OpenClaw's native ignored runtime store |
| GitHub credential | `gh`'s native ignored credential store |
| Gmail OAuth credential | `gog`'s native ignored credential store |
| Private key, certificate, or multiline credential | Dedicated ignored file, mode `600` |

The containing directory for file-shaped credentials must be mode `700`.
Tracked templates may contain variable names and profile shapes only, never
credential values.

## Environment-style secrets

The ignored per-instance `.env` remains the source for consumers that actually
expect environment variables, including provider, Telegram, n8n, WordPress, and
Cursor CLI credentials.

Rules:

1. Use one exact `KEY=value` entry per variable.
2. Keep the file mode `600`.
3. Never display the file, even with a redaction pipeline. Audit names and
   syntax with a parser that never emits values.
4. Update Compose mappings when a container process needs a new variable.
5. Restart through `/home/kenny/mira/scripts/stop-openclaw.sh` and
   `start-openclaw.sh`, then run a service-specific read-only check.
6. For default Telegram auth, use `TELEGRAM_BOT_TOKEN` and omit `botToken`,
   `tokenFile`, and `token` from `channels.telegram`.

## OpenClaw environment filtering

OpenClaw filters security-sensitive environment names during service dotenv
loading, host exec inheritance, or both. The exact lists are versioned framework
behavior; inspect the current source before diagnosing a missing variable.

Do not generalize from one blocked key to all provider keys. In particular:

- AWS access-key variables are intentionally unavailable to Mira's exec calls.
- `AWS_REGION` and `AWS_DEFAULT_REGION` can pass normally.
- Trusted inherited `AWS_PROFILE`, `AWS_CONFIG_FILE`, and
  `AWS_SHARED_CREDENTIALS_FILE` select AWS's native credential chain.

When a variable is blocked, first use the consumer's documented native store,
credential file, OAuth flow, role, or broker. Creating a conversion script that
copies a blocked secret into another readable file requires an explicit,
service-specific design review.

## AWS profiles

AWS uses one persistent credential file and one non-secret profile file:

- Credentials: `~/.openclaw/aws/credentials`
- Config: `~/.openclaw/aws/config`
- Default profile: `coding-agent`
- Publishing profile: `locks-publish`

The `coding-agent` profile contains the dedicated IAM user's bootstrap key. Its
durable permissions are read-only Locks access plus `sts:AssumeRole` for exact
Locks and CDK roles. CDK automatically assumes the role declared by each stack
or the appropriate bootstrap role.

The `locks-publish` profile assumes `LocksAppPublishRole` for static-site
publishing and data seeding. It uses short-lived STS credentials.

Use:

```bash
# Read-only checks and CDK foundation/application deployment
AWS_PROFILE=coding-agent aws sts get-caller-identity
AWS_PROFILE=coding-agent npm run deploy:oidc
AWS_PROFILE=coding-agent npm run deploy:infrastructure

# Static publishing and seeding
AWS_PROFILE=locks-publish aws sts get-caller-identity
AWS_PROFILE=locks-publish npm run deploy:app
AWS_PROFILE=locks-publish npm run seed
```

Before any AWS mutation, verify the account and role, inspect the targeted CDK
diff where applicable, and obtain fresh explicit approval. A conversational
approval gate is not an IAM boundary.

## Add or rotate a secret

1. Identify the consumer and its native credential mechanism.
2. Edit the ignored host-side store without printing the old or new value.
3. Preserve owner-only permissions using an atomic same-directory replacement.
4. Update only friend-safe wiring, templates, and instructions.
5. Restart or refresh the affected consumer.
6. Verify identity or service access without displaying the credential.
7. Revoke the old credential after the new path is confirmed.

For AWS key rotation, update only the `coding-agent` entry in the credentials
file. Do not copy the key into `.env`. Verify both `coding-agent` and
`locks-publish` with `aws sts get-caller-identity`.

## Audit

An audit may report:

- expected variable or profile names;
- file existence, owner, and numeric mode;
- whether duplicate names or malformed entries exist;
- read-only identity-check results.

It must never report values, prefixes, hashes of values, authorization headers,
or full credential-file contents.
