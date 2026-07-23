---
name: coding-harness
description: Routes non-Mira coding requests through Kenny's private agent harness and Cursor CLI. Use when Kenny asks Mira to implement, fix, refactor, test, or review code in a repository other than Mira itself.
---

# Coding Harness

Use this skill for coding work in repositories other than Mira's own repo/home.
Do not use it for changes to `/home/kenny/mira`, Mira's OpenClaw runtime, or
Mira behavior files; self-work belongs to a separate future skill.

Mira is a thin router here. She resolves/clones the target repo and rejects
self-work, then delegates all execution to the harness runner
(`runtime/repos/agent/scripts/agent_run.py`). The harness owns prompt
construction, blocking child runs, the green/red gate, handoffs, the per-phase
review-and-remediate loop, phased scheduling, and run records. Mira never
reimplements those; she forwards flags and reports results.

## Preflight

1. Identify the target repository. If Kenny did not provide a path, repo URL, or
   GitHub `owner/repo`, ask for it.
2. Materialize the tracked immutable harness pin, then check config:

   ```bash
   python3 skills/coding-harness/coding_harness.py refresh-harness
   python3 skills/coding-harness/coding_harness.py check-config
   ```

   If `check-config` reports missing Cursor CLI auth, Kenny must authenticate
   Cursor CLI in Mira's runtime before coding runs can execute; use
   `skills/cursor-agent-login/SKILL.md`.

## Small, single-shot work

For a well-scoped change that fits one autonomous run, delegate directly:

```bash
python3 skills/coding-harness/coding_harness.py run \
  --target <path-or-repo> --prompt "<Kenny's coding request>" \
  [--mode plan] [--verify "<cmd>"] [--timeout <secs>] [--dry-run]
```

Prefer structured checks with
`--verification-json '{"commands":[{"argv":["python3","-m","unittest"]}]}'`.
`--verify` is legacy shell compatibility and is denied unless the tracked
policy explicitly permits shell verification. The adapter emits exactly one
JSON object containing `harness_revision` and `runner_result`.

## Larger work: plan, then approved phased execution

For work that is too large or risky for one run, follow the harness
plan-then-approved-execution contract (`skills/phased-execution/SKILL.md` and
`skills/collaborative-planning/SKILL.md` inside the refreshed harness checkout):

1. **Plan interactively with Kenny.** Research the target, present options, and
   converge on an ordered set of phases. Each phase needs a clear done condition
   and a verification command.
2. **Author a phase-spec.** Write the agreed plan as a phase-spec JSON under
   Mira's runtime, e.g. `runtime/coding-harness-plans/<name>.json`:

   ```json
   {
     "schema_version": 2,
     "phases": [
       {
         "id": "phase-1",
         "prompt": "...",
         "done": "...",
         "verification": {
           "commands": [
             {"argv": ["python3", "-m", "pytest", "tests/foo.py"]}
           ]
         }
       },
       {
         "id": "phase-2",
         "prompt": "...",
         "done": "...",
         "verification": {
           "commands": [
             {"argv": ["npm", "test"]}
           ]
         }
       }
     ]
   }
   ```

   `schema_version: 2`, `id`, and `prompt` are required for the documented
   shape. Use structured `verification.commands[].argv`; legacy `verify` shell
   strings are denied by Mira's policy. `done`, `verification`, `mode`
   (`autonomous`/`plan`), `review`, `review_threshold`, and `review_max_rounds`
   are optional per-phase overrides. Phase-specs live in ignored runtime, not the
   blueprint.
3. **Approval gate.** Show Kenny the phase-spec and get explicit approval. Do not
   run an unapproved plan.
4. **Delegate the approved plan:**

   ```bash
   python3 skills/coding-harness/coding_harness.py run-plan \
     --target <path-or-repo> --plan runtime/coding-harness-plans/<name>.json \
     [--timeout <secs>] [--dry-run] \
     [--no-review] [--review-threshold {blocking,high,medium,low}] [--review-max-rounds N]
   ```

   The harness auto-schedules approved phases in sequence and stops on the first
   red gate.

Use `--dry-run` to build run records without invoking `agent` when you want to
confirm the plan shape before a real launch.

## Inspecting runs

Passthroughs to the harness runner (records live under Mira's ignored
`runtime/coding-harness-runs`, set via `AGENT_RUN_HOME`):

```bash
python3 skills/coding-harness/coding_harness.py list
python3 skills/coding-harness/coding_harness.py status <run-id>
python3 skills/coding-harness/coding_harness.py show <run-id>
python3 skills/coding-harness/coding_harness.py resume <run-or-plan-id> [--restart-current-stage]
python3 skills/coding-harness/coding_harness.py cancel <run-or-plan-id> --reason "<reason>"
```

Resume never discards target work or reruns green phases. Drift fails closed;
an interrupted implementation/fix needs explicit `--restart-current-stage`.
Cancellation from another session requires the same run store and a verifiable
recorded process; otherwise the request is persisted for later reconciliation.

## Reporting back

Report the harness output to Kenny: per-phase gate results (green/red),
changed files and git snapshot, verification results, review verdict/findings,
handoffs, and any remaining approval gates.

## Target Rules

- Accepted targets: container-visible paths, GitHub URLs, or GitHub `owner/repo`
  slugs.
- Repositories cloned by the adapter use collision-free `owner--repo` paths
  under `/home/node/.openclaw/workspace/runtime/repos/`; existing origins are
  validated and targets are never auto-pulled. Fresh private clones use GitHub
  CLI's credential helper without exporting or printing a token.
- The adapter rejects symlink escapes and Mira, OpenClaw configuration,
  workspace behavior, and the harness checkout or any repository nested below
  it.

## Updating the pin

Do not point the lock at a branch, tag, or abbreviated SHA. Review and test a
specific agent revision first, then update only the canonical repository URL,
full lowercase 40-character SHA, and supported contract version in
`harness.lock.json`. Run the offline contract tests and inspect the diff before
using `refresh-harness` to materialize it detached.

The path, environment, exact-revision, record, and Git checks are enforced.
Prompts, hooks, and wrappers are advisory defense in depth and do not provide
hard network isolation. External mutations remain explicit approval gates.

## Hard gates

Do not push, deploy, open PRs, merge, rotate credentials, or mutate external
systems unless Kenny explicitly asks and the harness run reports that approval
gate clearly. The harness's child runs never take these actions on their own;
they remain parent-owned and require explicit approval.
