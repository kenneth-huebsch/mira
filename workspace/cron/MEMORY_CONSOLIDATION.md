---
cron_id: memory_consolidation
dynamic:
  - consolidation_medium_memory
  - consolidation_long_memory
  - proactive_engagement_priorities
---

# MEDIUM MEMORY CONSOLIDATION

You are running scheduled consolidation for medium and long memory.

Follow standing execution rules from `AGENTS.md` (silent execution, output discipline).

## INPUT

Read:
- `memory/medium_memory.jsonl`
- `memory/long_memory.jsonl`
- `memory/engagement_priorities.jsonl`
- `memory/email_triage_state.jsonl` (may not exist yet — skip the operational-state step if missing)

## TASK

### Memory

1. Parse each JSONL line as one memory record.
2. For expired medium-memory entries (`expires_at` before today), decide:
   - Promote to `memory/long_memory.jsonl` if the fact should be remembered long term.
   - Delete if it is no longer useful.
3. Promote memories that represent durable commitments, life context, or major ongoing plans.
4. Examples that usually should be promoted:
   - "my wife is pregnant"
   - "we are going to portugal this summer"
   - "I made a new years resolution to work out 3 times per week"
5. Merge duplicates and near-duplicates across both files by keeping the clearest summary and freshest date range.
6. Compress repetitive entries into one concise line when they describe the same ongoing context.
7. If a medium or long memory clearly suggests a good future proactive outreach topic, optionally append one record to `memory/engagement_priorities.jsonl`.
8. Engagement-priority records must use this minimal JSONL schema:
   - `topic`
   - `kind` (`accountability|relationship|general`)
   - `prompt`
   - `created_at`
   - `expires_at` — default to `created_at + 30 days`. Do not use `9999-12-31` for new priorities.
9. Skip appending when an existing engagement-priority record already covers the same `topic`.
10. Rewrite `memory/medium_memory.jsonl` and `memory/long_memory.jsonl` in valid JSONL format.

### Engagement priorities aging

11. Parse each JSONL line in `memory/engagement_priorities.jsonl`.
12. Drop any record whose `expires_at` is before today.
13. Drop any record whose `created_at` is more than 30 days before today, regardless of `expires_at` (this clears legacy `9999-12-31` rows so priorities turn over).
14. Rewrite `memory/engagement_priorities.jsonl` in valid JSONL, preserving the order of remaining records. If all records are dropped, leave the file empty (zero bytes) rather than deleting it.

### Operational state

15. If `memory/email_triage_state.jsonl` exists:
    - Parse each JSONL line as one email-triage record.
    - Drop every record whose `run_at` is more than 7 days before now (UTC).
    - Rewrite the file in valid JSONL, preserving the order of the remaining records.
    - If all records are dropped, leave the file empty (zero bytes) rather than deleting it.
    - Do not touch Gmail. This step only compacts the local sidecar.

## RULES

- Keep the files valid JSONL (one JSON object per line).
- Preserve fields: `summary`, `created_at`, `expires_at` for memory records.
- Do not invent long-term identity traits.
- Drop trivial small talk and stale low-value facts.
- Keep memory selective; fewer high-signal entries are better than many weak entries.
- When promoting medium -> long, keep `summary` concise and set `expires_at` to a valid date or `9999-12-31` if there is no expiration.
- Only append an engagement priority when it would genuinely help future proactive outreach.
- For `memory/email_triage_state.jsonl`, preserve every field of each retained record exactly as written. Only drop whole lines based on age.

## EMPTY FILE HANDLING

Some Write tools refuse to write 0 or 1 character of content and will return a warning like `Write: to <path> (N chars) failed`. Avoid that path when a file should become empty.

- If, after dropping records, a file should become empty and it is already 0 bytes or whitespace-only, leave it unchanged and treat that file as successfully consolidated.
- If a non-empty file must be cleared, do not use the Write tool with empty or 1-character content. Use a shell truncation command such as `: > memory/<name>.jsonl`, then verify with `wc -c`.
- Do not retry empty writes. The goal is the final file state, not a successful Write-tool call.
- Do not surface the Write tool warning in the final output. The OUTPUT FORMAT below still applies.

## OUTPUT FORMAT

Return exactly one token: `NO_REPLY`.

- Do not output counts, summaries, plans, status text, or progress narration.
- Do not output planning preambles such as "Now I'll consolidate", "Actions:", "I'll read", "Let me check", or any bullet list of intended changes.
- Do not surface tool warnings, error messages, or stack traces.
- The first and only user-visible text must be exactly: `NO_REPLY`.
