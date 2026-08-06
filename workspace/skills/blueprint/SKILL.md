---
name: blueprint
description: Use to turn a complex multi-session or multi-phase coding objective into a cold-start implementation plan with dependency ordering, verification, and approval gates.
origin: adapted-from-agent-harness
---

# Blueprint

Use this skill when a coding objective is too large or risky to execute safely
from one loose prompt.

## When To Use

- A feature needs multiple independently reviewable phases.
- A refactor or migration spans several sessions.
- Workstreams have dependencies or shared-file conflicts.
- A fresh agent will need enough context to continue later.

Do not use it for tiny tasks, single-file edits, or work that is already
well-scoped for one coding-harness run.

## Blueprint Pipeline

1. **Research:** Read repository instructions, relevant code and docs, existing
   plans, architecture notes, and available test commands.
2. **Design:** Break the objective into ordered phases with dependency edges,
   shared-file conflicts, risks, and recovery notes.
3. **Draft:** Give every phase enough context for a cold implementation agent.
4. **Review:** Check the plan adversarially for missing dependencies, vague done
   conditions, oversized phases, weak verification, and hidden gated actions.
5. **Present:** Summarize sequencing, any safe parallelism, risks, non-goals,
   and actions requiring approval.

## Phase Requirements

Each phase should include:

- a stable ID and one dominant goal
- the context a fresh agent needs
- exact files or areas to inspect
- specific implementation actions
- a mechanical verification command or concrete manual check
- a clear done condition
- dependencies and shared-file constraints
- rollback or recovery notes when applicable
- any separately gated action
- explicit negation of delivery actions when they must be mentioned
- symbolic routing tier, task class, concrete reason, risk flags, and bounded
  allowed paths. Use `cheap` only when the phase is mechanical and
  deterministic; otherwise choose `default` or `reasoning` conservatively.

Avoid phases that say only "implement the feature," rely on unstated
conversation context, or claim parallelism while touching the same files.
Child prompts and done conditions must never assign commit, push, pull request,
merge, publish, release, or deploy actions. Omit those actions or state only an
explicit negation such as "Do not commit or push." Final delivery is parent-owned
after the whole plan is green; it is never a per-phase outcome.

## Handoff To Execution

After Kenny agrees to the plan, translate it into the schema documented by
`skills/coding-harness/SKILL.md` under
`runtime/coding-harness-plans/<name>.json`. Run `preflight-plan`, show the
returned normalized spec and hash, and obtain explicit approval for that exact
result before delegating it through the coding-harness adapter. Any phase-spec
file edit invalidates the approval and requires a new preflight, display, and
approval.

This skill never invokes the harness runner directly and never commits, pushes,
opens a pull request, deploys, or mutates an external system.
