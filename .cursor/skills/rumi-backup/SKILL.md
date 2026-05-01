---
name: rumi-backup
description: Sync, review, commit, push, or restore the Rumi OpenClaw blueprint. Use after changing Rumi behavior or when backing up/restoring the rumi repo. Protects credentials while preserving friend-safe persona, cron, skill, plugin, and asset files.
---

# Rumi Backup

Read and follow `docs/agent-playbooks/rumi-backup.md`.

Key rule: this repo may include friend-safe personalized behavior, IDs, cron
prompts, and persona assets, but must never include credentials, tokens, auth
profiles, sessions, logs, or accumulated private memory history.

Before committing or pushing, run the scan documented in the playbook and inspect
the diff.
