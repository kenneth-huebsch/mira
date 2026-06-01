---
name: dripr-production-debug
description: Debug Dripr production, staging, or ops issues with a long-running read-only background investigation. Use when Kenny asks Mira to debug Dripr, investigate a prod issue, explain a CloudWatch alert, inspect a campaign/email/user problem, or run Dripr tests.
---

# Dripr Production Debug

Use this skill when Kenny wants Dripr investigated rather than a quick answer.
Always launch the investigation in a detached subagent so the stronger pinned
model can run without blocking Mira's interactive session. The main session may
only scope the request, start the subagent, and report that it is running.
After spawning the subagent, always return visible final text in the same turn;
an empty/tool-only parent turn is invalid and surfaces as a Telegram failure.

## Quick Start

1. Read `capabilities/dripr_production_debug/DRIPR_PRODUCTION_DEBUG.md`.
2. Run the preflight helper if tool access is available:
   `python3 capabilities/dripr_production_debug/dripr_production_debug.py check-config`
3. Spawn a detached background subagent with:
   - label: `dripr-production-debug`
   - model: `openrouter/openai/gpt-5.5` unless
     `DRIPR_DEBUG_MODEL` says otherwise
   - thinking: `medium` unless `DRIPR_DEBUG_THINKING` says otherwise
   - run timeout: 7200 seconds unless Kenny gives a different bound
4. Tell Kenny the investigation is running and what evidence it will inspect.
   This must be visible final text, for example:
   `Started a detached Dripr production debug run; I will inspect repo/docs, read-only database state, and CloudWatch logs if permissions allow.`

## `sessions_spawn` Arguments

Call `sessions_spawn` with exactly this shape, filling in only `task` and the
configured model/timeout values:

```json
{
  "task": "<subagent prompt>",
  "label": "dripr-production-debug",
  "runtime": "subagent",
  "model": "openrouter/openai/gpt-5.5",
  "thinking": "medium",
  "cwd": "/home/node/.openclaw/workspace",
  "runTimeoutSeconds": 7200,
  "mode": "run",
  "cleanup": "keep",
  "sandbox": "inherit"
}
```

Do not add `agentId`: `dripr-production-debug` is a skill label, not an
OpenClaw agent id. Do not use `runtime: "acp"`, `streamTo`, `resumeSessionId`,
`timeoutSeconds`, `attachAs`, or empty `attachments`; those are not part of this
detached subagent workflow and can make the spawn fail.

## Subagent Prompt Shape

Give the child this task:

```text
Investigate this Dripr issue read-only: <symptom>.

Read capabilities/dripr_production_debug/DRIPR_PRODUCTION_DEBUG.md first.
Use the Dripr checkout at /home/node/.openclaw/workspace/runtime/repos/dripr.
Before operating in that repo, run `git pull --ff-only` so the local checkout is
up to date, then read its AGENTS.md and every `.agent/skills/*/SKILL.md` file
for repo-specific rules and workflows. If `git pull --ff-only` fails, stop and
report the blocker instead of investigating stale code.
Use helper commands under capabilities/dripr_production_debug/ for repo status,
bounded MySQL SELECT/WITH queries, and bounded CloudWatch log searches. Do not
run Dripr repo scripts, package scripts, .agent/scripts, utility scripts,
deploy/build scripts, cron scripts, npm scripts, or tests unless Kenny
explicitly asked for that exact run. Do not mutate production, send email,
deploy, push code, create PRs, or perform DB repairs. Return a concise incident
report with evidence, likely root cause, recommended next move, and gaps.
```

Use `sessions_spawn` with the exact argument shape above. Do not conduct the
investigation in the main session. If detached subagents are unavailable, stop
and tell Kenny the investigation could not be started, including the exact
spawn error. Do not poll in a loop; OpenClaw announces completion. Use
`/subagents` or task tools only for intervention or explicit status requests.
Immediately after `sessions_spawn` succeeds, end the parent turn with a visible
one-sentence acknowledgment. Do not ask follow-up questions, present choices, or
leave the parent response empty after the subagent is started.

## Confusion Or Missing Context

If the detached subagent is confused, lacks the key context needed to proceed,
or finds multiple materially different interpretations of Kenny's request, it
must surface the confusion as one concise question in its final report and then
end. It should not wait in-session, keep probing, or ask follow-up questions in
a loop. Kenny will answer in the interactive chat, and Mira can spawn a new
subagent with the additional context.

## Dripr References

In the Dripr checkout, prioritize:

- `AGENTS.md`
- every `.agent/skills/*/SKILL.md` file
- `docs-internal/system-design.md`
- `docs-internal/campaign-state-machine.md`
- `docs-internal/development-guide.md`
- `docs-internal/testing-strategy.md`

## Hard Stops

- Do not edit the production database.
- Do not run tests against `dripr-prod` or `dripr-staging`.
- Do not run any script from the Dripr repo unless Kenny explicitly asks. This
  includes `build-and-push-to-aws.sh`, `deploy-to-lightsail.sh`,
  `spin_up_env.py`, `python/scripts/**`, `.agent/scripts/**`, `python/cron_jobs/**`,
  package scripts such as `npm run ...`, and helper/utility scripts.
- Always run `git pull --ff-only` in the Dripr checkout before using repo code
  or docs for an investigation. If it fails, stop and report the blocker.
- If confused or missing essential context, ask one concise question in the
  final report and end so Mira can spawn a fresh subagent after Kenny replies.
- Do not run Dripr tests unless Kenny explicitly asks for tests. If approved,
  use the capability helper's `run-test ... --kenny-approved` form.
- Do not expose credentials, env contents, account IDs, ARNs, raw logs, or
  unnecessary customer data.
- Do not deploy, push, open PRs, or send customer-facing email without Kenny's
  explicit request.
- If a repair is needed, recommend it and wait for Kenny.
