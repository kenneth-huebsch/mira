#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
ACCOUNT = "rumi.openclaw@gmail.com"
WORKSPACE_ROOT = Path("/home/node/.openclaw/workspace")
MEDIUM_MEMORY = WORKSPACE_ROOT / "memory/medium_memory.jsonl"
CALENDARS = [
    ("personal", "kenneth.huebsch@gmail.com"),
    ("work", "o9k4ud8ocv356bk0e65kb59s0mjcisaq@import.calendar.google.com"),
]


def run_json(args: list[str]) -> dict[str, Any]:
    proc = subprocess.run(args, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip() or "command failed")
    parsed = json.loads(proc.stdout)
    if not isinstance(parsed, dict):
        raise RuntimeError("expected JSON object")
    return parsed


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


def list_items(data: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def text(value: Any, max_chars: int = 160) -> str:
    compact = re.sub(r"\s+", " ", str(value or "").strip())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 1].rstrip() + "..."


def event_time(value: Any) -> str:
    if isinstance(value, dict):
        if value.get("dateTime"):
            return str(value["dateTime"])
        if value.get("date"):
            return str(value["date"])
    return str(value or "")


def compact_event(event: dict[str, Any], source: str) -> dict[str, Any]:
    return {
        "source": source,
        "summary": text(event.get("summary") or event.get("title")),
        "start": event_time(event.get("start")),
        "end": event_time(event.get("end")),
        "status": text(event.get("status"), 40),
        "location": text(event.get("location"), 80),
    }


def current_memory(today: str) -> list[dict[str, str]]:
    records = []
    for record in load_jsonl(MEDIUM_MEMORY):
        summary = text(record.get("summary"), 220)
        expires_at = str(record.get("expires_at") or "")
        if summary and (not expires_at or expires_at >= today):
            records.append(
                {
                    "summary": summary,
                    "created_at": str(record.get("created_at") or ""),
                    "expires_at": expires_at,
                }
            )
    return records[:12]


def main() -> int:
    now = datetime.now(ET)
    today = now.date()
    start = datetime.combine(today, time.min, ET).isoformat()
    end = datetime.combine(today, time(23, 59, 59), ET).isoformat()
    calendar_results: list[dict[str, Any]] = []
    calendar_failures: list[dict[str, str]] = []

    for source, calendar_id in CALENDARS:
        try:
            data = run_json(
                [
                    "gog",
                    "calendar",
                    "events",
                    calendar_id,
                    "--from",
                    start,
                    "--to",
                    end,
                    "--json",
                    "--account",
                    ACCOUNT,
                ]
            )
            calendar_results.extend(compact_event(event, source) for event in list_items(data, "events", "items"))
        except Exception as exc:  # noqa: BLE001 - cron collector should report compact failures.
            calendar_failures.append({"source": source, "error": text(exc, 180)})

    payload = {
        "status": "OK",
        "now_et": now.isoformat(timespec="seconds"),
        "date_et": today.isoformat(),
        "calendar": {
            "events": calendar_results,
            "failures": calendar_failures,
            "failure_rule": "Never claim no events when any calendar source is listed in failures.",
        },
        "memory": current_memory(today.isoformat()),
        "todoist": {
            "source": "MCP",
            "instruction": "Use Todoist MCP tools for due today, overdue, P1/P2, and important upcoming tasks from Kennys Personal Tasks and Kennys Work Todo List.",
        },
        "model_contract": {
            "voice": "Rumi: concise, warm, human, varied",
            "use_facts_only": True,
            "avoid": ["raw JSON", "tool chatter", "generic templated report"],
        },
    }
    print(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
