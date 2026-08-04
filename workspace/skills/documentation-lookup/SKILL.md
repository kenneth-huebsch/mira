---
name: documentation-lookup
description: Use when coding-project planning depends on current external APIs, framework behavior, package versions, release notes, or platform-specific instructions.
origin: adapted-from-agent-harness
---

# Documentation Lookup

Use this skill to keep a coding plan from relying on stale model memory.

## When To Use

- a library or service is new or unfamiliar
- an API or framework changed recently
- configuration, deployment, authentication, billing, or cloud behavior is
  version-sensitive
- an error names version-specific behavior
- an integration is security-sensitive

## Process

1. Identify the exact library, service, framework, version, and feature from the
   repository before searching.
2. Prefer official documentation, specifications, and release notes.
3. Use secondary sources only to fill gaps or locate the primary source.
4. Record the relevant constraint and source in the plan or final answer.
5. If current documentation conflicts with established repository patterns,
   explain the discrepancy and recommend the safest compatible choice.

## Boundaries

- Treat documentation lookup as read-only.
- Never paste secrets, credentials, private repository content, or personal
  data into an external search or documentation service.
- Ask before signing in, creating resources, or changing external
  configuration.
- Do not turn research into implementation; approved coding work still routes
  through `skills/coding-harness/SKILL.md`.
