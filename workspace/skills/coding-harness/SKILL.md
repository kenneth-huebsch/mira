---
name: coding-harness
description: Routes non-Mira coding requests through Kenny's private agent harness and Cursor CLI. Use when Kenny asks Mira to implement, fix, refactor, test, or review code in a repository other than Mira itself.
---

# Coding Harness

Use this skill for coding work in repositories other than Mira's own repo/home.
Do not use it for changes to `/home/kenny/mira`, Mira's OpenClaw runtime, or
Mira behavior files; self-work belongs to a separate future skill.

## Workflow

1. Identify the target repository. If Kenny did not provide a path, repo URL, or
   GitHub `owner/repo`, ask for it.
2. Run the preflight:

   ```bash
   python3 capabilities/coding_harness/coding_harness.py check-config
   ```

   If this reports missing Cursor CLI auth, Kenny must authenticate Cursor CLI
   in Mira's runtime before coding runs can execute.

3. Refresh the harness:

   ```bash
   python3 capabilities/coding_harness/coding_harness.py refresh-harness
   ```

4. Start the Cursor CLI harness run:

   ```bash
   python3 capabilities/coding_harness/coding_harness.py run --target <path-or-repo> --prompt "<Kenny's coding request>"
   ```

5. Report the helper's final output to Kenny. Include blockers, changed files,
   verification, and any required approval gate.

## Target Rules

- Accepted targets: container-visible paths, GitHub URLs, or GitHub `owner/repo`
  slugs.
- Repositories cloned by the helper live under
  `/home/node/.openclaw/workspace/runtime/repos/`.
- The helper must reject Mira self-work targets.
- Do not push, deploy, rotate credentials, or mutate external systems unless
  Kenny explicitly asks and the harness run reports that approval gate clearly.
