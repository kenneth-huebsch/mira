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

Two local source areas are worth preserving separately:

- `skills/quick-reminders/` is behavior-bearing and has been copied into `workspace/skills/quick-reminders/` in this blueprint.
- Container convenience changes in `docker-compose.yml` and `entrypoint.sh` may be useful on this host, but they are not part of Rumi's workspace behavior. Reapply manually or keep them in an OpenClaw fork if a fresh container needs the same gog/agent-browser setup.

The `pi-embedded-runner` changes look like upstream source fixes for suppressing visible pre-tool narration in silent/tool-use runs. They are not captured by workspace restore. If that behavior is required and not merged upstream, preserve it in an OpenClaw fork or patch branch.

## Current Local Source Changes

- `docker-compose.yml`
  - Runs the gateway container as root with `entrypoint.sh`.
  - Adds `GOG_KEYRING_BACKEND`, `GOG_KEYRING_PASSWORD`, and `XDG_CONFIG_HOME` env vars.
  - Mounts `entrypoint.sh` and `skills/quick-reminders`.
  - Exposes port `3500`.
- `entrypoint.sh`
  - Installs/links `gog` and `agent-browser`.
  - Prepares runtime dirs for `gogcli`, npm, and browser automation.
  - Drops back to the `node` user for the OpenClaw command.
- `src/agents/pi-embedded-runner/run.ts`
- `src/agents/pi-embedded-runner/run/attempt.ts`
- `src/agents/pi-embedded-runner/run/params.ts`
  - Threads `suppressToolUseVisibleOutput` through embedded runner params.
- `src/agents/pi-embedded-runner/run/attempt.spawn-workspace.context-engine.test.ts`
- `src/agents/pi-embedded-subscribe.subscribe-embedded-pi-session.suppresses-commentary-phase-output.test.ts`
  - Adds test coverage for that suppression behavior.

## Restore Decision

For now, this blueprint does not fork OpenClaw source. It documents the source changes and preserves `quick-reminders` as workspace behavior.

If a future restore from latest upstream OpenClaw does not behave correctly, check whether the `suppressToolUseVisibleOutput` patch or the container `entrypoint.sh` setup needs to be reapplied.
