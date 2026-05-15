#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
KENNY_SESSION_KEY = "agent:main:telegram:direct:7540422842"
MAX_TEXT_CHARS = 500
MAX_CONTEXT_CHARS = 30000
MAX_EXISTING_RECORDS = 20


def choose_existing(candidates: list[Path]) -> Path:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def state_root() -> Path:
    return choose_existing(
        [
            Path("/home/node/.openclaw"),
            Path("/home/kenny/.openclaw"),
            Path.home() / ".openclaw",
        ],
    )


def workspace_root() -> Path:
    env_workspace = os.environ.get("OPENCLAW_WORKSPACE")
    candidates = []
    if env_workspace:
        candidates.append(Path(env_workspace))
    root = state_root()
    candidates.extend(
        [
            root / "workspace",
            Path("/home/node/.openclaw/workspace"),
            Path("/home/kenny/.openclaw/workspace"),
            Path.cwd(),
        ],
    )
    return choose_existing(candidates)


STATE_ROOT = state_root()
WORKSPACE_ROOT = workspace_root()
SESSIONS_INDEX = STATE_ROOT / "agents/main/sessions/sessions.json"
SESSIONS_DIR = STATE_ROOT / "agents/main/sessions"
MEMORY_DIR = WORKSPACE_ROOT / "memory"
MEDIUM_MEMORY = MEMORY_DIR / "medium_memory.jsonl"
LONG_MEMORY = MEMORY_DIR / "long_memory.jsonl"
AUDIT_FILE = MEMORY_DIR / "nightly_session_reflection_state.jsonl"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Nightly interactive session reflection helper.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect = subparsers.add_parser("collect", help="Collect compact transcript context.")
    collect.add_argument("--date", default="yesterday", help="ET date YYYY-MM-DD or 'yesterday'.")
    collect.add_argument("--session-key", default=KENNY_SESSION_KEY)
    collect.add_argument("--out", help="Optional path to write JSON context.")

    apply = subparsers.add_parser("apply", help="Validate and append model-proposed memory records.")
    apply.add_argument("--json-file", required=True, help="Decision JSON file from the model.")
    apply.add_argument("--date", default="yesterday", help="Reflected ET date YYYY-MM-DD or 'yesterday'.")
    apply.add_argument("--session-key", default=KENNY_SESSION_KEY)
    apply.add_argument("--dry-run", action="store_true")

    reset = subparsers.add_parser("reset", help="Reset the interactive session if explicitly enabled.")
    reset.add_argument("--session-key", default=KENNY_SESSION_KEY)

    return parser.parse_args()


def today_et() -> datetime:
    return datetime.now(ET)


def resolve_target_date(value: str) -> str:
    if value == "yesterday":
        return (today_et().date() - timedelta(days=1)).isoformat()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"invalid date: {value}")
    return value


def parse_timestamp(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        text = raw.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(ET)
    except ValueError:
        return None


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        lines = path.read_text().splitlines()
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


def append_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, separators=(",", ":"), ensure_ascii=False))
            handle.write("\n")


def session_file_from_key(session_key: str) -> tuple[str | None, Path | None]:
    index = load_json(SESSIONS_INDEX)
    entry = index.get(session_key) if isinstance(index, dict) else None
    if not isinstance(entry, dict):
        return None, None
    session_id = str(entry.get("sessionId") or "").strip() or None
    raw_file = str(entry.get("sessionFile") or "").strip()
    candidates: list[Path] = []
    if raw_file:
        raw_path = Path(raw_file)
        candidates.append(raw_path)
        if str(raw_path).startswith("/home/node/.openclaw"):
            candidates.append(Path(str(raw_path).replace("/home/node/.openclaw", str(STATE_ROOT), 1)))
    if session_id:
        candidates.append(SESSIONS_DIR / f"{session_id}.jsonl")
    path = choose_existing(candidates) if candidates else None
    if path and path.exists():
        return session_id, path
    return session_id, None


