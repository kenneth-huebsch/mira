---
cron_id: upcoming_dates
---

# UPCOMING DATES REMINDER

Check whether any important date for Kenny is exactly N days from today and
ping him on Telegram if so. **Lookahead window: 7 days.**

Follow standing execution rules from `AGENTS.md`. Use `gog` per `TOOLS.md` —
the `Copied Birthdays` calendar id is resolved at runtime via
`gog calendar calendars --json` (see `TOOLS.md`).

---

## TASK

Run this exact command once with `exec`, then return only its stdout as the
final assistant text. Do not use web search, do not make extra date/tool calls,
and do not narrate what you are doing.

```bash
python3 - <<'PY'
import json
import subprocess
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

ACCOUNT = "rumi.openclaw@gmail.com"
LOOKAHEAD_DAYS = 7
TZ = ZoneInfo("America/New_York")


def run_json(args):
    last_error = None
    for _ in range(2):
        proc = subprocess.run(args, text=True, capture_output=True)
        if proc.returncode == 0:
            try:
                return json.loads(proc.stdout)
            except json.JSONDecodeError as exc:
                last_error = str(exc)
        else:
            last_error = proc.stderr.strip() or proc.stdout.strip()
    raise RuntimeError(last_error or "command failed")


def entries(data, *keys):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in keys:
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []


def nth_weekday(year, month, weekday, n):
    current = date(year, month, 1)
    offset = (weekday - current.weekday()) % 7
    return current + timedelta(days=offset + 7 * (n - 1))


try:
    today = datetime.now(TZ).date()
    target = today + timedelta(days=LOOKAHEAD_DAYS)
    target_from = datetime.combine(target, time.min, TZ).isoformat()
    target_to = datetime.combine(target, time(23, 59, 59), TZ).isoformat()
    target_mmdd = target.strftime("%m-%d")
    target_human = target.strftime("%A, %b ") + str(target.day)

    calendars = entries(
        run_json(["gog", "calendar", "calendars", "--json", "--account", ACCOUNT]),
        "calendars",
        "items",
    )
    birthday_calendar = next(
        (
            cal
            for cal in calendars
            if "copied birthdays"
            in (cal.get("summaryOverride") or cal.get("summary") or "").lower()
        ),
        None,
    )
    if not birthday_calendar:
        raise RuntimeError("Copied Birthdays calendar unavailable")

    events = entries(
        run_json(
            [
                "gog",
                "calendar",
                "events",
                birthday_calendar["id"],
                "--from",
                target_from,
                "--to",
                target_to,
                "--json",
                "--account",
                ACCOUNT,
            ]
        ),
        "events",
        "items",
    )

    items = []
    for event in events:
        name = (event.get("summary") or "").strip()
        if name:
            items.append(f"🎂 {name}'s birthday")

    fixed_holidays = {
        "02-14": "💘 Valentine's Day",
        "03-17": "🍀 St. Patty's Day",
    }
    if target_mmdd in fixed_holidays:
        items.append(fixed_holidays[target_mmdd])

    if target == nth_weekday(target.year, 5, 6, 2):
        items.append("💐 Mother's Day")
    if target == nth_weekday(target.year, 6, 6, 3):
        items.append("👔 Father's Day")

    if not items:
        print("NO_REPLY")
    else:
        print(f"📅 Heads up — in {LOOKAHEAD_DAYS} days ({target_human}):")
        for item in items:
            print(f"- {item}")
except Exception:
    print("Upcoming Dates check failed: calendar unavailable.")
PY
```

---

## OUTPUT RULES

- Return only one of:
  - `NO_REPLY`
  - The reminder produced by the script
  - `Upcoming Dates check failed: calendar unavailable.`
