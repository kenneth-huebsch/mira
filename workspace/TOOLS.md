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

## Telegram

- **Kenny's chat id:** `7540422842`
- **Cayce's chat id:** `8790259622` (Kenny's wife — has a per-DM `systemPrompt` set in `~/.openclaw/openclaw.json` that defines her access policy; that prompt overrides default behavior for her DMs).
- All other senders go through the channel allowlist in `openclaw.json` (`channels.telegram.allowFrom`).

Group chats require a mention of the bot to trigger a reply
(`channels.telegram.groups['*'].requireMention: true`).

---

## Skills (workspace-local)

Workspace-local skills live in `skills/` and override bundled/managed skills
of the same name:

- `skills/memory_manager.md` — invoked by `memory-plugin.ts` after each
  interactive turn to decide whether to append to medium memory.
- `skills/engagement_priorities_manager.md` — invoked by `memory-plugin.ts`
  after each interactive turn to decide whether to append a priority.
- `skills/agent-browser/SKILL.md` — browser automation skill for Rumi.

Bundled skills currently enabled (see `~/.openclaw/openclaw.json`
`skills.entries`): `gog`, `quick-reminders`, `browser`. Everything else is
disabled by default.
