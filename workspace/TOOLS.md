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


## Dripr Production Debug

Use the local `dripr-production-debug` skill when Kenny asks Mira to debug
Dripr, investigate a production/staging issue, explain a CloudWatch alert, or
inspect a campaign/email/user problem.

The Dripr checkout is live-only and lives at:

```bash
/home/node/.openclaw/workspace/runtime/repos/dripr
```

On Kenny's host, that maps to:

```bash
/home/kenny/mira/.openclaw/workspace/runtime/repos/dripr
```

The helper command is:

```bash
python3 capabilities/dripr_production_debug/dripr_production_debug.py check-config
```

Configuration is live-only and belongs in:

```bash
/home/node/.openclaw/secrets/dripr-production-debug.env
```

On Kenny's host, that maps to:

```bash
/home/kenny/mira/.openclaw/secrets/dripr-production-debug.env
```

Default model/timeout for detached investigations:

```bash
DRIPR_DEBUG_MODEL=openrouter/openai/gpt-5.5
DRIPR_DEBUG_THINKING=medium
DRIPR_DEBUG_TIMEOUT_SECONDS=7200
```

The workflow must run in a detached subagent so the stronger model can work
without blocking Mira's interactive session. It is read-only by default. It may
inspect the Dripr checkout, run bounded read-only MySQL `SELECT`/`WITH`
queries, and search CloudWatch logs. It must not run Dripr repo scripts or tests
unless Kenny explicitly asks for that exact run. That includes deploy/build
scripts, `python/scripts/**`, `.agent/scripts/**`, `python/cron_jobs/**`,
package scripts such as `npm run ...`, and helper/utility scripts. It must not
mutate production, deploy, push code, open PRs, send customer-facing email, or
repair data unless Kenny explicitly asks for that separate action.

Before relying on Dripr repo code or docs, the detached debug subagent must run:

```bash
git pull --ff-only
```

from `/home/node/.openclaw/workspace/runtime/repos/dripr`. If the pull fails,
stop and report the blocker rather than investigating stale code.

If the detached debug subagent is confused or missing essential context, it
should ask one concise question in its final report and then end. Kenny will
answer in interactive chat; Mira can then spawn a fresh subagent with the extra
context.


## Dripr Coding

Use the local `dripr-coding` skill when Kenny asks Mira to implement, fix,
refactor, test, or otherwise code something in Dripr.

The workflow must run in a detached subagent so the prompt-to-PR agent loop can
work without blocking Mira's interactive session. The main session should only
scope the request, spawn the detached run, and return visible confirmation text
without waiting for child progress.

The live-only repos live at:

```bash
/home/node/.openclaw/workspace/runtime/repos/dripr
/home/node/.openclaw/workspace/runtime/repos/agent
```

On Kenny's host, those map to:

```bash
/home/kenny/mira/.openclaw/workspace/runtime/repos/dripr
/home/kenny/mira/.openclaw/workspace/runtime/repos/agent
```

The helper command is:

```bash
python3 capabilities/dripr_coding/dripr_coding.py check-config
python3 capabilities/dripr_coding/dripr_coding.py prepare-repos
python3 capabilities/dripr_coding/dripr_coding.py run-prompt-pr --title "<title>" --kind chore --prompt "<task>"
```

The helper clones missing repos from:

```bash
https://github.com/kenneth-huebsch/dripr.git
https://github.com/kenneth-huebsch/agent.git
```

If a repo exists, the helper refreshes it to clean `main` with:

```bash
git reset --hard
git clean -fd
git switch main
git pull --ff-only
```

This deletes tracked and untracked local edits while preserving ignored files
such as `node_modules`, virtualenvs, and local env files.

The helper also configures repo-local git commit identity before the prompt
runner starts:

```bash
user.name=mira-dripr-coding-agent
user.email=mira-dripr-coding-agent@users.noreply.github.com
```

Override with `DRIPR_CODING_GIT_USER_NAME` and
`DRIPR_CODING_GIT_USER_EMAIL` in the live-only env file only when the runner
should use a different commit identity.

Configuration is optional and live-only. If present, it belongs in:

```bash
/home/node/.openclaw/secrets/dripr-coding.env
```

On Kenny's host, that maps to:

```bash
/home/kenny/mira/.openclaw/secrets/dripr-coding.env
```

Default model/timeout for detached coding runs:

```bash
DRIPR_CODING_MODEL=openrouter/xiaomi/mimo-v2-flash
DRIPR_CODING_THINKING=off
DRIPR_CODING_TIMEOUT_SECONDS=7200
```

The Dripr coding subagent is an orchestration wrapper, not the implementation
engine. Cursor CLI performs the actual coding inside Dripr's prompt-to-PR
runner, so the OpenClaw subagent does not need a frontier model by default.

The prompt-to-PR runner requires Cursor CLI auth, `gh` auth, git auth for both
repos, and Dripr `env/integration.env` pointed at the test environment. If
`/home/node/.openclaw/secrets/dripr-git-credentials` exists, the helper uses it
as the Git credential store for both repos. Keep auth state, tokens, generated
task files, logs, repo checkouts, and env contents out of tracked files.

This capability may run Dripr's `.agent/scripts/run-prompt-pr.sh` wrapper
because Kenny explicitly asked for a coding job. It must not deploy, mutate
infrastructure, edit production or staging data, touch credentials, or run
production/staging tests. Dripr Production Debug remains read-only by default
and must continue to treat Dripr repo scripts as banned unless Kenny explicitly
asks for that exact debug-time run.

The detached subagent must invoke `run-prompt-pr` or report a concrete blocker.
Restating the requested change is not completion.


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
