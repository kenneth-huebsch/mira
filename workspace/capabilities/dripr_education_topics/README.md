---
capability_id: dripr_education_topics
---

# Dripr Education Topics

Interactive workflow for generating and publishing Dripr's monthly education
topic. Kenny reviews title, copy, and image in chat before anything is published.

## Files

- `dripr_education_topics.py` - repo sync, recent-topic lookup, Bedrock image generation, and gated prod API publish
- `DRIPR_EDUCATION_TOPICS.md` - Mira-facing behavior for the interactive flow
- `../../skills/dripr-education-topics/SKILL.md` - interactive trigger

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
python3 capabilities/dripr_education_topics/dripr_education_topics.py recent-topics
python3 capabilities/dripr_education_topics/dripr_education_topics.py generate-image \
  --title "..." --visual-concept "..." --output /path/to/draft.png
python3 capabilities/dripr_education_topics/dripr_education_topics.py publish --kenny-approved \
  --month 7 --year 2026 --title "..." --content "..." --image /path/to/draft.png
```

## Safety Boundaries

- Interactive only. No detached subagent.
- No publish without `--kenny-approved`.
- Production API only. No staging env or staging publish.
- No credential or env dumps in chat output.
