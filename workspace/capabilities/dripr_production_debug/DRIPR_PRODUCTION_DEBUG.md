---
capability_id: dripr_production_debug
---

# Dripr Production Debug

Use this capability inside the detached Dripr Production Debug subagent when
Kenny asks Mira to debug Dripr, when Kenny reports a production symptom, or
when a Dripr ops alert needs deeper investigation.

The investigation must run in a detached subagent with the configured stronger
model. Do not conduct Dripr production investigations in Mira's main
interactive session.

## First Move

Restate the investigation scope in one sentence:

- Environment: production, staging, integration, or unknown.
- Symptom: what appears broken.
- Time window in Eastern time.
- Known identifiers: campaign ID, email ID, user email, Clerk user ID, route,
  queue name, message ID, log text, or screenshot details.

If the symptom lacks a usable time window and identifier, the main Mira session
may ask Kenny for the smallest missing detail before launching the detached
subagent. Once launched, proceed with the available evidence.

If, after launch, the detached subagent is confused or missing essential context,
it must surface the confusion as one concise question in its final report and
then end. Do not wait in-session or ask follow-up questions in a loop. Kenny
will answer in interactive chat, and Mira can spawn a fresh subagent with the
additional context.

## Evidence Order

1. In the Dripr checkout, run `git pull --ff-only` before using repo code or
   docs. If it fails because of auth, local changes, conflicts, or network
   trouble, stop and report the blocker instead of investigating stale code.
2. Read Dripr repo guidance:
   - `AGENTS.md`
   - every `.agent/skills/*/SKILL.md` file
   - `docs-internal/system-design.md`
   - `docs-internal/campaign-state-machine.md` for campaign or email lifecycle
   - `docs-internal/testing-strategy.md`
3. Inspect the code path that owns the symptom.
4. Use read-only MySQL only for the smallest useful state slice.
5. Use CloudWatch logs around exact identifiers and timestamps.
6. Do not run tests or scripts from the Dripr repo unless Kenny explicitly asks
   for that exact run.

Do not claim a root cause from code alone when CloudWatch logs or database state
are available and relevant.

## Dripr Mental Model

Dripr is a React/Vite UI with Flask API Gateway, Data Fetcher, Email Manager,
Cron Jobs, MySQL, and SNS/SQS event fan-out. Common incident areas:

- signup/auth/user lifecycle: Clerk webhook, `USER_CREATED`, welcome email
- billing: Stripe webhooks and subscription status
- campaign orchestration: `DORMANT`, `WAITING_FOR_DATA`,
  `WAITING_FOR_HOME_ANALYSIS`, `READY_TO_CREATE_EMAIL`, `READY_TO_SEND_EMAIL`
- data fetching: Zillow, Rentcast, Google Maps, local market data
- AI generation: Bedrock intro and home report analysis
- email creation/sending: Gmail, Postmark, S3-rendered HTML
- queue health: SNS/SQS fan-out and service consumers
- database consistency: cadence clock, status/sub-status, current email, error
  text

Campaign scheduling is high risk. Preserve the Eastern-time `fixed_send_day`
invariant, `last_scheduled_send_date` cadence-clock semantics, first-email
delay, 14-day cooldown, monotonic schedule guards, and delivery-status priority.

## Helper Commands

Preflight:

```bash
python3 capabilities/dripr_production_debug/dripr_production_debug.py check-config
python3 capabilities/dripr_production_debug/dripr_production_debug.py repo-status
```

Tests require Kenny's explicit approval:

```bash
python3 capabilities/dripr_production_debug/dripr_production_debug.py run-test python-unit --kenny-approved
python3 capabilities/dripr_production_debug/dripr_production_debug.py run-test ui-unit --kenny-approved
python3 capabilities/dripr_production_debug/dripr_production_debug.py run-test integration-trial --kenny-approved
```

Read-only MySQL:

```bash
python3 capabilities/dripr_production_debug/dripr_production_debug.py mysql-query --sql "<single SELECT or WITH query>"
```

CloudWatch logs:

```bash
python3 capabilities/dripr_production_debug/dripr_production_debug.py cloudwatch-logs --filter-pattern '"exact id or error text"' --since-hours 6 --limit 50
```

When an `exec` call returns `Command still running (session <name>, pid <pid>)`,
use the returned session name for process follow-up, not the PID. If one
session-name poll fails, stop and report the process follow-up failure instead
of retrying in a loop.

Do not invent helper flags. Use only arguments documented here or shown by
the helper's CloudWatch help:

```bash
python3 capabilities/dripr_production_debug/dripr_production_debug.py cloudwatch-logs --help
```

Keep CloudWatch log group names exact; the cron log group is
`/aws/lightsail/dripr/cron-jobs` with a hyphen.

## Scripts And Tests

- Do not run scripts from the Dripr repo unless Kenny explicitly asks. This
  includes `build-and-push-to-aws.sh`, `deploy-to-lightsail.sh`,
  `spin_up_env.py`, `python/scripts/**`, `.agent/scripts/**`,
  `python/cron_jobs/**`, package scripts such as `npm run ...`, and
  helper/utility scripts.
- Do not run Dripr tests unless Kenny explicitly asks for tests.
- If Kenny approves Python pure logic tests, use `run-test python-unit
  --kenny-approved`.
- If Kenny approves UI pure logic tests, use `run-test ui-unit
  --kenny-approved`.
- If Kenny approves database/API tests, use a targeted integration test only
  when the test environment is clearly `dripr-test`.
- Do not run tests against `dripr-prod` or `dripr-staging`.
- Do not run broad or expensive suites unless Kenny asks or the investigation
  needs them.
- Always run `git pull --ff-only` before relying on Dripr repo code or docs. If
  the pull fails, report the blocker and do not continue against stale code.
- If confused or missing essential context, ask one concise question in the
  final report and end. Do not keep investigating by guessing.

## Safety Rules

- Read-only by default: no database writes, AWS mutations, deploys, customer
  emails, repo pushes, PRs, or production repairs.
- If a repair is needed, stop with a recommendation. Use Dripr's
  `.agent/skills/gated-production-db-repairs/` only after Kenny explicitly asks
  for a repair workflow.
- Redact or summarize customer data, credentials, account IDs, ARNs, hostnames,
  and long logs.
- Do not paste raw env files, SQL dumps, CloudWatch output, tokens, or
  transcript internals.
- Three strikes: if the same path fails three times, stop and report what is
  blocked.

## Report Format

Return a concise incident report:

```text
Dripr debug report: <short symptom>

What I checked:
- <repo/doc/code/db/log/test evidence>

Findings:
- <confirmed fact with source>
- <rejected hypothesis with source>

Likely root cause:
<state confidence and why>

Recommended next move:
<one or two concrete next steps, noting if Kenny approval is needed>

Gaps:
<missing access, missing identifier, or test/log gap; omit if none>
```

If there is no issue, say that clearly and list the evidence checked.
