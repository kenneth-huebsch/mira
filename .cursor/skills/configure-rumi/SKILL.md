---
name: configure-rumi
description: Configure Rumi's OpenClaw behavior, persona, identity, appearance, cron prompts, workspace skills, plugins, memory policy, or assets. Use when changing how Rumi acts, speaks, remembers, appears, or runs scheduled behavior.
---

# Configure Rumi

Read and follow `docs/agent-playbooks/configure-rumi.md`.

Key rule: durable behavior belongs in Rumi's workspace docs, cron prompts, skills,
plugins, and assets. Do not rely only on `memory/*.jsonl` for canonical behavior
policy.

Memory-system changes must keep these files in sync:

- `cron/NIGHTLY_SESSION_REFLECTION.md` for tomorrow-useful interactive context and durable facts Kenny explicitly revealed.
- `cron/MEMORY_CONSOLIDATION.md` for hygiene only.
- `AGENTS.md` for memory ownership policy.
- `docs/cron-dependencies.md` and `docs/agent-playbooks/configure-rumi.md`.
- `scripts/sync-from-live.sh` and `scripts/restore-to-live.sh` when adding prompts or helper scripts.

After changing live behavior, run:

```bash
cd /home/kenny/rumi
./scripts/sync-from-live.sh
git diff
```

Then use the `rumi-backup` skill before committing or pushing.
