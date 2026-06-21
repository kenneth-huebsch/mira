---
name: dripr-education-topics
description: Create and publish monthly Dripr education topics with Kenny's review. Use when Kenny asks to create, upload, publish, or draft Expert Tips education content or the monthly email footer topic. Also use when Kenny asks to copy a production education topic into the staging database for local testing.
user-invocable: true
---

# Dripr Education Topics

Use this skill when Kenny wants Mira to draft and publish Dripr's monthly
education topic. This is an **interactive** workflow. Stay in the main Mira
session, go back and forth with Kenny, and do not spawn a detached subagent.

Mira publishes to **production only** through the Dripr API. She does not call
staging APIs or publish to staging through the API. The one allowed staging
exception is copying an existing production education-topic row into
`dripr-staging` when Kenny explicitly asks.

## Quick Start

1. Read `capabilities/dripr_education_topics/DRIPR_EDUCATION_TOPICS.md`.
2. Run:
   ```bash
   python3 capabilities/dripr_education_topics/dripr_education_topics.py check-config
   python3 capabilities/dripr_education_topics/dripr_education_topics.py sync-repo
   ```
3. Read the canonical Dripr skill from the refreshed checkout:
   `.agent/skills/uploading-education-topics/SKILL.md`
   Follow it for research, copy, image generation, and review. For publish, use
   the Mira helper below instead of the Dripr skill's staging section.
4. Run:
   ```bash
   python3 capabilities/dripr_education_topics/dripr_education_topics.py recent-topics
   ```
5. Draft title and content per the Dripr skill.
6. Generate the PNG with the helper (do not improvise a separate Bedrock script):
   ```bash
   python3 capabilities/dripr_education_topics/dripr_education_topics.py generate-image \
     --title "<title>" \
     --visual-concept "<one concrete scene without text or labels>" \
     --output /home/node/.openclaw/workspace/runtime/capability-runs/dripr-education-topics/<year-month>/draft.png
   ```
   Use `--prompt` only when you need a full custom prompt override.
7. Present the review package to Kenny and stop for approval.
8. After Kenny approves, publish to production:
   ```bash
   python3 capabilities/dripr_education_topics/dripr_education_topics.py publish --kenny-approved \
     --month <month> --year <year> --title "<title>" --content "<content>" --image <draft.png>
   ```

## Review Package

Before publish, show Kenny:

- month and year
- title
- content exactly as it will be stored
- image prompt used
- the generated PNG itself (attach/send the image)

If Kenny wants changes, revise and repeat the review gate. Do not publish until
he explicitly approves the exact copy and image.

## Monthly Cron Follow-up

The Dripr Education Topics Check cron runs daily at 10:30 AM Eastern but only
notifies Kenny on the monthly trigger day (14 days before month-end). When that
cron finds no topic for next month, it asks whether Mira should create one.

If Kenny replies **yes** (or otherwise clearly approves creating the topic) in
interactive chat after that alert, use this skill immediately for the target
month and year from the cron context. Do not wait for a separate explicit
create request.

## Copy Production Topic To Staging

Use this only when Kenny explicitly asks to copy an education topic to staging,
for example: "copy the education topic to staging".

1. Resolve the target `month` and `year` from Kenny's request or recent context.
   Ask if it is unclear.
2. Run:
   ```bash
   python3 capabilities/dripr_education_topics/dripr_education_topics.py copy-to-staging \
     --month <month> --year <year>
   ```
3. If the helper returns `action: already_exists`, tell Kenny staging already
   has that month/year and do not insert again.
4. If the helper returns `action: copied`, confirm the staging row was created.
   The `image_url` will still point at the production S3 object; that is expected
   for local application-logic testing.

This command reads production from `env/prod.env` and writes only to
`dripr-staging` through `env/staging.env`'s `DATABASE_URL`. It does not call
staging APIs or upload images.

## Draft Storage

Save drafts under:

```bash
/home/node/.openclaw/workspace/runtime/capability-runs/dripr-education-topics/<year-month>/
```

Do not use `dripr_coding.py prepare-repos` in this workflow.

## Credentials

Use Dripr **`env/prod.env`** for production publish, research, and prod reads.

For the explicit `copy-to-staging` command only, the helper also reads
`DATABASE_URL` from **`env/staging.env`**. Do not use staging env files for any
other education-topic workflow.

## Hard Stops

- Do not spawn a detached subagent for this workflow.
- Do not publish without `--kenny-approved`.
- Do not publish to staging or call staging APIs.
- Do not write staging data except through `copy-to-staging` when Kenny explicitly asks.
- Do not bypass the production API with direct database or S3 writes.
- Do not improvise separate Bedrock image scripts; use `generate-image`.
- Do not expose API keys, env contents, or credentials.
