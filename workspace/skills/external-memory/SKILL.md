---
name: external-memory
description: Explicitly store or search approved curated memories in Mem0. Use only when Kenny asks to use cloud memory or when backing up durable summaries; never upload raw transcripts, emails, logs, credentials, tokens, or session state.
---

# External Memory

Use this skill for explicit, approved external memory calls to Mem0. Dry-run
first unless Kenny has already approved the exact live write/search.

Secrets must come from ignored runtime env files, not tracked docs or memory:

- `MEM0_API_KEY`

## Dry Runs

Mem0 add:

```bash
python3 skills/external-memory/external_memory.py add \
  "Kenny prefers direct, practical answers." \
  --category preference
```

Mem0 search:

```bash
python3 skills/external-memory/external_memory.py search \
  "communication preferences"
```

## Live Calls

Add `--live` only after confirming the content is safe for the target service:

```bash
python3 skills/external-memory/external_memory.py --live add "approved durable summary"
python3 skills/external-memory/external_memory.py --live search "approved query"
```

## Privacy Rules

Never send:

- credentials, tokens, OAuth/device state, or auth headers,
- raw emails or mailbox dumps,
- raw transcripts, logs, browser state, sessions, or crash dumps,
- unreviewed private memory exports,
- repo contents unless Kenny explicitly approved that exact upload.

Prefer concise durable summaries. Include action boundaries when the memory
affects future behavior.
