---
name: configure-mira
description: Configure Mira's OpenClaw harness-routing behavior, persona, identity, Gmail conventions, Telegram control surface, workspace skills, memory policy, or restore shape.
---

# Configure Mira

Read and follow `docs/agent-playbooks/configure-mira.md`.

Key rule: durable behavior belongs in Mira's workspace docs, skills, scripts,
and assets. Mira has local-first workspace memory plus memory helper skills, but
accumulated memory contents and runtime indexes stay out of the blueprint. Mira
has no cron jobs enabled by default.

Behavior changes must keep these files in sync:

- `AGENTS.md` for memory ownership policy.
- `docs/cron-dependencies.md` and `docs/agent-playbooks/configure-mira.md` when
  adding scheduled behavior or memory helper dependencies.
- `scripts/workspace-manifest.txt` when adding future prompts, skills, or helper scripts.
- `templates/openclaw.friend-safe.example.json`, `workspace/TOOLS.md`, and restore docs when changing runtime tool access.

After changing live behavior, run:

```bash
cd /home/kenny/mira
./scripts/sync-from-live.sh
git diff
```

Then use the `mira-backup` skill before committing or pushing.
