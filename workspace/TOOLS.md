# TOOLS.md

Canonical reference for tool-specific conventions. This file is auto-injected
into every agent run, so cron prompts and `AGENTS.md` should reference it
rather than restating account names, calendar IDs, or command flags.

If a convention here drifts from reality (an account changes, a calendar id
fails to resolve, a command flag is renamed), fix it HERE — once — and every
caller picks it up automatically.

---

## `gog` (Google Workspace CLI)

`gog` is OpenClaw's Google Workspace skill. Always load and follow the bundled
`gog` skill before issuing commands; the notes below cover only the
Kenny-specific conventions.

### Account

There is exactly one `gog` auth account: **`rumi.openclaw@gmail.com`**.
Both Kenny's personal and work calendars are shared into this account; there
is no separate "work" auth. Prefer one of the following on every call:

- Set `GOG_ACCOUNT=rumi.openclaw@gmail.com` in the environment, or
- Pass `--account rumi.openclaw@gmail.com` explicitly.

### Calendars (canonical IDs)

Kenny has TWO Google calendars. Whenever any user (Kenny or a guest) asks
about Kenny's schedule, calendar, availability, what's on today/this week, or
anything time-bound, query BOTH and merge the results. Querying only one is a
defect.

- **Kennys Personal Calendar** — id: `kenneth.huebsch@gmail.com`
- **Kennys Work Calendar** — id: `o9k4ud8ocv356bk0e65kb59s0mjcisaq@import.calendar.google.com` (imported via iCal; `summaryOverride` is `Kennys Work Calendar`)
- **Copied Birthdays** — resolve at runtime via `gog calendar calendars --json` (the id rotates and is not stable enough to hardcode). Pick the entry whose `summary` or `summaryOverride` contains "Copied Birthdays" (case-insensitive).

### Calendar usage

```bash
FROM="$(TZ=America/New_York date -Iseconds -d 'today 00:00')"
TO="$(TZ=America/New_York date -Iseconds -d 'today 23:59:59')"
gog calendar events kenneth.huebsch@gmail.com --from "$FROM" --to "$TO" --json
gog calendar events 'o9k4ud8ocv356bk0e65kb59s0mjcisaq@import.calendar.google.com' --from "$FROM" --to "$TO" --json
```

Notes:

- The list-calendars subcommand is `gog calendar calendars --json`. There is **no** `gog calendar list` subcommand — do not use it.
- `gog calendar events` REQUIRES a calendar id as its first positional argument; calling it without one is wrong.
- Include all-day events and timed events. Deduplicate before summarizing.
- When summarizing, label events by which calendar they came from when it adds clarity (e.g. "Daniel <> Kenny (work)").
- **Failure handling.** Retry once on failure. If still failing, mark that specific calendar as unavailable in the output. Never claim "no events" when retrieval failed for either calendar. Only say "no events scheduled" when BOTH calendars were successfully queried and BOTH returned zero.
- **ID resolution fallback.** If either id above stops resolving, fall back to `gog calendar calendars --json` and re-resolve by `summaryOverride` matching `Personal` / `Work` (case-insensitive).

### Gmail usage

All Gmail operations run against `rumi.openclaw@gmail.com`. Common patterns:

```bash
# Search unread mail addressed directly to Rumi (not auto-forwarded)
gog gmail messages search "in:inbox is:unread deliveredto:rumi.openclaw@gmail.com" --max 50 --account rumi.openclaw@gmail.com --json

# Search auto-forwarded personal mail. The mailbox delivery target is Rumi;
# Kenny's original address is preserved in forwarding headers and usually To.
gog gmail messages search "in:inbox is:unread deliveredto:rumi.openclaw@gmail.com (to:kenny@dripr.ai OR to:kenny@0trust.email)" --max 100 --account rumi.openclaw@gmail.com --json

# Fetch full message
gog gmail get <messageId> --account rumi.openclaw@gmail.com --json

# Mark read (remove UNREAD label)
gog gmail messages modify <messageId> --remove UNREAD --account rumi.openclaw@gmail.com

# List existing drafts
gog gmail drafts list --account rumi.openclaw@gmail.com

# Create a draft (use --body-file - <<EOF for multi-line bodies)
gog gmail drafts create \
  --to <sender> \
  --subject "Re: <original subject>" \
  --reply-to-message-id <messageId> \
  --account rumi.openclaw@gmail.com \
  --body-file - <<'EOF'
<draft body>
EOF

# Send a previously-created draft (only after explicit Kenny confirmation)
gog gmail drafts send <draft_id> --account rumi.openclaw@gmail.com
```

The Gmail search operator is `deliveredto:` (lowercase, no hyphen); the raw
email header is `Delivered-To`. For this mailbox, forwarded mail is delivered
to `rumi.openclaw@gmail.com`; Kenny's original address is preserved in
`X-Pm-Forwarded-From`, `X-Original-To`, and/or `To`. For forwarded-mail
classification, prefer `X-Pm-Forwarded-From` or `X-Original-To` when present,
then fall back to `To`.

---

## Todoist

Todoist is wired in as an MCP server (Pattern A — remote HTTP endpoint). The
agent calls it via the standard MCP tool surface; no local CLI.

Project conventions:

- **Kennys Personal Tasks** — Kenny's personal todo project.
- **Kennys Work Todo List** — Kenny's work todo project.

If project names ever differ slightly, resolve by closest name match
(`Personal Tasks`, `Work Tasks`).

When generating Kenny's daily brief, include tasks due today, high priority
(`P1` / `P2`), and important upcoming tasks from BOTH projects.

---

## OpenClaw Crons

