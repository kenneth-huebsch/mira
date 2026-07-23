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

Four local operational files are preserved separately:

- `docker-compose.yml` is copied into `openclaw/docker-compose.yml` in this
  blueprint and restored to the OpenClaw checkout by `scripts/restore-to-live.sh`.
- `entrypoint.sh` is copied into `openclaw/entrypoint.sh` in this blueprint and
  restored to the OpenClaw checkout by `scripts/restore-to-live.sh`.
- `Dockerfile.mira` defines the reproducible derived runtime image.
- `toolchain.lock.json` records reviewed tool versions and artifact checksums.

Other source patches under `src/` should be treated as temporary. Report them
before upgrading OpenClaw; clobber them only when Kenny explicitly approves it
or confirms upstream now owns the behavior.

## Current Local Source Changes

- `docker-compose.yml`
  - Builds/uses the derived image as node with all capabilities dropped,
    no-new-privileges, read-only image filesystems, and bounded tmpfs mounts.
  - Retains only the writable OpenClaw state/workspace mounts.
- `entrypoint.sh`
  - Validates exact tools and writable paths, then executes as node.
  - Performs no downloads, package installation, privilege changes, or chown.
- `Dockerfile.mira` and `toolchain.lock.json`
  - Install pinned Debian packages and checksum-verified Cursor/gog artifacts
    over the separately built OpenClaw image.

## Restore Decision

For now, this blueprint does not fork OpenClaw source. It preserves Mira's
container setup as the four managed files under `openclaw/`.

If a future restore from latest upstream OpenClaw does not behave correctly,
check whether the Docker Compose mount/env setup was restored and whether any
new source patch should be proposed upstream instead of kept locally.
