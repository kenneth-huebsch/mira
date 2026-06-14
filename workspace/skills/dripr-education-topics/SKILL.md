---
name: dripr-education-topics
description: Create and publish monthly Dripr education topics with Kenny's review. Use when Kenny asks to create, upload, publish, or draft Expert Tips education content or the monthly email footer topic.
user-invocable: true
---

# Dripr Education Topics

Use this skill when Kenny wants Mira to draft and publish Dripr's monthly
education topic. This is an **interactive** workflow. Stay in the main Mira
session, go back and forth with Kenny, and do not spawn a detached subagent.

Mira publishes to **production only** through the Dripr API. She does not read
`env/staging.env`, does not call staging APIs, and does not publish to staging.
Staging preview is Kenny-only and out of scope for Mira.

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

## Draft Storage

Save drafts under:

```bash
/home/node/.openclaw/workspace/runtime/capability-runs/dripr-education-topics/<year-month>/
```

Do not use `dripr_coding.py prepare-repos` in this workflow.

## Credentials

Use Dripr **`env/prod.env` only**:

- `DATABASE_URL` for recent-topic research and post-publish verification
- `DRIPR_API_KEY` and `VITE_API_GATEWAY_URL` for production publish
- `AWS_ACCESS_KEY`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION` for Bedrock image generation

Mira never reads `env/staging.env`.

## Hard Stops

- Do not spawn a detached subagent for this workflow.
- Do not publish without `--kenny-approved`.
- Do not publish to staging or read staging env files.
- Do not bypass the API with direct database or S3 writes.
- Do not improvise separate Bedrock image scripts; use `generate-image`.
- Do not expose API keys, env contents, or credentials.
