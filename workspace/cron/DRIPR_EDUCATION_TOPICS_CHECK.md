---
cron_id: dripr_education_topics_check
system_files:
  - capabilities/dripr_education_topics/DRIPR_EDUCATION_TOPICS.md
---

# DRIPR EDUCATION TOPICS CHECK CRON WRAPPER

Run Mira's monthly production check for next month's Dripr education topic. This
cron prompt is only the scheduler entrypoint; capability behavior lives in
`capabilities/dripr_education_topics/`.

Follow standing execution rules from `AGENTS.md` and tool conventions from
`TOOLS.md`.

## TASK

1. Read `capabilities/dripr_education_topics/DRIPR_EDUCATION_TOPICS.md` before any
   judgment or final output.
2. Run this exact helper with `exec`:

```bash
python3 capabilities/dripr_education_topics/dripr_education_topics.py check-next-month
```

3. If the helper output is exactly `NO_REPLY`, stop immediately and return
   exactly `NO_REPLY`. Do not explain.
4. If the helper output is JSON with `"status":"SETUP_REQUIRED"`, return:

```text
Mira education topic check needs setup before it can run.
```

5. If the helper output is JSON with `"status":"ERROR"`, return:

```text
Mira education topic check failed.
```

6. If the helper output is JSON with `"status":"OK"` and `"topic_exists":true`,
   return a short warm Mira message telling Kenny the next month's education
   topic is already in production. Include `target_label` and the topic `title`.
7. If the helper output is JSON with `"status":"OK"` and `"topic_exists":false`,
   return a short warm Mira message telling Kenny there is no education topic
   scheduled in production for `target_label` yet, and ask whether she should
   create one. Invite a simple **yes** reply so interactive Mira can start the
   `dripr-education-topics` skill.

## RULES

- Do not publish, generate images, sync-repo, or draft topics in this cron.
- Do not spawn a detached subagent.
- Do not create tasks, reminders, calendar events, notes, email, drafts, files,
  or memory.
- Do not use web search, browser tools, Gmail, Todoist, calendar, curl, or any
  network request other than the required helper behavior.
- Do not call Telegram or delivery tools. Return final visible text and let the
  scheduler deliver it.

## OUTPUT FORMAT

Return only one of:

- `NO_REPLY`
- A short ready message when `topic_exists` is true
- A short ask-to-create message when `topic_exists` is false
- `Mira education topic check needs setup before it can run.`
- `Mira education topic check failed.`