def text_parts(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        if kind == "text" and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "\n".join(parts)


METADATA_BLOCK_RE = re.compile(
    r'(?ms)^[^\n]*(?:untrusted metadata|untrusted, for context)[^\n]*:\n```json\n.*?\n```\n\n?'
)


def clean_text(role: str, text: str) -> str:
    text = text.replace("[[reply_to_current]]", "").strip()
    if role == "user":
        text = METADATA_BLOCK_RE.sub("", text).strip()
        if text.startswith("A new session was started via /new or /reset."):
            return ""
    if text.startswith("✅ New session started"):
        return ""
    return re.sub(r"\s+", " ", text).strip()


def short(text: str, max_chars: int = MAX_TEXT_CHARS) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 1].rstrip() + "..."


def transcript_events(path: Path, target_date: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    total_chars = 0
    for line in path.read_text().splitlines():
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict) or parsed.get("type") != "message":
            continue
        ts = parse_timestamp(str(parsed.get("timestamp") or ""))
        if ts is None or ts.date().isoformat() != target_date:
            continue
        message = parsed.get("message")
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "")
        if role not in {"user", "assistant", "toolResult"}:
            continue
        text = clean_text(role, text_parts(message.get("content")))
        if role == "toolResult":
            tool_name = str(message.get("toolName") or "")
            interesting = (
                bool(message.get("isError"))
                or "error" in text.lower()
                or "failed" in text.lower()
                or "successfully" in text.lower()
                or "✓" in text
            )
            if not interesting:
                continue
            text = f"{tool_name}: {text}" if tool_name else text
        if not text:
            continue
        event = {
            "timestamp_et": ts.isoformat(timespec="seconds"),
            "role": role,
            "text": short(text),
        }
        encoded_len = len(json.dumps(event, ensure_ascii=False))
        if total_chars + encoded_len > MAX_CONTEXT_CHARS:
            break
        events.append(event)
        total_chars += encoded_len
    return events


def normalize_summary(value: Any, max_chars: int = 180) -> str:
    return short(str(value or ""), max_chars)


def normalize_key(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def add_days(date_iso: str, days: int) -> str:
    date = datetime.fromisoformat(f"{date_iso}T00:00:00+00:00")
    return (date + timedelta(days=days)).date().isoformat()


def clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, minimum), maximum)


