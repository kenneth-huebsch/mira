---
cron_id: memory_consolidation
dynamic:
  - consolidation_medium_memory
  - consolidation_long_memory
  - proactive_engagement_priorities
---

# MEMORY HYGIENE CONSOLIDATION

You are running scheduled hygiene for memory and operational sidecars.

Follow standing execution rules from `AGENTS.md` (silent execution, output discipline).

## TASK

Run this exact command once with `exec`:

```bash
python3 cron/memory_consolidation.py
```

The helper owns all deterministic hygiene: parsing JSONL, dropping expired
records, deduping exact memory summaries, aging engagement priorities,
compacting email triage state, and safely writing or truncating files.

If the helper prints `NO_REPLY`, return exactly `NO_REPLY`.
If the helper exits non-zero or prints anything else, return a short visible
failure line: `Memory consolidation failed.`

## OUTPUT FORMAT

Return exactly one token: `NO_REPLY`.

- Do not output counts, summaries, plans, status text, or progress narration.
- Do not output planning preambles such as "Now I'll consolidate", "Actions:", "I'll read", "Let me check", or any bullet list of intended changes.
- Do not surface tool warnings, error messages, or stack traces.
- The first and only user-visible text must be exactly: `NO_REPLY`.
