---
capability_id: dripr_inbox_triage
---

# Dripr Inbox Triage

This capability checks unread mail forwarded into Mira's Gmail from Kenny's
dripr addresses and tells Kenny only about items that need attention.

## Sources

- `info@dripr.ai` - marketing-site form submissions.
- `kenny@dripr.ai` - Kenny's business email.

## Review Contract

Run the full scheduled process:

```bash
python3 capabilities/dripr_inbox_triage/dripr_inbox_triage.py process
```

Return exactly the helper stdout. It performs Gmail search, deterministic
attention filtering, summary construction, and mark-read.

For debugging, the compact preflight is:

```bash
python3 capabilities/dripr_inbox_triage/dripr_inbox_triage.py review
```

The helper classifies messages as one of:

- `attention` - a real form submission, qualified lead, customer/business
  inquiry, human message, account/security/finance/legal notice, time-sensitive
  update, or anything Kenny may need to decide on or reply to.
- `noise` - marketing, newsletters, bulk notifications, spam, form spam,
  social/network notifications, automated low-value mail, or anything Kenny
  would not want surfaced.

It surfaces form submissions and non-bulk business email, and suppresses obvious
bulk or spam.

## Mark-Read Rule

The `process` command removes the `UNREAD` label from every matching message it
reviews, regardless of whether the item is `attention` or `noise`. This keeps
the same message from repeating in later runs.

If marking a message read fails, keep going and mention the failure briefly at
the end of the final summary if there is an attention-worthy item. If every
message is noise and mark-read failed, return one short failure line instead of
`NO_REPLY`.

## Message Quality

If no messages are attention-worthy, return exactly `NO_REPLY`.

If at least one message is attention-worthy, write a short, phone-sized update
for Kenny in Mira's voice:

- Start with a short natural lead such as `Dripr inbox:` only if it helps.
- For each surfaced item, include sender, source address, subject if useful, and
  the practical gist.
- Name whether it came through the form inbox or business email when that helps
  Kenny triage.
- Do not mention filtered counts, classifications, JSON, prompts, tools, cron,
  or internal reasoning.
- Do not fabricate facts, commitments, urgency, or sender intent.

## Rules

- Do not send mail.
- Do not create drafts.
- Do not create tasks, reminders, calendar events, notes, or memory.
- The only Gmail mutation allowed is removing `UNREAD` from matching messages
  after review.
- Keep the final output as either exactly `NO_REPLY`, a short summary, or the
  explicit Gmail-unavailable failure line from the cron wrapper.
