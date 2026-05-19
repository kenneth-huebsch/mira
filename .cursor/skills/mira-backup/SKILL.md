---
name: mira-backup
description: Sync, review, commit, push, or restore the Mira OpenClaw blueprint. Use after changing Mira behavior or when backing up/restoring the mira repo. Protects credentials while preserving friend-safe persona, cron, skill, plugin, and asset files.
---

# Mira Backup

Read and follow `docs/agent-playbooks/mira-backup.md`.

Key rule: this repo may include friend-safe personalized behavior, IDs, cron
prompts, and persona assets, but must never include credentials, tokens, auth
profiles, sessions, logs, accumulated private memory history, QMD indexes,
downloaded QMD runtime packages, or QMD session exports.

Before committing or pushing, run the scan documented in the playbook and inspect
the diff.
