# TOOLS.md

Canonical reference for tool-specific conventions. This file is auto-injected
into every agent run, so cron prompts and `AGENTS.md` should reference it
rather than restating account names, calendar IDs, or command flags.

If a convention here drifts from reality (an account changes, a calendar id
fails to resolve, a command flag is renamed), fix it HERE — once — and every
caller picks it up automatically.

---

## OpenClaw Exec Runtime

Mira's OpenClaw `exec` tool runs inside the gateway container
(`/home/node/.openclaw/workspace`). Cron helpers should call container-provided
commands directly, such as `gog` or `python3`, and must not call `docker exec`
or require host-installed tool binaries.

Runtime dependencies belong in `openclaw/entrypoint.sh` so restored containers
prepare the same command surface. Live credentials and tokens remain under
`.openclaw` secrets/state and must not be copied into tracked files.

## `gog` (Google Workspace CLI)

`gog` is OpenClaw's Google Workspace skill. Always load and follow the bundled
`gog` skill before issuing commands; the notes below cover only the
Kenny-specific conventions.

### Account

Mira's Gmail account is `mira.agentops@gmail.com`. Use one of the following on
every Gmail call:

- Set `GOG_ACCOUNT=mira.agentops@gmail.com` in the environment, or
- Pass `--account mira.agentops@gmail.com` explicitly.

### Gmail usage

Dripr inbox triage checks unread mail forwarded into Mira's Gmail for two
original addresses:

- `info@dripr.ai` - marketing-site form submissions.
- `kenny@dripr.ai` - Kenny's business email.

Common patterns:

```bash
# Search unread mail that appears to be forwarded to Mira from dripr addresses.
gog gmail messages search "in:inbox is:unread deliveredto:mira.agentops@gmail.com (to:info@dripr.ai OR to:kenny@dripr.ai)" --max 100 --account mira.agentops@gmail.com --json

# Fetch full message.
gog gmail get <messageId> --account mira.agentops@gmail.com --json

# Mark read after review.
gog gmail messages modify <messageId> --remove UNREAD --account mira.agentops@gmail.com
```

The Gmail search operator is `deliveredto:` (lowercase, no hyphen); the raw
email header is `Delivered-To`. For forwarded dripr mail, prefer the original
address from `X-Pm-Forwarded-From` or `X-Original-To` when present, then fall
back to `To`.

### OpenClaw Crons

Use OpenClaw crons for recurring scheduled agent work. For LLM-backed crons:

- Use the OpenClaw cron CLI rather than editing cron JSON directly.
- Never set `payload.model` to `default`; use a fully qualified model id.
- For ordinary cron/tool workflows, set `payload.model` to
  `openrouter/xiaomi/mimo-v2-flash` and `payload.thinking` to `off`.
- Use Eastern time (`America/New_York`) for user-facing schedules unless Kenny
  explicitly asks otherwise.
- For `delivery.mode: announce` crons, the payload should return the message as
  final visible text. Do not tell the model to send Telegram itself.
- If a cron should be silent when there is nothing useful, make the payload say
  `return exactly NO_REPLY`; do not say only "do nothing".
- After creating or editing a cron, verify it with `openclaw cron list --json`
  or `openclaw cron runs <job-id>` before telling Kenny it is done.


## MySQL New-User Check

Mira's MySQL new-user check runs as a scheduled cron and must use the
capability helper instead of ad hoc database commands:

```bash
python3 capabilities/mysql_new_users/mysql_new_users.py review
```

Configuration is live-only and belongs in:

```bash
/home/node/.openclaw/secrets/mysql-new-users.env
```

On Kenny's host, that maps to:

```bash
/home/kenny/mira/.openclaw/secrets/mysql-new-users.env
```

Keep MySQL credentials, DSNs, query output, logs, and private user data out of
tracked files. The helper accepts only read-only `SELECT` or `WITH` SQL and
returns compact JSON or exactly `NO_REPLY`.

The scheduled check runs at 11:00 AM Eastern. It should notify Kenny only when
the helper returns new users. If no rows match, return exactly `NO_REPLY`.


## CloudWatch Dashboard Check

Mira's CloudWatch dashboard check runs as a scheduled cron and must use the
capability helper instead of ad hoc AWS commands:

```bash
python3 capabilities/cloudwatch_dashboard/cloudwatch_dashboard.py review
```

Configuration is live-only and belongs in:

```bash
/home/node/.openclaw/secrets/cloudwatch-dashboard.env
```

On Kenny's host, that maps to:

```bash
/home/kenny/mira/.openclaw/secrets/cloudwatch-dashboard.env
```

The threshold file is also live-only. By default the helper reads:

```bash
/home/node/.openclaw/secrets/cloudwatch-dashboard-checks.json
```

Keep AWS credentials, account IDs, ARNs, dashboard JSON, metric outputs, and
private production details out of tracked files. The helper uses the AWS SDK to
read the `dripr-daily` CloudWatch dashboard in `us-east-1`, evaluates the past
24 hours against configured thresholds, and returns compact JSON or exactly
`NO_REPLY`.

The scheduled check runs at 9:00 AM Eastern. It should notify Kenny only when
configured checks breach thresholds or when setup/runtime fails. If all checks
are healthy, return exactly `NO_REPLY`.


## `agent-browser` CLI (web browsing)

`agent-browser` is Mira's default tool for live web work. Use it before
`web_fetch` whenever Kenny asks Mira to open, inspect, search within, click
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
