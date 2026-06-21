---
capability_id: dripr_education_topics
---

# Dripr Education Topics

Use this capability inside **Interactive Mira** when Kenny asks to create,
upload, publish, or copy monthly Dripr education topics.

This workflow is intentionally interactive. It needs back-and-forth review of
title, copy, and image before publish. Do not spawn a detached subagent.

## Canonical Skill

After `sync-repo`, read the live Dripr skill:

```bash
/home/node/.openclaw/workspace/runtime/repos/dripr/.agent/skills/uploading-education-topics/SKILL.md
```

That file owns the creative rules, Bedrock image prompt shape, and review gate.
It also describes Kenny's local staging workflow. **Mira does not use the
staging publish path.** Mira publishes to production only through the Dripr API.
When Kenny explicitly asks to copy a production topic into staging for testing,
use `copy-to-staging` below.

## Copy Production Row To Staging

When Kenny asks to copy an education topic to staging:

1. Resolve `month` and `year`.
2. Run:
   ```bash
   python3 capabilities/dripr_education_topics/dripr_education_topics.py copy-to-staging \
     --month <month> --year <year>
   ```
3. If the helper returns `action: already_exists`, report that staging already
   has that month/year.
4. If the helper returns `action: copied`, confirm success. The copied row keeps
   the production `image_url`; that is expected for application-logic testing.

This reads prod from `env/prod.env`, checks staging through `env/staging.env`'s
`DATABASE_URL`, and inserts at most one matching row. It does not call staging
APIs or upload images.

## Publish Model

After Kenny approves, Mira calls:

```bash
POST $VITE_API_GATEWAY_URL/api/education-topics
```

using `DRIPR_API_KEY` and `VITE_API_GATEWAY_URL` from `env/prod.env`. The API
uploads the image to the production bucket and creates the `education_topics`
row. Mira does not write the database or S3 directly.

## Required Flow

1. Read this file and `capabilities/dripr_education_topics/README.md`.
2. Run:
   ```bash
   python3 capabilities/dripr_education_topics/dripr_education_topics.py check-config
   ```
3. Run:
   ```bash
   python3 capabilities/dripr_education_topics/dripr_education_topics.py sync-repo
   ```
4. Read Dripr's `uploading-education-topics` skill from the refreshed checkout.
5. Run:
   ```bash
   python3 capabilities/dripr_education_topics/dripr_education_topics.py recent-topics
   ```
6. Research, draft title/content, generate the PNG with `generate-image`, and present
   the review package to Kenny. Stop and wait for explicit approval.
   ```bash
   python3 capabilities/dripr_education_topics/dripr_education_topics.py generate-image \
     --title "<title>" \
     --visual-concept "<one concrete scene without text or labels>" \
     --output <draft.png>
   ```
7. Publish only after Kenny explicitly approves:
   ```bash
   python3 capabilities/dripr_education_topics/dripr_education_topics.py publish --kenny-approved \
     --month <month> --year <year> --title "<title>" --content "<content>" --image <draft.png>
   ```

Save drafts under:

```bash
/home/node/.openclaw/workspace/runtime/capability-runs/dripr-education-topics/
```

Do not use `dripr_coding.py prepare-repos` for this workflow.

## Review Gate

Before publish, show Kenny:

- month and year
- title
- content exactly as it will be stored
- image prompt used
- the generated PNG (attach/send the image)

If Kenny requests changes, update the draft and repeat the review gate.

## Safety Rules

- Do not publish without `--kenny-approved`.
- Do not publish to staging or call staging APIs.
- Do not write staging data except through `copy-to-staging` when Kenny explicitly asks.
- Do not bypass the production API with direct database or S3 writes.
- Do not expose API keys, env file contents, or raw credentials.
- If publish, copy, or verification fails, report the blocker and stop.

## Report Format

```text
Dripr education topic: <month/year title>

Status:
- <draft ready for review / published to prod / blocked>

What I did:
- `check-config`: <OK or blocker>
- `sync-repo`: <OK or blocker>
- `recent-topics`: <summary>
- image: <generated or pending>
- `publish`: <HTTP status, image URL, or blocker>

Result:
- <production image URL if published, or review draft details>

Next step:
- <revise draft / done>
```
