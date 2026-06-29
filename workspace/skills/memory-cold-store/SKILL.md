---
name: memory-cold-store
description: Store and retrieve high-value durable Mira memories in an ignored git-notes cold store. Use for important decisions, lessons, durable corrections, cross-session handoffs, and project landmarks that should survive beyond daily notes.
---

# Memory Cold Store

Use this skill for durable, high-value memory that should be kept in Mira's
ignored git-notes cold store. Do not use it for raw transcripts, logs, email
bodies, credentials, tokens, browser/session state, or unreviewed private dumps.

The store lives at `~/.openclaw/memory/git-notes` unless
`MIRA_MEMORY_COLD_STORE_DIR` overrides it. The actual notes are runtime state and
must not be copied into the tracked blueprint.

## Commands

Store a durable memory:

```bash
python3 skills/memory-cold-store/memory_cold_store.py remember \
  "Use OpenRouter embeddings for Mira memory search." \
  --type decision \
  --topic memory \
  --importance high
```

Search memories:

```bash
python3 skills/memory-cold-store/memory_cold_store.py search "OpenRouter"
```

List or inspect:

```bash
python3 skills/memory-cold-store/memory_cold_store.py list
python3 skills/memory-cold-store/memory_cold_store.py get <memory-id-or-object>
python3 skills/memory-cold-store/memory_cold_store.py doctor
```

Export for human review:

```bash
python3 skills/memory-cold-store/memory_cold_store.py export
```

## Write Policy

Store only concise, durable notes:

- decisions Kenny made or approved,
- lessons from mistakes that should not repeat,
- durable corrections to Mira's behavior,
- cross-session handoffs with clear action boundaries,
- project landmarks that future sessions should recall.

If a memory changes future behavior, include the action boundary: when it
applies, when it expires, what unlocks action, and whether approval is required.
