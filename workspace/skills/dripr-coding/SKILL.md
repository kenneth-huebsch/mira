---
name: dripr-coding
description: Hand Dripr coding requests to a detached prompt-to-PR run. Use when Kenny asks Mira to implement, fix, refactor, test, or otherwise code something in the Dripr repo.
---

# Dripr Coding

Use this skill when Kenny asks Mira to make a Dripr code change. Always launch
the work in a detached subagent so the local prompt-to-PR agent loop can run
without blocking Interactive Mira. The main session may only scope the request,
start the subagent, and report that it is running.

After spawning the subagent, always return visible final text in the same turn;
an empty/tool-only parent turn is invalid and surfaces as a Telegram failure.
Do not wait for the child to make progress or complete.

## Quick Start

1. Read `capabilities/dripr_coding/DRIPR_CODING.md`.
2. If Kenny's request does not identify a coding task, ask one concise
   clarifying question before launching.
3. Spawn a detached background subagent with:
   - label: `dripr-coding`
   - model: `openrouter/xiaomi/mimo-v2-flash` unless `DRIPR_CODING_MODEL` says otherwise
   - thinking: `off` unless `DRIPR_CODING_THINKING` says otherwise
   - run timeout: 7200 seconds unless Kenny gives a different bound
4. Immediately end the parent turn with visible final text. Use no tools and do
   not wait for subagent output after `sessions_spawn`. The final text should be
   one sentence, for example:
   `Started a detached Dripr coding run; it will refresh Dripr and the agent harness, then kick off the prompt-to-PR runner.`

## Subagent Prompt Shape

Give the child this task:

```text
Run a Dripr coding prompt-to-PR job for this request: <Kenny's request>.

Read capabilities/dripr_coding/DRIPR_CODING.md first. Use the helper at
capabilities/dripr_coding/dripr_coding.py. It owns cloning or refreshing the
Dripr repo at /home/node/.openclaw/workspace/runtime/repos/dripr and the agent
harness at /home/node/.openclaw/workspace/runtime/repos/agent.

Run `python3 capabilities/dripr_coding/dripr_coding.py check-config`, then
`python3 capabilities/dripr_coding/dripr_coding.py prepare-repos`. After the
repos are refreshed, read Dripr's AGENTS.md and the relevant `.agent/skills/*/SKILL.md`
files, then run `python3 capabilities/dripr_coding/dripr_coding.py run-prompt-pr`
with a short title, the best matching kind, and Kenny's request as the prompt.
Do not stop after restating the request. The job is incomplete unless
`run-prompt-pr` has been invoked or a concrete setup/auth/repo blocker prevented
that invocation.

Let Dripr's prompt-to-PR runner own the implementation, review, checks, branch,
push, and PR. If setup, auth, repo refresh, or the runner fails, stop and return
a concise blocker report. Your final report must include the helper commands
you ran and either the PR URL, runner result, or blocker. If helper JSON includes
`review_must_fix`, quote those bullets in the final report; do not say reviewer
details are unavailable. Do not deploy, mutate infrastructure, edit production
or staging data, touch credentials, or paste secrets/logs/customer data.
```

Use `sessions_spawn`. Do not conduct the coding job in the main session. If
detached subagents are unavailable, stop and tell Kenny the run could not be
started. Do not poll in a loop; OpenClaw announces completion. Use `/subagents`
or task tools only for intervention or explicit status requests.

Immediately after `sessions_spawn` succeeds, end the parent turn with a visible
one-sentence acknowledgment. Do not ask follow-up questions, present choices,
read more files, inspect child output, or leave the parent response empty after
the subagent is started. The next assistant message after `sessions_spawn` must
contain visible normal assistant text, not hidden thinking.

## Confusion Or Missing Context

If the detached subagent is confused, lacks the key context needed to proceed,
or finds multiple materially different interpretations of Kenny's request, it
must surface the confusion as one concise question in its final report and then
end. It should not wait in-session, keep probing, or ask follow-up questions in
a loop. Kenny will answer in the interactive chat, and Mira can spawn a new
subagent with the additional context.

## Hard Stops

- Do not run Dripr coding work in Interactive Mira's parent session.
- Do not use the Dripr production debug helper for coding tasks.
- Do not deploy, mutate infrastructure, edit production or staging data, or
  touch credentials.
- Do not expose credentials, env contents, account IDs, ARNs, raw logs, or
  unnecessary customer data.
- If setup or the runner fails, report the blocker and stop.