Use OpenClaw crons for recurring scheduled agent work. For one-shot simple
reminders under 48 hours, prefer the `quick-reminders` skill. For natural
short-lived follow-ups, prefer the engagement follow-up helper below.

When creating or editing an LLM-backed cron:

- Use the OpenClaw cron CLI rather than editing cron JSON files directly.
- Never set `payload.model` to `default`. In cron payloads, `default` is treated
  as a literal OpenRouter model id and fails as `openrouter/default`.
- For ordinary cron/tool workflows, set `payload.model` to
  `openrouter/xiaomi/mimo-v2-flash` and `payload.thinking` to `off`.
- For proactive relationship-building engagement, use
  `openrouter/deepseek/deepseek-v3.2` and `payload.thinking` to `off`.
- Use Eastern time (`America/New_York`) for user-facing schedules unless Kenny
  explicitly asks otherwise.
- For `delivery.mode: announce` crons, the payload should return the message as
  final visible text. Do not tell the model to send Telegram itself.
- If a cron should be silent when there is nothing useful, make the payload say
  `return exactly NO_REPLY`; do not say only "do nothing".
- After creating or editing a cron, verify it with `openclaw cron list --json`
  or `openclaw cron runs <job-id>` before telling Kenny it is done.

Container-safe pattern:

```bash
docker exec openclaw-openclaw-gateway-1 openclaw cron edit <job-id> \
  --model openrouter/xiaomi/mimo-v2-flash \
  --thinking off
```

---

## Engagement Follow-Ups

Use engagement follow-ups when Kenny mentions a short-lived situation and a
later message would feel natural: workouts, interviews, cooking, errands,
travel legs, live games, or "check how X went" moments. Default to queuing the
follow-up when the moment is specific, time-bounded, and likely welcome; ask
first only when the social fit is ambiguous. This is different from
`quick-reminders`: quick reminders send fixed text at a fixed time with no LLM;
engagement follow-ups let interactive Rumi write a constrained instruction now
and let the cron write a natural message later.

All queue writes go through the helper, never by editing
`memory/engagement_followups.jsonl` directly:

```bash
python3 cron/engagement_followups.py enqueue --json '{
  "due_in_minutes": 60,
  "expires_in_hours": 6,
  "intent": "Ask Kenny how the workout went.",
  "source_context": "Kenny said he was about to go work out.",
  "suggested_message_angle": "casual, no pressure, one line",
  "requires_live_check": false,
  "payload": {"activity": "workout"}
}'
```

For live outcomes, set `requires_live_check: true` and use only supported
`live_check_type` values. The first supported live check is `sports_result`:

```bash
python3 cron/engagement_followups.py enqueue --json '{
  "due_in_minutes": 180,
  "expires_in_hours": 8,
  "intent": "Tell Kenny how the Phillies game ended if it is final.",
  "source_context": "Kenny was talking about the Phillies game.",
  "suggested_message_angle": "fan-to-fan, excited if they won, sympathetic if they lost",
  "requires_live_check": true,
  "live_check_type": "sports_result",
  "payload": {"team": "Phillies", "league": "MLB"}
}'
```

The helper prints `QUEUED` or `DUPLICATE`. Keep any user-visible confirmation
brief and natural; do not expose queue IDs or raw JSON unless Kenny asks.

---

## Telegram

- **Kenny's chat id:** `7540422842`
- **Cayce's chat id:** `8790259622` (Kenny's wife — has a per-DM `systemPrompt` set in `~/.openclaw/openclaw.json` that defines her access policy; that prompt overrides default behavior for her DMs).
- All other senders go through the channel allowlist in `openclaw.json` (`channels.telegram.allowFrom`).

Group chats require a mention of the bot to trigger a reply
(`channels.telegram.groups['*'].requireMention: true`).

---

## Memory Search

OpenClaw memory search is backed by QMD when available. Use `memory_search`
when the injected memory snapshot is not enough for searchable docs, future
markdown memory, prior plans, or project context. Use `memory_get` to read a
cited markdown source returned by search.

Memory search is read-only recall. It does not change the write policy in
`AGENTS.md`: only Kenny may cause writes to `memory/*.jsonl`, and curated JSONL
memory remains the source of truth for what Rumi intentionally remembers.

---

## Skills (workspace-local)

Workspace-local skills live in `skills/` and override bundled/managed skills
of the same name:

- `skills/memory_manager.md` — invoked by `memory-plugin.ts` after each
  interactive turn to decide whether to append to medium memory.
- `skills/agent-browser/SKILL.md` — browser automation skill for Rumi.

Enabled skills (see `~/.openclaw/openclaw.json` `skills.entries`): `gog`,
`quick-reminders`, and the workspace-local `agent-browser`. Everything else is
disabled by default.

## `agent-browser` CLI (web browsing)

`agent-browser` is Rumi's default tool for live web work. Use it before
`web_fetch` whenever Kenny asks Rumi to open, inspect, search within, click
around, scrape, or verify a webpage, especially sites that block simple fetches
(eBay, ESPN, most major news/sports sites).

Use `web_fetch` only when Kenny explicitly asks for a raw URL fetch/static page
read, or when `agent-browser` is unavailable or fails after one retry.

**Always use `agent-browser` first for:**
- Web browsing
- Sports scores, schedules, live data (ESPN, NBA, NFL sites)
- E-commerce searches (eBay, Amazon, etc.)

**Basic pattern:**
```bash
agent-browser open <url>
agent-browser snapshot          # get page content
agent-browser snapshot -i       # get content with interactive refs
agent-browser get title
agent-browser close             # always close when done
```

Load and follow `skills/agent-browser/SKILL.md` for full usage. Do not narrate
that you are using `agent-browser` — just use it and return the result.
