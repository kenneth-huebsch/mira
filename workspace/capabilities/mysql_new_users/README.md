# MySQL New Users

This capability lets Mira check Kenny's product database every morning for new
users and send a short Telegram summary only when there is something to report.

## Files

- `mysql_new_users.py` - deterministic helper that loads live-only MySQL
  configuration, runs Kenny's read-only query, and emits compact JSON or
  `NO_REPLY`.
- `MYSQL_NEW_USERS.md` - Mira-facing behavior for turning helper JSON into a
  concise summary.
- `../../cron/MYSQL_NEW_USERS.md` - scheduler wrapper.

## Live-Only Configuration

Create this file on the live Mira host:

```bash
/home/kenny/mira/.openclaw/secrets/mysql-new-users.env
```

Inside the OpenClaw container this is read as:

```bash
/home/node/.openclaw/secrets/mysql-new-users.env
```

Required values:

```bash
MYSQL_HOST=
MYSQL_PORT=3306
MYSQL_DATABASE=
MYSQL_USER=
MYSQL_PASSWORD=
MYSQL_NEW_USERS_QUERY='SELECT id, email, created_at FROM users WHERE created_at >= %(since_utc)s ORDER BY created_at DESC LIMIT %(limit)s'
```

Optional values:

```bash
MYSQL_NEW_USERS_SINCE_HOURS=25
MYSQL_NEW_USERS_MAX_ROWS=25
MYSQL_NEW_USERS_FIELDS=id,email,created_at
MYSQL_SSL_CA=/home/node/.openclaw/secrets/mysql-ca.pem
```

Use `MYSQL_NEW_USERS_QUERY_FILE=/home/node/.openclaw/secrets/mysql-new-users.sql`
instead of `MYSQL_NEW_USERS_QUERY` if the SQL is easier to maintain as a file.
Do not put credentials, DSNs, private query output, or production schema details
in tracked files unless Kenny explicitly decides they are safe to store.

## Query Contract

The helper accepts only a single read-only `SELECT` or `WITH` query. It provides
these named parameters:

- `%(since_utc)s`
- `%(since_et)s`
- `%(now_utc)s`
- `%(now_et)s`
- `%(limit)s`

The query should return only fields that are safe for Mira to summarize to
Kenny. Keep the output small and human-useful: signup time, email or name if
allowed, plan/source/status, and flags that need attention.

## Manual Checks

From Mira's OpenClaw workspace inside the gateway runtime:

```bash
python3 capabilities/mysql_new_users/mysql_new_users.py check-config
python3 capabilities/mysql_new_users/mysql_new_users.py review
```

`NO_REPLY` means no matching users were found. `SETUP_REQUIRED` means the
live-only env file, SQL, or Python MySQL driver still needs to be configured.
The helper uses `/home/node/.openclaw/secrets/...` container paths and should
not depend on host-only paths or host-installed Python packages.
