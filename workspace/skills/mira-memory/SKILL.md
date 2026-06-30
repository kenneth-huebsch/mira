---
name: mira-memory
description: Maintain Mira's local-first memory stack: SESSION-STATE.md write-ahead state, MEMORY.md and daily notes, OpenClaw memorySearch, active-memory, LanceDB vectors, and git-notes cold storage. Use when checking memory health, deciding where to store durable context, or debugging recall.
---

# Mira Memory

Mira uses a local-first adaptation of the elite long-term memory pattern. The
supported layers are:

- `SESSION-STATE.md` for hot working state that survives compaction.
- `MEMORY.md` and `memory/YYYY-MM-DD.md` for curated local archives.
- OpenClaw `memorySearch`, `active-memory`, and `memory-lancedb` for bounded
  semantic recall in direct sessions.
- `skills/memory-cold-store/` for high-value git-notes cold storage.

Mira intentionally does not use external cloud memory by default. Do not upload
raw transcripts, email, repo contents, logs, credentials, tokens, sessions, or
browser state to third-party memory services.

## Write-Ahead Discipline

When Kenny states a durable preference, decision, correction, deadline, active
handoff, or important project fact, save the relevant note before relying on it
in future turns. Use the narrowest durable layer that fits:

- Active task state: update `SESSION-STATE.md`.
- Curated durable summary: update `MEMORY.md`.
- Detailed working note: update `memory/YYYY-MM-DD.md`.
- High-value durable decision, lesson, correction, handoff, or landmark: use
  `skills/memory-cold-store/memory_cold_store.py`.

## Health Check

Run from Mira's workspace inside the OpenClaw runtime:

```bash
python3 skills/mira-memory/mira_memory_check.py
```

The check verifies required memory files, OpenClaw memory config, memory tools,
and the git-notes cold store.
