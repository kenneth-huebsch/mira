# OpenClaw Source Change Audit

Audited source checkout: `/home/kenny/mira/openclaw-src`

## Summary

The restore path should still start from latest upstream OpenClaw. Mira's
harness-routing behavior belongs in this blueprint repo under `workspace/`.

## Standing Source Boundary

Future Mira coding work must not edit upstream OpenClaw source files under
`/home/kenny/mira/openclaw-src/src/`. Keep the OpenClaw checkout pullable from upstream.

Use Mira-owned behavior surfaces instead:

- `workspace/` prompts, docs, skills, helpers, and templates.
- Live cron/config changes through OpenClaw CLI commands, mirrored back into the
  blueprint when behavior-bearing.

If a behavior change appears to require an upstream source patch, stop and
document the limitation. Only use an OpenClaw fork or patch branch after Kenny
explicitly approves it.

Two local source files are preserved separately:

- `docker-compose.yml` is copied into `openclaw/docker-compose.yml` in this
  blueprint and restored to the OpenClaw checkout by `scripts/restore-to-live.sh`.
- `entrypoint.sh` is copied into `openclaw/entrypoint.sh` in this blueprint and
  restored to the OpenClaw checkout by `scripts/restore-to-live.sh`.

Other source patches under `src/` should be treated as temporary. Report them
before upgrading OpenClaw; clobber them only when Kenny explicitly approves it
or confirms upstream now owns the behavior.

## Current Local Source Changes

- `docker-compose.yml`
  - Runs the gateway container as root with `entrypoint.sh`.
  - Adds `GOG_KEYRING_BACKEND`, `GOG_KEYRING_PASSWORD`, and `XDG_CONFIG_HOME` env vars.
  - Mounts `entrypoint.sh`.
  - Exposes port `3500`.
- `entrypoint.sh`
  - Installs/links `gog`, GitHub CLI, Cursor CLI, optional `mem0ai`, and basic runtime tools for harness routing and memory helpers.
  - Prepares runtime dirs for `gogcli`, npm, and `gh`.
  - Drops back to the `node` user for the OpenClaw command.

## Restore Decision

For now, this blueprint does not fork OpenClaw source. It preserves Mira's
container setup as `openclaw/docker-compose.yml` and `openclaw/entrypoint.sh`.

If a future restore from latest upstream OpenClaw does not behave correctly,
check whether the Docker Compose mount/env setup was restored and whether any
new source patch should be proposed upstream instead of kept locally.
