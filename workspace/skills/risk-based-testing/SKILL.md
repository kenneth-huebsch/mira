---
name: risk-based-testing
description: Use when deciding how much test coverage or test-first discipline a planned coding change needs, including features, bug fixes, refactors, and migrations.
origin: adapted-from-agent-harness
---

# Risk-Based Testing

Choose testing proportional to the behavior's risk. Do not impose universal
test-driven development or a fixed coverage percentage.

## Prefer A Regression Test First

- a bug has a clear reproduction
- shared business logic or a public contract changes
- authentication, authorization, payments, data integrity, migrations, or
  background jobs are involved
- a refactor must preserve behavior
- user-facing regressions would be expensive
- multiple implementations must remain consistent, such as mock and production
  paths or cached and uncached behavior

For a reproducible bug, define a check that fails for the bug, make the smallest
fix, rerun the check, and retain it when it protects a real invariant.

## Prefer Focused Verification

- documentation-only edits
- formatting or mechanical cleanup
- tiny local changes with low blast radius
- policy or configuration changes where schema or structure validation is more
  useful than application tests

## Planning Process

1. Identify the behavior, blast radius, and dominant failure mode.
2. Read repository-local testing rules and existing test patterns.
3. Choose the narrowest mechanical check that would catch the likely failure.
4. Give every implementation phase an explicit verification command or manual
   check.
5. Broaden the suite only when shared behavior, contracts, or risk justify it.

AI-written fixes often preserve the same blind spot during self-review. Give
special attention to missing response fields on one code path, mock/production
drift, generated contract drift, frontend/backend shape mismatch, optimistic
rollback, and cache invalidation.

Treat a failing check as evidence. Inspect setup, fixtures, environment, mocks,
cached state, and command usage before deciding whether the implementation or
the test is wrong.

This skill chooses verification for the plan. Actual implementation and test
execution remain delegated through `skills/coding-harness/SKILL.md`.
