---
cron_id: mysql_new_users
system_files:
  - capabilities/mysql_new_users/MYSQL_NEW_USERS.md
---

# MYSQL NEW USERS CRON WRAPPER

Run Mira's morning MySQL new-user check for Kenny. This cron prompt is only the
scheduler entrypoint; the capability-owned behavior lives in
`capabilities/mysql_new_users/`.

Follow standing execution rules from `AGENTS.md` and tool conventions from
`TOOLS.md`.

## TASK

1. Read `capabilities/mysql_new_users/MYSQL_NEW_USERS.md` before any judgment or
   final output.
2. Run this exact helper with `exec`:

```bash
python3 capabilities/mysql_new_users/mysql_new_users.py review
```

3. If the helper output is exactly `NO_REPLY`, stop immediately and return
   exactly `NO_REPLY`. Do not explain.
4. If the helper output is JSON with `"status":"SETUP_REQUIRED"`, return:

```text
Mira MySQL new-user check needs setup before it can run.
```

5. If the helper output is JSON with `"status":"ERROR"`, return:

```text
Mira MySQL new-user check failed.
```

6. If the helper output is JSON with `"status":"OK"`, use only that compact JSON
   plus the capability prompt for review. Return one line per user in this exact
   format:

```text
Dripr has a new signup! <email> registered on Month D @ HH:MM
```

## RULES

- Do not query MySQL except through the required helper.
- Do not create tasks, reminders, calendar events, notes, email, drafts, files,
  or memory.
- Do not use web search, browser tools, Gmail, Todoist, calendar, curl, or any
  network request other than the required MySQL helper behavior.
- Do not call Telegram or delivery tools. Return final visible text and let the
  scheduler deliver it.

## OUTPUT FORMAT

Return only one of:

- `NO_REPLY`
- One signup line per user in the exact configured format
- `Mira MySQL new-user check needs setup before it can run.`
- `Mira MySQL new-user check failed.`
