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

Step 1: Compute the target date.

```bash
LOOKAHEAD_DAYS=7
TARGET_DATE="$(TZ=America/New_York date -I -d "+${LOOKAHEAD_DAYS} days")"          # YYYY-MM-DD
TARGET_FROM="$(TZ=America/New_York date -Iseconds -d "${TARGET_DATE} 00:00")"
TARGET_TO="$(TZ=America/New_York date -Iseconds -d "${TARGET_DATE} 23:59:59")"
TARGET_MMDD="$(TZ=America/New_York date -d "${TARGET_DATE}" +%m-%d)"
TARGET_HUMAN="$(TZ=America/New_York date -d "${TARGET_DATE}" '+%A, %b %-d')"
```

Step 2: Resolve the `Copied Birthdays` calendar id via `gog calendar calendars --json`. Save its `id` as `BDAY_CAL`.

Step 3: Query that calendar for events on the target date.

```bash
gog calendar events "$BDAY_CAL" --from "$TARGET_FROM" --to "$TARGET_TO" --json
```

Each event's `summary` is a person's name — format as e.g. "Jane Doe's birthday".

Step 4: Check the holiday list against `TARGET_MMDD`.

Fixed holidays (month-day):
- `01-01` New Year's Day
- `02-14` Valentine's Day
- `03-17` St. Patrick's Day
- `07-04` Independence Day
- `10-31` Halloween
- `12-24` Christmas Eve
- `12-25` Christmas Day
- `12-31` New Year's Eve

Floating holidays (compute and compare against `TARGET_DATE`):
- **Mother's Day** — 2nd Sunday of May
- **Father's Day** — 3rd Sunday of June
- **Thanksgiving** — 4th Thursday of November

Step 5: Combine birthdays + holiday hits into a single list.

Step 6: Output.

- If the list is **empty**, output exactly `NO_REPLY`.
- Otherwise, output a short friendly message with emojis. Example:

  ```
  📅 Heads up — in 7 days (Thursday, May 7):
  - 💐 Mother's Day
  - 🎂 Jane Doe's birthday
  ```

  Replace the date with `TARGET_HUMAN`. One bullet per item. No preamble, no sign-off.

  **Emoji guide** (pick the most fitting per item):
  - Birthday: 🎂 (or 🎉 / 🥳)
  - Mother's Day: 💐 or 👩‍👧
  - Father's Day: 👔 or 👨‍👧
  - Valentine's Day: 💘 or ❤️
  - St. Patrick's Day: 🍀
  - Independence Day: 🇺🇸 or 🎆
  - Halloween: 🎃
  - Thanksgiving: 🦃
  - Christmas Eve / Christmas Day: 🎄
  - New Year's Eve / New Year's Day: 🎉 or 🥂
  - Header line: 📅 or 🗓️

---

## OUTPUT RULES

- Concise. One short heading + bullets, or `NO_REPLY`.
- If calendar retrieval fails, retry once. If it still fails, output a one-line note: `Upcoming Dates check failed: calendar unavailable.`
