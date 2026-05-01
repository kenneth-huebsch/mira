---
name: configure-rumi
description: Configure Rumi's OpenClaw behavior, persona, identity, appearance, cron prompts, workspace skills, plugins, memory policy, or assets. Use when changing how Rumi acts, speaks, remembers, appears, or runs scheduled behavior.
---

# Configure Rumi

Read and follow `docs/agent-playbooks/configure-rumi.md`.

Key rule: durable behavior belongs in Rumi's workspace docs, cron prompts, skills,
plugins, and assets. Do not rely only on `memory/*.jsonl` for canonical behavior
policy.

After changing live behavior, run:

```bash
cd /home/kenny/rumi
./scripts/sync-from-live.sh
git diff
```

Then use the `rumi-backup` skill before committing or pushing.
