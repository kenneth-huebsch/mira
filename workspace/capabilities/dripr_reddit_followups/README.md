# Dripr Reddit Follow-Ups

This capability lets Mira check Kenny's Airtable Reddit scrape table twice daily
for rows that still need a marketing follow-up.

## Skill Dependency

Install the ClawHub `native-airtable` skill in Mira's workspace:

```bash
cd /home/kenny/mira
./scripts/openclaw-cli.sh skills install native-airtable
```

The helper wraps `skills/native-airtable/scripts/airtable.py`; it does not call
Airtable directly.

## Files

- `dripr_reddit_followups.py` - deterministic helper that loads live-only config,
  discovers the Airtable table, filters rows where `followed_up` is `no`, and
  emits compact JSON or `NO_REPLY`.
- `DRIPR_REDDIT_FOLLOWUPS.md` - Mira-facing behavior for turning helper JSON into
  a concise Kenny-facing summary.
- `../../cron/DRIPR_REDDIT_FOLLOWUPS.md` - scheduler wrapper.

## Live-Only Configuration

Create this file on the live Mira host:

```bash
/home/kenny/mira/.openclaw/secrets/dripr-reddit-airtable.env
```

Inside the OpenClaw container this is read as:

```bash
/home/node/.openclaw/secrets/dripr-reddit-airtable.env
```

Required values:

```bash
AIRTABLE_PAT=pat_your_token_here
AIRTABLE_BASE_ID=appmU4swFIn5T7d3U
```

Optional values:

```bash
AIRTABLE_TABLE_ID=
AIRTABLE_TABLE_NAME=
DRIPR_REDDIT_FOLLOWUPS_MAX_ROWS=3
```

Create the PAT at `https://airtable.com/create/tokens` with:

- scopes: `data.records:read`, `schema.bases:read`
- access: base `appmU4swFIn5T7d3U`

If the base has more than one table containing `followed_up`, `why_relevant`, and
`url`, set `AIRTABLE_TABLE_ID` or `AIRTABLE_TABLE_NAME`.

Keep the PAT, record contents, and private Airtable data out of tracked files.

## Manual Checks

From Mira's OpenClaw workspace inside the gateway runtime:

```bash
python3 capabilities/dripr_reddit_followups/dripr_reddit_followups.py check-config
python3 capabilities/dripr_reddit_followups/dripr_reddit_followups.py review
```

`NO_REPLY` means no rows currently need follow-up. `SETUP_REQUIRED` means the
PAT, skill install, or table discovery still needs configuration.
