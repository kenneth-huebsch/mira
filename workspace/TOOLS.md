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

Use `skills/gog-reauth/SKILL.md` when `gog` reports an expired or revoked
Gmail OAuth token, or when Kenny asks to re-run the Gmail OAuth flow.

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
- For manual cron kickoffs requested in chat, use
  `skills/manual-cron-kickoff/SKILL.md`. After `cron run` is accepted, return a
  short visible acknowledgement immediately; do not poll unless Kenny explicitly
  asks.
- After creating or editing a cron, verify it with `openclaw cron list --json`
  or `openclaw cron runs <job-id>` before telling Kenny it is done.

Container-safe pattern. Mira's gateway container is
`openclaw-mira-openclaw-gateway-1`. Always pass `--user node` so the CLI runs
as the same uid that owns the workspace and extensions; without it
`docker exec` defaults to root and prints spurious "blocked plugin candidate:
suspicious ownership" warnings for every workspace-owned plugin (the daemon
itself runs as `node` and loads them fine — those warnings only appear on
root-invoked CLI calls and are not runtime failures):

```bash
docker exec --user node openclaw-mira-openclaw-gateway-1 openclaw cron edit <job-id> \
  --model openrouter/xiaomi/mimo-v2-flash \
  --thinking off
```


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

## Dripr Staging (Kenny-only)

Staging is Kenny's local Dripr environment on his own computer. Mira must not:

- read or source `env/staging.env`
- call staging APIs or URLs
- deploy to staging or interact with Kenny's local staging app

Mira's **only** staging touchpoints are the database:

- read-only `dripr-staging` queries when Kenny explicitly asks
- copying a production `education_topics` row into `dripr-staging` through
  `capabilities/dripr_education_topics/dripr_education_topics.py copy-to-staging`
  when Kenny explicitly asks to copy an education topic to staging

Default all other Dripr workflows to **production**.

## Dripr Production Debug

Use the local `dripr-production-debug` skill when Kenny asks Mira to debug
Dripr, investigate a production issue, explain a CloudWatch alert, or inspect a
campaign/email/user problem.

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

QMD indexes Dripr repo skills for on-demand recall in direct chat at
`runtime/repos/dripr/.agent/skills/**/SKILL.md` after the checkout exists.

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

List Dripr repo skills from the live checkout:

```bash
python3 capabilities/dripr_coding/dripr_coding.py list-skills
python3 capabilities/dripr_production_debug/dripr_production_debug.py list-skills
```

Detached Dripr subagents should use `list-skills` after repo refresh or
`git pull --ff-only`, then read only the relevant `.agent/skills/*/SKILL.md`
files for the task. QMD also indexes Dripr repo skills for on-demand recall in
direct chat.


## Dripr Education Topics

Use the local `dripr-education-topics` skill when Kenny asks Mira to create,
upload, publish, or draft monthly Dripr education topics.

This workflow runs in the **interactive** session because Kenny must review
title, copy, and image before publish. Do not spawn a detached subagent.

Mira publishes approved topics to **production only** through
`POST /api/education-topics` using `DRIPR_API_KEY` and `VITE_API_GATEWAY_URL`
from `env/prod.env`. The API uploads the image and creates the database row.
She does not publish to staging.

Helper commands:

```bash
python3 capabilities/dripr_education_topics/dripr_education_topics.py check-config
python3 capabilities/dripr_education_topics/dripr_education_topics.py sync-repo
python3 capabilities/dripr_education_topics/dripr_education_topics.py recent-topics
python3 capabilities/dripr_education_topics/dripr_education_topics.py generate-image \
  --title "<title>" --visual-concept "<scene>" --output <draft.png>
python3 capabilities/dripr_education_topics/dripr_education_topics.py publish --kenny-approved \
  --month <month> --year <year> --title "<title>" --content "<content>" --image <draft.png>
python3 capabilities/dripr_education_topics/dripr_education_topics.py copy-to-staging \
  --month <month> --year <year>
```

Credentials come from Dripr **`env/prod.env`** for production workflows. The
`copy-to-staging` command also reads `DATABASE_URL` from **`env/staging.env`**
and writes only one `education_topics` row when Kenny explicitly asks. It does
not call staging APIs. Mira does not use staging env files for other workflows.

The canonical creative rules live in the Dripr checkout at:

```bash
/home/node/.openclaw/workspace/runtime/repos/dripr/.agent/skills/uploading-education-topics/SKILL.md
```

Use `sync-repo`, not `dripr_coding.py prepare-repos`, so in-progress draft
images under Mira runtime are not disturbed.

Optional live-only overrides belong in:

```bash
/home/node/.openclaw/secrets/dripr-education-topics.env
```

Supported overrides only:

```bash
DRIPR_REPO_PATH=/home/node/.openclaw/workspace/runtime/repos/dripr
DRIPR_EDUCATION_TOPICS_RUN_ROOT=/home/node/.openclaw/workspace/runtime/capability-runs/dripr-education-topics
DRIPR_BEDROCK_REGION=us-west-2
```

### Scheduled check

Mira's monthly education-topic readiness check runs as a scheduled cron and
must use the capability helper instead of ad hoc database commands:

```bash
python3 capabilities/dripr_education_topics/dripr_education_topics.py check-next-month
```

The scheduled check runs daily at 10:30 AM Eastern. The helper returns
`NO_REPLY` on non-trigger days. On the trigger day (14 days before month-end),
it notifies Kenny when next month's production topic already exists or asks
whether to create one. Creation stays in the interactive `dripr-education-topics`
skill after Kenny replies yes.



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
