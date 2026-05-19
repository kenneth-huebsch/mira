---
name: configure-mira
description: Configure Mira's OpenClaw behavior, persona, identity, appearance, workspace skills, plugins, memory policy, or assets. Use when changing how Mira acts, speaks, remembers, appears, or runs scheduled behavior.
---

# Configure Mira

Read and follow `docs/agent-playbooks/configure-mira.md`.

Key rule: durable behavior belongs in Mira's workspace docs, skills, plugins,
and assets. Do not rely only on `memory/*.jsonl` for canonical behavior policy.

Memory-system changes must keep these files in sync:

- `AGENTS.md` for memory ownership policy.
- `docs/cron-dependencies.md` and `docs/agent-playbooks/configure-mira.md`.
- `scripts/sync-from-live.sh` and `scripts/restore-to-live.sh` when adding future prompts or helper scripts.
- `templates/openclaw.friend-safe.example.json`, `workspace/TOOLS.md`, and
  restore docs when changing QMD recall behavior. QMD is read-only recall over
  selected markdown docs, not the curated JSONL source of truth; do not backfill
  historical JSONL memory or enable session indexing unless Kenny asks.

After changing live behavior, run:

```bash
cd /home/kenny/mira
./scripts/sync-from-live.sh
git diff
```

Then use the `mira-backup` skill before committing or pushing.
