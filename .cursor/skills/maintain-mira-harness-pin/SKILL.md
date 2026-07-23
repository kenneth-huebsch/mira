---
name: maintain-mira-harness-pin
description: Maintains synchronization between the agent repository, Mira's harness.lock.json, and Mira's live detached harness checkout. Use whenever changing or merging the agent repo, updating Mira's harness pin, running refresh-harness, or diagnosing mismatched harness SHAs.
---

# Maintain Mira's Harness Pin

Read and follow `docs/agent-playbooks/maintain-harness-pin.md`.

Key rule: land the intended `agent` change first, then pin Mira to the full
merged `agent/main` SHA, restore the blueprint, run `refresh-harness`, and verify
that the lock and live detached checkout match.

Prefer updating the pin after any intentional `agent/main` maintenance change,
including documentation cleanup, unless leaving it unchanged is an explicit
decision. Never develop in Mira's live pinned harness checkout.
