# Dripr Production Debug

This capability lets Mira investigate Dripr production issues with read-only
evidence from the Dripr repo, MySQL, CloudWatch, and only Kenny-approved tests.

Staging is Kenny's local environment. Mira does not use `env/staging.env` or
staging APIs. She may query the `dripr-staging` database only when Kenny
explicitly asks to inspect staging DB state.

## Files

- `dripr_production_debug.py` - deterministic helper for repo preflights,
  explicitly approved test commands, bounded read-only MySQL queries, and
  bounded CloudWatch log searches.
- `DRIPR_PRODUCTION_DEBUG.md` - Mira-facing behavior for incident
  investigation, report quality, and safety rules.
- `../../skills/dripr-production-debug/SKILL.md` - interactive trigger and
  subagent workflow.

## Live-Only Runtime

The Dripr checkout is live-only and should not be copied into the Mira
blueprint:

```bash
/home/kenny/mira/.openclaw/workspace/runtime/repos/dripr
```

Inside the OpenClaw container this is:

```bash
/home/node/.openclaw/workspace/runtime/repos/dripr
```

The checkout should contain:

- `python/venv` with dependencies installed from `python/requirements.txt`.
- `ui/node_modules` installed with dev dependencies available for tests.
- A clean git working tree before each investigation unless Kenny explicitly
  asks Mira to inspect local edits.
- The detached debug subagent should run `git pull --ff-only` before relying on
  repo code or docs. If the pull fails, it should stop and report the blocker.

## Live-Only Configuration

Optional config belongs in:

```bash
/home/kenny/mira/.openclaw/secrets/dripr-production-debug.env
```

Inside the container:

```bash
/home/node/.openclaw/secrets/dripr-production-debug.env
```

Supported values:

```bash
DRIPR_REPO_PATH=/home/node/.openclaw/workspace/runtime/repos/dripr
DRIPR_DEBUG_MODEL=openrouter/openai/gpt-5.5
DRIPR_DEBUG_THINKING=medium
DRIPR_DEBUG_TIMEOUT_SECONDS=7200
DRIPR_DEBUG_MYSQL_MAX_ROWS=50
DRIPR_DEBUG_LOG_GROUPS=/aws/lightsail/dripr/api-gateway,/aws/lightsail/dripr/data-fetcher,/aws/lightsail/dripr/email-manager
DRIPR_MYSQL_ENV_FILE=/home/node/.openclaw/secrets/mysql-new-users.env
DRIPR_CLOUDWATCH_ENV_FILE=/home/node/.openclaw/secrets/cloudwatch-dashboard.env
```

Do not put GitHub tokens, database credentials, AWS keys, env files, query
outputs, logs, customer data, or incident transcripts in tracked files.

## Manual Checks

From Mira's OpenClaw workspace:

```bash
python3 capabilities/dripr_production_debug/dripr_production_debug.py check-config
python3 capabilities/dripr_production_debug/dripr_production_debug.py repo-status
python3 capabilities/dripr_production_debug/dripr_production_debug.py list-skills
```

Only when Kenny explicitly asks Mira to run Dripr tests:

```bash
python3 capabilities/dripr_production_debug/dripr_production_debug.py run-test python-unit --kenny-approved
python3 capabilities/dripr_production_debug/dripr_production_debug.py run-test ui-unit --kenny-approved
python3 capabilities/dripr_production_debug/dripr_production_debug.py run-test integration-trial --kenny-approved
```

MySQL queries must be a single `SELECT` or `WITH` statement:

```bash
python3 capabilities/dripr_production_debug/dripr_production_debug.py mysql-query --sql "SELECT id, campaign_status FROM campaigns LIMIT 5"
```

CloudWatch searches are bounded by time and result limit:

```bash
python3 capabilities/dripr_production_debug/dripr_production_debug.py cloudwatch-logs --filter-pattern '"ERROR"' --since-hours 6 --limit 50
```

CloudWatch log search requires the AWS identity in `DRIPR_CLOUDWATCH_ENV_FILE`
to allow `logs:FilterLogEvents` on the Dripr log groups. Dashboard metric
access alone is not enough for log investigation.

## Boundaries

This capability is investigative by default and should run only in a detached
subagent pinned to the configured model/thinking level. It may read repo files,
query read-only production data, and search logs. It must not run Dripr repo
scripts or tests unless Kenny explicitly asks for that exact run. That includes
deploy/build scripts, `python/scripts/**`, `.agent/scripts/**`,
`python/cron_jobs/**`, package scripts such as `npm run ...`, and
helper/utility scripts. It must not mutate production, send customer email,
deploy, push commits, open PRs, or perform data repairs unless Kenny explicitly
asks for that separate workflow.
