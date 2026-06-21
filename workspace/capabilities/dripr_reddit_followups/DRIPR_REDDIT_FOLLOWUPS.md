---
capability_id: dripr_reddit_followups
---

# Dripr Reddit Follow-Ups

This capability summarizes Reddit posts from Kenny's Airtable scrape that still
need a marketing follow-up. The helper does all Airtable access and returns
compact JSON. Mira should only use the helper payload and this behavior file for
the final message.

## Check Contract

Run:

```bash
python3 capabilities/dripr_reddit_followups/dripr_reddit_followups.py review
```

If the helper prints exactly `NO_REPLY`, return exactly:

```text
NO_REPLY
```

If the helper prints JSON with `"status":"SETUP_REQUIRED"`, return:

```text
Mira Dripr Reddit follow-up check needs setup before it can run.
```

If the helper prints JSON with `"status":"ERROR"`, return:

```text
Mira Dripr Reddit follow-up check failed.
```

If the helper prints JSON with `"status":"OK"`, write a short, human-readable
summary for Kenny.

## Message Quality

Use the helper payload as the source of truth. Start with one short header line,
then one numbered block per follow-up.

Example shape:

```text
Dripr Reddit follow-ups (2):

1.
Why relevant: <why_relevant>
URL: <url>

2.
Why relevant: <why_relevant>
URL: <url>
```

Formatting rules:

- Use the exact `why_relevant` and `url` values from the helper JSON.
- Keep the tone practical and scannable for quick marketing follow-up.
- If there is only one row, still use the header plus one numbered block.
- If `truncated` is true, add one final line: `There may be more follow-ups not shown.`
- Do not include raw JSON, Airtable record IDs, credentials, PATs, base IDs, or
  tool output.
- Do not suggest posting replies automatically. Kenny decides whether and how to
  respond on Reddit.

Avoid:

- Inventing post titles, subreddits, or relevance details not present in the helper
  JSON.
- Adding greetings, long commentary, or action plans unless the data clearly
  needs Kenny's attention.
- Creating tasks, reminders, files, notes, emails, calendar events, or memory.

## Rules

- Do not query Airtable directly. The helper is the only allowed Airtable access
  for this cron.
- Do not write files or memory.
- Do not use web search, browser tools, Gmail, Todoist, calendar, curl, or any
  network request other than the required helper behavior.
- Do not call Telegram or delivery tools. Return final visible text and let the
  scheduler deliver it.