def valid_date(value: Any) -> str | None:
    text = str(value or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return None
    try:
        datetime.fromisoformat(f"{text}T00:00:00+00:00")
    except ValueError:
        return None
    return text


def collect(args: argparse.Namespace) -> int:
    target_date = resolve_target_date(args.date)
    session_id, session_path = session_file_from_key(args.session_key)
    if session_path is None:
        payload = {
            "ok": False,
            "reason": "session_not_found",
            "session_key": args.session_key,
            "date_et": target_date,
        }
    else:
        events = transcript_events(session_path, target_date)
        low_signal = len(events) == 0
        payload = {
            "ok": True,
            "low_signal": low_signal,
            "date_et": target_date,
            "session_key": args.session_key,
            "session_id": session_id,
            "session_file": str(session_path),
            "event_count": len(events),
            "events": events,
            "existing_medium_memory": [] if low_signal else load_jsonl(MEDIUM_MEMORY)[-MAX_EXISTING_RECORDS:],
            "existing_long_memory": [] if low_signal else load_jsonl(LONG_MEMORY)[-MAX_EXISTING_RECORDS:],
            "decision_schema": {
                "medium_memory": [
                    {"summary": "string", "expires_in_days": "3-30 or expires_at YYYY-MM-DD"}
                ],
                "long_memory": [{"summary": "string", "expires_at": "YYYY-MM-DD or 9999-12-31"}],
                "reset_recommended": False,
                "notes": ["optional short operational notes, no transcript dumps"],
            },
        }
    output = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0 if payload.get("ok") else 2


def decision_list(decision: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = decision.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def apply(args: argparse.Namespace) -> int:
    reflected_date = resolve_target_date(args.date)
    created_at = today_et().date().isoformat()
    decision = load_json(Path(args.json_file))
    if not isinstance(decision, dict):
        raise ValueError("decision JSON must be an object")

    existing_medium = load_jsonl(MEDIUM_MEMORY)
    existing_long = load_jsonl(LONG_MEMORY)
    existing_summaries = {
        normalize_key(str(record.get("summary") or ""))
        for record in [*existing_medium, *existing_long]
        if record.get("summary")
    }

    medium_to_append: list[dict[str, Any]] = []
    long_to_append: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []

    for item in decision_list(decision, "medium_memory"):
        summary = normalize_summary(item.get("summary"))
        key = normalize_key(summary)
        if not summary or key in existing_summaries:
            skipped.append({"kind": "medium", "reason": "empty_or_duplicate"})
            continue
        expires_at = valid_date(item.get("expires_at"))
        if not expires_at:
            expires_at = add_days(created_at, clamp_int(item.get("expires_in_days"), 14, 3, 30))
        record = {"summary": summary, "created_at": created_at, "expires_at": expires_at}
        medium_to_append.append(record)
        existing_summaries.add(key)

    for item in decision_list(decision, "long_memory"):
        summary = normalize_summary(item.get("summary"))
        key = normalize_key(summary)
        if not summary or key in existing_summaries:
            skipped.append({"kind": "long", "reason": "empty_or_duplicate"})
            continue
        record = {
            "summary": summary,
            "created_at": created_at,
            "expires_at": valid_date(item.get("expires_at")) or "9999-12-31",
        }
        long_to_append.append(record)
        existing_summaries.add(key)

    if not args.dry_run:
        append_jsonl(MEDIUM_MEMORY, medium_to_append)
        append_jsonl(LONG_MEMORY, long_to_append)
        audit = {
            "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "reflected_date_et": reflected_date,
            "session_key": args.session_key,
            "medium_appended": len(medium_to_append),
            "long_appended": len(long_to_append),
            "skipped": skipped,
            "reset_recommended": bool(decision.get("reset_recommended")),
            "reset_enabled": os.environ.get("NIGHTLY_REFLECTION_ENABLE_RESET") == "1",
        }
        append_jsonl(AUDIT_FILE, [audit])

    result = {
        "ok": True,
        "dry_run": args.dry_run,
        "medium_appended": len(medium_to_append),
        "long_appended": len(long_to_append),
        "skipped": skipped,
        "reset_recommended": bool(decision.get("reset_recommended")),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def reset(args: argparse.Namespace) -> int:
    if os.environ.get("NIGHTLY_REFLECTION_ENABLE_RESET") != "1":
        print(json.dumps({"ok": True, "reset": "skipped", "reason": "reset_disabled"}, indent=2))
        return 0
    command = os.environ.get("NIGHTLY_REFLECTION_RESET_COMMAND")
    if not command:
        print(
            json.dumps(
                {
                    "ok": False,
                    "reset": "not_run",
                    "reason": "NIGHTLY_REFLECTION_RESET_COMMAND is not configured",
                },
                indent=2,
            )
        )
        return 2
    completed = subprocess.run(command, shell=True, text=True, capture_output=True, timeout=60)
    print(
        json.dumps(
            {
                "ok": completed.returncode == 0,
                "reset": "attempted",
                "returncode": completed.returncode,
                "stdout": short(completed.stdout, 1000),
                "stderr": short(completed.stderr, 1000),
            },
            indent=2,
        )
    )
    return completed.returncode


def main() -> int:
    args = parse_args()
    try:
        if args.command == "collect":
            return collect(args)
        if args.command == "apply":
            return apply(args)
        if args.command == "reset":
            return reset(args)
    except Exception as exc:  # noqa: BLE001 - cron helper should return compact failure JSON.
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
