#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
WORKSPACE_ROOT = Path(os.environ.get("OPENCLAW_WORKSPACE_DIR", Path(__file__).resolve().parents[1]))
MEMORY_DIR = WORKSPACE_ROOT / "memory"
FOLLOWUPS = MEMORY_DIR / "engagement_followups.jsonl"
ENGAGEMENT_MEMORY = MEMORY_DIR / "engagement_memory.jsonl"
MAX_FOLLOWUP_DAYS = 14
MAX_ATTEMPTS = 8
COMPLETED_RETENTION = timedelta(days=3)
TERMINAL_STATUSES = {"delivered", "expired", "failed"}
SUPPORTED_LIVE_CHECKS = {"sports_result"}
ESPN_SPORTS = {
    "MLB": ("baseball", "mlb"),
    "NBA": ("basketball", "nba"),
    "NFL": ("football", "nfl"),
    "NHL": ("hockey", "nhl"),
}


def now_et() -> datetime:
    return datetime.now(ET)


def compact(value: Any, max_chars: int = 500) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return text[:max_chars]


def normalize_key(value: Any) -> str:
    text = compact(value, 180).lower()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_") or "followup"


def parse_dt(value: Any, default_tz: ZoneInfo = ET) -> datetime | None:
    if not value:
        return None
    raw = str(value).strip()
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=default_tz)
    return parsed.astimezone(ET)


def iso(dt: datetime) -> str:
    return dt.astimezone(ET).isoformat(timespec="seconds")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return records
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            records.append(parsed)
    return records


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n" for record in records)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def compact_followups(records: list[dict[str, Any]], now: datetime) -> tuple[list[dict[str, Any]], bool]:
    cutoff = now - COMPLETED_RETENTION
    kept: list[dict[str, Any]] = []
    changed = False

    for record in records:
        if record.get("status") not in TERMINAL_STATUSES:
            kept.append(record)
            continue

        reference_time = (
            parse_dt(record.get("delivered_at"))
            or parse_dt(record.get("last_checked_at"))
            or parse_dt(record.get("expires_at"))
            or parse_dt(record.get("due_at"))
            or parse_dt(record.get("created_at"))
        )
        if reference_time and reference_time < cutoff:
            changed = True
            continue
        kept.append(record)

    return kept, changed


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, separators=(",", ":"), ensure_ascii=False))
        handle.write("\n")


def read_instruction(args: argparse.Namespace) -> dict[str, Any]:
    raw = args.json if args.json is not None else sys.stdin.read()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("instruction must be a JSON object")
    return parsed


def coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)


