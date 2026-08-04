---
name: collaborative-planning
description: Use when Kenny wants involvement in architecture, planning, tradeoffs, or product direction, or asks whether a coding proposal is worthwhile, overengineered, temporary, or missing a material risk.
origin: adapted-from-agent-harness
---

# Collaborative Planning

Use this skill when Kenny wants Mira to help choose the direction of a coding
project, not merely relay an implementation prompt.

## Planning Contract

Mira should:

- identify the target repository and read its local instructions first
- research the relevant code and docs before proposing changes
- identify constraints, success criteria, and approval boundaries
- present meaningful options only when they would materially change the plan
- recommend a default with concrete reasons
- ask only questions whose answers affect the implementation
- wait for approval before moving from planning to implementation

Do not ask Kenny for trivial details that can be inferred safely from the
repository.

## Workflow

1. Summarize the current system shape and the requested outcome.
2. Identify architecture, product, compatibility, data, rollout, or risk
   decisions that materially affect the work.
3. When a decision matters, present two or three viable options with tradeoffs
   and recommend one.
4. Turn the agreed direction into a concise implementation plan with files or
   areas to inspect, ordered work, verification, risks, non-goals, and gated
   actions.
5. For larger work, use `skills/blueprint/SKILL.md` to make each phase
   independently understandable and verifiable.
6. Hand approved implementation to `skills/coding-harness/SKILL.md`.

## Pressure-Test Proposals

When Kenny asks whether a proposal is worthwhile, temporary, missing a risk, or
overengineered, evaluate the decision rather than validating its premise. Give:

1. the strongest case for the proposal
2. the strongest case against it or for the smallest adequate alternative
3. the concrete failure mode if the recommendation is wrong
4. a verdict: do it, do not do it, or do a named smaller version

Compare the full proposal with both the smallest adequate version and doing
nothing. Name the measurable condition that would justify revisiting a smaller
decision later.

## Execution Boundary

This skill plans; it does not bypass Mira's coding-harness adapter. Do not
invoke the harness runner directly, edit a target repository, or start an
unapproved phase plan from this skill. External mutations remain separately
gated.
