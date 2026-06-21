---
capability_id: dripr_education_topics
---

# Dripr Education Topics

Interactive workflow for generating and publishing Dripr's monthly education
topic. Kenny reviews title, copy, and image in chat before anything is published.

## Files

- `dripr_education_topics.py` - repo sync, next-month prod check, prod-to-staging copy, recent-topic lookup, Bedrock image generation, and gated prod API publish
- `DRIPR_EDUCATION_TOPICS.md` - Mira-facing behavior for the interactive flow
- `../../skills/dripr-education-topics/SKILL.md` - interactive trigger
- `../../cron/DRIPR_EDUCATION_TOPICS_CHECK.md` - monthly scheduler wrapper

## Publish Model

Mira publishes to **production only** through `POST /api/education-topics`.
Credentials come from `env/prod.env` (`DRIPR_API_KEY`, `VITE_API_GATEWAY_URL`).
The API handles S3 upload and database insert. Mira does not publish to staging.

## Live-Only Paths

Dripr checkout:

```bash
/home/node/.openclaw/workspace/runtime/repos/dripr
```

Draft workspace:

```bash
/home/node/.openclaw/workspace/runtime/capability-runs/dripr-education-topics
```

Optional overrides:

```bash
/home/node/.openclaw/secrets/dripr-education-topics.env
```

## Helper Commands

```bash
python3 capabilities/dripr_education_topics/dripr_education_topics.py check-config
python3 capabilities/dripr_education_topics/dripr_education_topics.py sync-repo
python3 capabilities/dripr_education_topics/dripr_education_topics.py check-next-month
python3 capabilities/dripr_education_topics/dripr_education_topics.py recent-topics
python3 capabilities/dripr_education_topics/dripr_education_topics.py generate-image \
  --title "..." --visual-concept "..." --output /path/to/draft.png
python3 capabilities/dripr_education_topics/dripr_education_topics.py publish --kenny-approved \
  --month 7 --year 2026 --title "..." --content "..." --image /path/to/draft.png
python3 capabilities/dripr_education_topics/dripr_education_topics.py copy-to-staging \
  --month 7 --year 2026
```

`copy-to-staging` reads the production row for the requested month/year, checks
whether staging already has that month/year, and inserts a matching row only
when missing. The copied `image_url` remains the production S3 URL by design.

`check-next-month` prints `NO_REPLY` except on the monthly trigger day (14 days
before month-end in Eastern time). On that day it queries production through
Dripr `env/prod.env` and returns JSON indicating whether next month's topic
exists.

## Safety Boundaries

- Interactive only. No detached subagent.
- No publish without `--kenny-approved`.
- Production API only. No staging API publish.
- `copy-to-staging` is the only allowed staging DB write, and only when Kenny explicitly asks.
- No credential or env dumps in chat output.
