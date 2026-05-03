---
cron_id: nightly_session_reflection
dynamic:
  - consolidation_medium_memory
  - consolidation_long_memory
  - proactive_engagement_priorities
---

# NIGHTLY SESSION REFLECTION

You are running scheduled reflection over Kenny's interactive session.

Follow standing execution rules from `AGENTS.md` (silent execution, output discipline).

## Purpose

Preserve the small amount of conversational context that would make Rumi feel
more human, continuous, and attentive in tomorrow's interactive session.

This is not a transcript summary job. It is selective memory extraction.

## Input

Use the helper:

```bash
python3 cron/nightly_session_reflection.py collect --date yesterday --out /tmp/nightly_session_reflection_context.json
```

The helper resolves Kenny's interactive Telegram session, filters the previous
Eastern Time day, and includes existing memory so you can avoid duplicates.

## Task

1. Run the `collect` command above.
2. If collection fails because there is no session, or if the collected JSON has
   `"low_signal": true`, write an empty decision JSON and continue to `apply`;
   do not invent memories.
3. Review the collected context.
4. Create `/tmp/nightly_session_reflection_decision.json` with exactly this JSON shape:

```json
{
  "medium_memory": [],
  "long_memory": [],
  "engagement_priorities": [],
  "reset_recommended": false,
  "notes": []
}
```

5. Run:

```bash
python3 cron/nightly_session_reflection.py apply --date yesterday --json-file /tmp/nightly_session_reflection_decision.json
```

6. Run:

```bash
python3 cron/nightly_session_reflection.py reset
```

Reset is disabled by default until the reset command is explicitly configured,
so this is safe to run. Do not try to reset by hand.

## What To Store

Write `medium_memory` entries for next-day conversational continuity:

- recent excitement, worry, frustration, uncertainty, or emotional context a human friend would remember
- active topics Kenny is likely to bring up tomorrow
- unresolved asks, experiments, plans, or follow-ups
- temporary preferences or working context
- tool lessons that directly affect future interaction quality

Use concise summaries with natural expirations of 3 to 30 days. Prefer 7 to 14
days for ordinary conversational context.

Write `long_memory` only for durable facts Kenny actually revealed:

- family facts
- lasting interests
- recurring preferences
- durable plans or commitments
- stable life context

Do not write durable behavior policy to `long_memory`. Durable behavior,
persona, and shared preferences belong in `USER.md`, `AGENTS.md`, `TOOLS.md`,
or other workspace docs.

Optionally write `engagement_priorities` when the day clearly suggests a good
future proactive check-in topic. Keep these sparse.

## What To Skip

- Generic daily summaries.
- Jokes, filler, and one-off banter.
- Facts already represented in medium or long memory.
- Transcript dumps or sensitive message excerpts.
- Inferred personality traits.
- Tool chatter unless it changes how Rumi should act later.

## Decision Quality

Good:

```json
{
  "medium_memory": [
    {
      "summary": "Kenny is excited and nervous about the Sixers Game 7 against Boston.",
      "expires_in_days": 7
    },
    {
      "summary": "Kenny wants Rumi to use agent-browser before web_fetch for eBay, ESPN, and similar live sites.",
      "expires_in_days": 30
    }
  ],
  "long_memory": [],
  "engagement_priorities": [
    {
      "topic": "sixers_game_7",
      "kind": "relationship",
      "prompt": "Ask how the Sixers Game 7 went and match Kenny's energy.",
      "expires_in_days": 7
    }
  ],
  "reset_recommended": true,
  "notes": []
}
```

Bad:

```json
{
  "medium_memory": [
    {
      "summary": "Kenny and Rumi chatted yesterday.",
      "expires_in_days": 30
    }
  ],
  "long_memory": [
    {
      "summary": "Kenny is an anxious person.",
      "expires_at": "9999-12-31"
    }
  ],
  "engagement_priorities": [],
  "reset_recommended": true,
  "notes": []
}
```

## Rules

- Keep memory selective. Zero new records is valid.
- Preserve valid JSON. The helper validates and dedupes, but you should still
  propose clean records.
- Do not use web search, browser tools, Gmail, Todoist, calendar, or network access.
- Do not modify `USER.md` from this cron.
- Do not attempt session reset except through `nightly_session_reflection.py reset`.
- If apply fails, return a short visible failure line.

## Output Format

On success, return exactly one token: `NO_REPLY`.

- Do not output counts, summaries, plans, status text, or progress narration.
- Do not mention reading files, prompts, tools, or internal process.
- The first and only user-visible text must be exactly: `NO_REPLY`.
