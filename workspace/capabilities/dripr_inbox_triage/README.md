# Dripr Inbox Triage Capability

Dripr Inbox Triage is Mira's scheduled check for mail forwarded into her Gmail
from Kenny's dripr addresses.

## Files

- `DRIPR_INBOX_TRIAGE.md` - capability-owned review behavior and final summary
  contract.
- `dripr_inbox_triage.py` - deterministic Gmail process and preflight helper.

## Sources

- `info@dripr.ai` - marketing-site form submissions.
- `kenny@dripr.ai` - Kenny's business email.

The helper resolves the original source address from forwarding headers first:
`X-Pm-Forwarded-From`, `X-Original-To`, then `To`.

## Cron Boundary

`workspace/cron/` remains the scheduler entrypoint folder. The cron wrapper
`cron/DRIPR_INBOX_TRIAGE.md` should stay thin: read the capability prompt, run
the helper, handle `NO_REPLY`, and return Mira's final user-facing text.

Capability behavior and deterministic Gmail plumbing belong here.

## Gmail Boundary

This capability is summary-only. It may:

- Search unread Gmail messages.
- Fetch full Gmail messages.
- Remove `UNREAD` from matching messages after review.

It must not:

- Send mail.
- Create drafts.
- Create tasks, reminders, calendar events, notes, or memory.
- Touch unrelated Gmail messages.

## Runtime Wiring

Mira's active Gmail account is documented in `TOOLS.md`. The helper defaults to
`mira.agentops@gmail.com` and can be overridden with `MIRA_GMAIL_ACCOUNT` or
`GOG_ACCOUNT` if the account changes.

OpenClaw `exec` for Mira runs inside the gateway container. This helper expects
container-provided runtime tools such as `gog`; it must not shell out through
Docker or depend on host-installed CLI binaries.

## Debugging

From Mira's OpenClaw workspace, check Google Workspace auth:

```bash
gog auth list
```

Run the preflight helper without marking mail read:

```bash
python3 capabilities/dripr_inbox_triage/dripr_inbox_triage.py review
```

Mark a reviewed message read through the same helper:

```bash
python3 capabilities/dripr_inbox_triage/dripr_inbox_triage.py mark-read <message_id>
```

Run the full cron-owned process:

```bash
python3 capabilities/dripr_inbox_triage/dripr_inbox_triage.py process
```
