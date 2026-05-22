---
capability_id: mysql_new_users
---

# MySQL New Users

This capability summarizes new users from Kenny's MySQL database. The helper
does all database access and returns compact JSON. Mira should only use the
helper payload and this behavior file for the final message.

## Daily Check Contract

Run:

```bash
python3 capabilities/mysql_new_users/mysql_new_users.py review
```

If the helper prints exactly `NO_REPLY`, return exactly:

```text
👨 No new Dripr signups today.
```

This is a daily heartbeat — it confirms the check ran with nothing to report.

If the helper prints JSON with `"status":"SETUP_REQUIRED"`, return:

```text
Mira MySQL new-user check needs setup before it can run.
```

If the helper prints JSON with `"status":"ERROR"`, return:

```text
Mira MySQL new-user check failed.
```

If the helper prints JSON with `"status":"OK"`, write the configured signup
line for each user in `users`.

## Message Quality

Use the helper payload as the source of truth. For each user, return exactly:

```text
Dripr has a new signup! <email> registered on Month D @ HH:MM
```

Formatting rules:

- Replace `<email>` with the user's `email` value.
- Format `creation_datetime` with the full English month name, unpadded day,
  24-hour hour, and two-digit minute, for example `May 10 @ 18:16`.
- If there are multiple users, return one signup line per user.
- If `truncated` is true, add one final line: `There are more signups not shown.`
- Do not include raw JSON, SQL, credentials, hostnames, internal file paths, or
  tool output.

Avoid:

- Inventing trends, causes, lead quality, or user details not present in the
  helper JSON.
- Adding greetings, explanations, summaries, bullets, or extra commentary.
- Suggesting outreach or operational actions unless the data clearly indicates
  something needs Kenny's attention.
- Creating tasks, reminders, files, notes, emails, calendar events, or memory.

## Rules

- Do not query the database directly. The helper is the only allowed database
  access for this cron.
- Do not write files or memory.
- Do not use web search, browser tools, Gmail, Todoist, calendar, curl, or any
  network request other than the required MySQL helper behavior.
- Do not call Telegram or delivery tools. Return final visible text and let the
  scheduler deliver it.
