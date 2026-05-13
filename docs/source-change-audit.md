# OpenClaw Source Change Audit

Audited source checkout: `/home/kenny/openclaw`

## Summary

The restore path should still start from latest upstream OpenClaw. Most behavior needed to recreate Rumi belongs in this blueprint repo under `workspace/`.

## Standing Source Boundary

Future Rumi coding work must not edit upstream OpenClaw source files under
`/home/kenny/openclaw/src/`. Keep the OpenClaw checkout pullable from upstream.

Use Rumi-owned behavior surfaces instead:

- `workspace/` prompts, docs, skills, helpers, and templates.
- `workspace/plugins/` for plugin-based runtime behavior when OpenClaw exposes
  the needed hook.
- Live cron/config changes through OpenClaw CLI commands, mirrored back into the
  blueprint when behavior-bearing.

If a behavior change appears to require an upstream source patch, stop and
document the limitation. Only use an OpenClaw fork or patch branch after Kenny
explicitly approves it.

Two local source areas are preserved separately:

- `skills/quick-reminders/` is behavior-bearing and has been copied into `workspace/skills/quick-reminders/` in this blueprint.
- `entrypoint.sh` is copied into `openclaw/entrypoint.sh` in this blueprint and
  restored to the OpenClaw checkout by `scripts/restore-to-live.sh`.
- Container convenience changes in `docker-compose.yml` are still host-local.
  Reapply manually or keep them in an OpenClaw fork if a fresh container needs
  the same volume/env setup.

The `pi-embedded-runner` changes look like upstream source fixes for suppressing visible pre-tool narration in silent/tool-use runs. They are not captured by workspace restore. If that behavior is required and not merged upstream, preserve it in an OpenClaw fork or patch branch.

## Current Local Source Changes

- `docker-compose.yml`
  - Runs the gateway container as root with `entrypoint.sh`.
  - Adds `GOG_KEYRING_BACKEND`, `GOG_KEYRING_PASSWORD`, and `XDG_CONFIG_HOME` env vars.
  - Mounts `entrypoint.sh` and `skills/quick-reminders`.
  - Exposes port `3500`.
- `entrypoint.sh`
  - Installs/links `gog`, QMD, and `agent-browser`.
  - Prepares runtime dirs for `gogcli`, npm, and browser automation.
  - Installs QMD into the mounted OpenClaw config dir (`runtime/qmd`) and links
    it into `.openclaw/bin` so the QMD binary survives container recreation.
  - Does not preserve QMD indexes, downloaded packages, or session exports in
    the blueprint; those remain runtime state.
  - Drops back to the `node` user for the OpenClaw command.
- `src/agents/pi-embedded-runner/run.ts`
- `src/agents/pi-embedded-runner/run/attempt.ts`
- `src/agents/pi-embedded-runner/run/params.ts`
  - Threads `suppressToolUseVisibleOutput` through embedded runner params.
- `src/agents/pi-embedded-runner/run/attempt.spawn-workspace.context-engine.test.ts`
- `src/agents/pi-embedded-subscribe.subscribe-embedded-pi-session.suppresses-commentary-phase-output.test.ts`
  - Adds test coverage for that suppression behavior.

## Restore Decision

For now, this blueprint does not fork OpenClaw source. It documents source
changes, preserves `quick-reminders` as workspace behavior, and preserves the
container entrypoint as `openclaw/entrypoint.sh`.

If a future restore from latest upstream OpenClaw does not behave correctly,
check whether the `suppressToolUseVisibleOutput` patch or the Docker Compose
mount/env setup needs to be reapplied.
