# Maintain Mira's Harness Pin

Use this playbook whenever changing the `agent` repository, Mira's
`harness.lock.json`, or Mira's live harness checkout.

## Mental model

Keep these three states distinct:

1. `agent/main` is the latest repository history.
2. `workspace/skills/coding-harness/harness.lock.json` selects one exact,
   approved `agent` commit.
3. `workspace/runtime/repos/agent` is Mira's live detached checkout of that
   locked commit.

`refresh-harness` materializes the lock. It never discovers or follows a newer
`agent/main` commit.

## Default synchronization policy

Prefer visible alignment over technically equivalent revisions:

- Merge or push the intended `agent` change to `agent/main` first.
- Use the resulting full `origin/main` SHA in Mira's lock.
- Do not pin a PR-head commit before merge when a merge commit will become the
  durable `main` revision.
- After any intentional `agent/main` change made while maintaining Mira,
  including documentation cleanup, update Mira's pin by default. A docs-only
  change does not require a runtime update, but keeping the pin aligned avoids
  ambiguity. Leave it unchanged only when that choice is explicit.

Functional changes to runner code, policies, hooks, or skills must be pinned
before claiming Mira uses them.

## Update workflow

1. Work in a normal `agent` checkout, not Mira's live pinned runtime checkout.
2. Test and land the `agent` change.
3. Fetch `agent/main` and record its full 40-character SHA.
4. Confirm the landed commit contains the intended tree.
5. Update Mira's `workspace/skills/coding-harness/harness.lock.json`.
6. Run Mira's adapter and restore tests.
7. Land the Mira lock update.
8. Align the local Mira blueprint with merged `main`.
9. Run `scripts/restore-to-live.sh`.
10. In Mira's container, as `node`, run:

```bash
python3 /home/node/.openclaw/workspace/skills/coding-harness/coding_harness.py refresh-harness
python3 /home/node/.openclaw/workspace/skills/coding-harness/coding_harness.py check-config
```

11. Verify the live checkout's `HEAD` exactly equals the lock SHA and remains
    detached and clean.

## Interpretation rules

- A newer `agent/main` does not mean Mira is outdated unless the lock was meant
  to consume that change.
- A successful refresh with an old lock correctly keeps the old revision.
- Identical Git tree hashes mean two commits have identical files, but they are
  still different revisions. Prefer pinning the merged `main` revision so the
  visible SHA tells a simple story.
- Never manually edit, pull, switch, or develop inside Mira's live harness
  checkout. Its state is owned by the lock and `refresh-harness`.

## Completion report

Report all four values:

- landed `agent/main` SHA;
- Mira lock SHA;
- live harness `HEAD`;
- `check-config` result.

Do not say Mira is updated unless the last three SHAs match the intended landed
revision.