def bounded_hours(value: Any, default: int, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(low, min(high, number))


def make_id(record: dict[str, Any]) -> str:
    basis = json.dumps(
        {
            "created_at": record.get("created_at"),
            "due_at": record.get("due_at"),
            "dedupe_key": record.get("dedupe_key"),
            "intent": record.get("intent"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def validate_instruction(input_record: dict[str, Any], now: datetime) -> dict[str, Any]:
    intent = compact(input_record.get("intent"), 240)
    source_context = compact(input_record.get("source_context"), 300)
    if not intent or not source_context:
        raise ValueError("intent and source_context are required")

    due_at = parse_dt(input_record.get("due_at"))
    if due_at is None and input_record.get("due_in_minutes") is not None:
        due_at = now + timedelta(minutes=max(1, int(input_record["due_in_minutes"])))
    if due_at is None:
        raise ValueError("due_at or due_in_minutes is required")
    if due_at < now - timedelta(minutes=5):
        raise ValueError("due_at is already in the past")
    if due_at > now + timedelta(days=MAX_FOLLOWUP_DAYS):
        raise ValueError(f"due_at must be within {MAX_FOLLOWUP_DAYS} days")

    expires_at = parse_dt(input_record.get("expires_at"))
    if expires_at is None:
        expires_at = due_at + timedelta(hours=bounded_hours(input_record.get("expires_in_hours"), 6, 1, 72))
    if expires_at <= due_at:
        raise ValueError("expires_at must be after due_at")
    if expires_at > now + timedelta(days=MAX_FOLLOWUP_DAYS + 3):
        raise ValueError("expires_at is too far in the future")

    requires_live_check = coerce_bool(input_record.get("requires_live_check"))
    live_check_type = compact(input_record.get("live_check_type"), 80) or None
    if requires_live_check and live_check_type not in SUPPORTED_LIVE_CHECKS:
        raise ValueError(f"unsupported live_check_type: {live_check_type}")
    if not requires_live_check:
        live_check_type = None

    constraints = input_record.get("constraints", [])
    if isinstance(constraints, str):
        constraints = [constraints]
    if not isinstance(constraints, list):
        constraints = []
    constraints = [compact(item, 120) for item in constraints if compact(item, 120)][:8]

    payload = input_record.get("payload", {})
    if not isinstance(payload, dict):
        payload = {"value": payload}

    suggested = compact(input_record.get("suggested_message_angle"), 220)
    dedupe_basis = input_record.get("dedupe_key") or {
        "intent": intent,
        "source_context": source_context,
        "live_check_type": live_check_type,
        "payload": payload,
    }
    dedupe_key = normalize_key(dedupe_basis)

    record = {
        "id": "",
        "status": "pending",
        "created_at": iso(now),
        "due_at": iso(due_at),
        "expires_at": iso(expires_at),
        "attempts": 0,
        "last_checked_at": None,
        "delivered_at": None,
        "dedupe_key": dedupe_key,
        "requires_live_check": requires_live_check,
        "live_check_type": live_check_type,
        "intent": intent,
        "source_context": source_context,
        "suggested_message_angle": suggested,
        "constraints": constraints,
        "payload": payload,
    }
    record["id"] = make_id(record)
    return record


def enqueue(args: argparse.Namespace) -> int:
    now = parse_dt(args.now) if args.now else now_et()
    if now is None:
        raise ValueError("invalid --now")
    record = validate_instruction(read_instruction(args), now)
    records = load_jsonl(FOLLOWUPS)
    for existing in records:
        if (
            existing.get("status") == "pending"
            and existing.get("dedupe_key") == record["dedupe_key"]
            and (parse_dt(existing.get("expires_at")) or now) > now
        ):
            print("DUPLICATE")
            return 0
    if not args.dry_run:
        append_jsonl(FOLLOWUPS, record)
    print("QUEUED")
    return 0


def team_aliases(value: Any) -> set[str]:
    raw = compact(value, 120).lower()
    aliases = {raw}
    replacements = {
        "phils": "philadelphia phillies",
        "sixers": "philadelphia 76ers",
        "76ers": "philadelphia 76ers",
        "birds": "philadelphia eagles",
        "eagles": "philadelphia eagles",
        "flyers": "philadelphia flyers",
        "phillies": "philadelphia phillies",
    }
    if raw in replacements:
        aliases.add(replacements[raw])
    aliases.update(part for part in re.split(r"\s+", raw) if part)
    return {alias for alias in aliases if alias}


def competitor_names(competitor: dict[str, Any]) -> set[str]:
    team = competitor.get("team") if isinstance(competitor.get("team"), dict) else {}
    values = [
        team.get("displayName"),
        team.get("name"),
        team.get("shortDisplayName"),
        team.get("location"),
        team.get("abbreviation"),
        competitor.get("displayName"),
    ]
    return {compact(value, 120).lower() for value in values if compact(value, 120)}


def matches_team(competitor: dict[str, Any], requested: Any) -> bool:
    requested_aliases = team_aliases(requested)
    names = competitor_names(competitor)
    return any(alias in names or any(alias in name for name in names) for alias in requested_aliases)


def fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "Rumi engagement followups"})
    with urllib.request.urlopen(request, timeout=20) as response:
        parsed = json.loads(response.read().decode("utf-8"))
    if not isinstance(parsed, dict):
        raise RuntimeError("expected JSON object")
    return parsed


def sports_scoreboard_url(payload: dict[str, Any]) -> str:
    explicit = compact(payload.get("espn_api_url") or payload.get("scoreboard_url"), 500)
    if explicit:
        return explicit
    league = compact(payload.get("league"), 20).upper()
    if league not in ESPN_SPORTS:
        raise RuntimeError("sports_result requires payload.league or payload.espn_api_url")
    sport, league_path = ESPN_SPORTS[league]
    date_value = compact(payload.get("date") or payload.get("game_date"), 40)
    date_param = ""
    if date_value:
        date_param = f"?dates={re.sub(r'[^0-9]', '', date_value)[:8]}"
    return f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league_path}/scoreboard{date_param}"


def parse_score(event: dict[str, Any], requested_team: Any) -> dict[str, Any] | None:
    competitions = event.get("competitions")
    if not isinstance(competitions, list) or not competitions:
        return None
    competition = competitions[0]
    if not isinstance(competition, dict):
        return None
    competitors = competition.get("competitors")
    if not isinstance(competitors, list):
        return None
    valid_competitors = [item for item in competitors if isinstance(item, dict)]
    if len(valid_competitors) < 2:
        return None
    followed = next((item for item in valid_competitors if matches_team(item, requested_team)), None)
    if followed is None:
        return None
    other = next((item for item in valid_competitors if item is not followed), valid_competitors[0])

    status = competition.get("status") if isinstance(competition.get("status"), dict) else event.get("status")
    status_type = status.get("type") if isinstance(status, dict) and isinstance(status.get("type"), dict) else {}
    completed = bool(status_type.get("completed"))
    detail = compact(status_type.get("detail") or status_type.get("shortDetail"), 120)

    def label(item: dict[str, Any]) -> str:
        team = item.get("team") if isinstance(item.get("team"), dict) else {}
        return compact(team.get("shortDisplayName") or team.get("displayName") or team.get("name"), 80)

    def score_value(item: dict[str, Any]) -> int | None:
        try:
            return int(item.get("score"))
        except (TypeError, ValueError):
            return None

    followed_score = score_value(followed)
    other_score = score_value(other)
    won = None
    if completed and followed_score is not None and other_score is not None:
        won = followed_score > other_score

    return {
        "completed": completed,
        "detail": detail,
        "team": label(followed),
        "opponent": label(other),
        "team_score": followed_score,
        "opponent_score": other_score,
        "won": won,
        "event_name": compact(event.get("name") or event.get("shortName"), 120),
    }


def check_sports_result(record: dict[str, Any]) -> dict[str, Any]:
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    fixture = payload.get("fixture_result")
    if isinstance(fixture, dict):
        return fixture
    team = payload.get("team")
    if not team:
        raise RuntimeError("sports_result requires payload.team")
    data = fetch_json(sports_scoreboard_url(payload))
    events = data.get("events")
    if not isinstance(events, list):
        return {"completed": False, "detail": "No games found yet"}
    for event in events:
        if isinstance(event, dict):
            parsed = parse_score(event, team)
            if parsed:
                return parsed
    return {"completed": False, "detail": "Matching game not found yet"}


def build_message_payload(record: dict[str, Any], now: datetime, live_result: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "status": "OK",
        "now_et": iso(now),
        "followup": {
            "id": record.get("id"),
            "intent": record.get("intent"),
            "source_context": record.get("source_context"),
            "suggested_message_angle": record.get("suggested_message_angle"),
            "constraints": record.get("constraints") if isinstance(record.get("constraints"), list) else [],
            "requires_live_check": bool(record.get("requires_live_check")),
            "live_check_type": record.get("live_check_type"),
            "payload": record.get("payload") if isinstance(record.get("payload"), dict) else {},
            "live_result": live_result,
        },
        "message_contract": {
            "audience": "Kenny",
            "length": "one short phone-sized message",
            "voice": "Rumi: warm, natural, human, not templated",
            "avoid": [
                "mentioning files",
                "mentioning cron",
                "generic reminder wording",
                "pretending to know facts not present in this JSON",
            ],
        },
    }


def record_engagement(record: dict[str, Any], now: datetime) -> None:
    append_jsonl(
        ENGAGEMENT_MEMORY,
        {
            "at": iso(now),
            "date_et": now.date().isoformat(),
            "slot_et": f"{now.hour:02d}",
            "topic_family": "followup",
            "topic": normalize_key(record.get("dedupe_key") or record.get("intent")),
            "style": "followup",
        },
    )


def run_due(args: argparse.Namespace) -> int:
    now = parse_dt(args.now) if args.now else now_et()
    if now is None:
        raise ValueError("invalid --now")
    records, changed = compact_followups(load_jsonl(FOLLOWUPS), now)
    due_index = None
    for index, record in enumerate(records):
        if record.get("status") != "pending":
            continue
        expires_at = parse_dt(record.get("expires_at"))
        if expires_at and expires_at <= now:
            record["status"] = "expired"
            changed = True
            continue
        due_at = parse_dt(record.get("due_at"))
        if due_at and due_at <= now and due_index is None:
            due_index = index

    if due_index is None:
        if changed and not args.dry_run:
            write_jsonl(FOLLOWUPS, records)
        print("NO_REPLY")
        return 0

    record = records[due_index]
    record["last_checked_at"] = iso(now)
    record["attempts"] = int(record.get("attempts") or 0) + 1
    live_result = None

    if record.get("requires_live_check"):
        if record.get("live_check_type") != "sports_result":
            record["status"] = "failed"
            changed = True
            if not args.dry_run:
                write_jsonl(FOLLOWUPS, records)
            print("NO_REPLY")
            return 0
        try:
            live_result = check_sports_result(record)
        except (RuntimeError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            live_result = {"completed": False, "detail": compact(exc, 160)}
        if not live_result.get("completed"):
            if record["attempts"] >= MAX_ATTEMPTS:
                record["status"] = "expired"
            else:
                record["due_at"] = iso(now + timedelta(minutes=20))
            changed = True
            if not args.dry_run:
                write_jsonl(FOLLOWUPS, records)
            print("NO_REPLY")
            return 0

    record["status"] = "delivered"
    record["delivered_at"] = iso(now)
    changed = True
    if not args.dry_run:
        write_jsonl(FOLLOWUPS, records)
        record_engagement(record, now)
    print(json.dumps(build_message_payload(record, now, live_result), separators=(",", ":"), ensure_ascii=False))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Queue and run Rumi engagement follow-ups.")
    parser.add_argument("--now", help="Override current time for tests (ISO-8601).")
    parser.add_argument("--dry-run", action="store_true")
    subparsers = parser.add_subparsers(dest="command")
    enqueue_parser = subparsers.add_parser("enqueue", help="Validate and append one follow-up instruction.")
    enqueue_parser.add_argument("--json", help="Instruction JSON. If omitted, read stdin.")
    enqueue_parser.add_argument("--now", help="Override current time for tests (ISO-8601).")
    enqueue_parser.add_argument("--dry-run", action="store_true")
    run_parser = subparsers.add_parser("run", help="Run due follow-ups.")
    run_parser.add_argument("--now", help="Override current time for tests (ISO-8601).")
    run_parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "enqueue":
        return enqueue(args)
    return run_due(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(2)
