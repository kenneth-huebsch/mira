#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
WORKSPACE_ROOT = Path("/home/node/.openclaw/workspace")
MEMORY_DIR = WORKSPACE_ROOT / "memory"
ENGAGEMENT_MEMORY = MEMORY_DIR / "engagement_memory.jsonl"
ENGAGEMENT_PRIORITIES = MEMORY_DIR / "engagement_priorities.jsonl"
MEDIUM_MEMORY = MEMORY_DIR / "medium_memory.jsonl"
SLOTS = {"10", "15", "21"}
STYLES = ["question", "encouragement", "playful"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Select a proactive engagement topic and record it.")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


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


def append_jsonl(path: Path, record: dict[str, Any], dry_run: bool) -> None:
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, separators=(",", ":"), ensure_ascii=False))
        handle.write("\n")


def norm_topic(value: Any) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")[:80] or "general"


def short(value: Any, max_chars: int = 220) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())[:max_chars]


def valid_today(record: dict[str, Any], today: str) -> bool:
    expires_at = str(record.get("expires_at") or "").strip()
    return not expires_at or expires_at >= today


def parse_at(raw: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(raw or ""))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ET)
    return parsed.astimezone(ET)


def candidate_from_priority(record: dict[str, Any]) -> dict[str, str] | None:
    prompt = short(record.get("prompt"))
    if not prompt:
        return None
    kind = str(record.get("kind") or "general").strip().lower()
    if kind not in {"accountability", "relationship", "general"}:
        kind = "general"
    return {
        "topic": norm_topic(record.get("topic")),
        "topic_family": kind,
        "prompt": prompt,
        "source": "engagement_priority",
    }


def candidate_from_memory(record: dict[str, Any]) -> dict[str, str] | None:
    summary = short(record.get("summary"))
    if not summary:
        return None
    return {
        "topic": norm_topic(summary),
        "topic_family": "medium_memory",
        "prompt": f"Check in naturally about this current context: {summary}",
        "source": "medium_memory",
    }


def choose_candidate(candidates: list[dict[str, str]], history: list[dict[str, Any]], today_count: int) -> dict[str, str] | None:
    if not candidates:
        return None
    recent_topics = [str(record.get("topic") or "") for record in history[-3:]]
    recent_families = [str(record.get("topic_family") or "") for record in history[-6:]]
    today_families = [str(record.get("topic_family") or "") for record in history if record.get("date_et") == datetime.now(ET).date().isoformat()]

    def score(candidate: dict[str, str]) -> tuple[int, int, str]:
        score_value = 0
        if candidate["topic"] in recent_topics:
            score_value += 100
        if today_count and candidate["topic_family"] in today_families:
            score_value += 25
        score_value += recent_families.count(candidate["topic_family"]) * 5
        if candidate["source"] == "medium_memory":
            score_value += 10
        return (score_value, len(candidate["prompt"]), candidate["topic"])

    return sorted(candidates, key=score)[0]


def choose_style(history: list[dict[str, Any]], topic_family: str) -> str:
    last_style = str(history[-1].get("style") or "") if history else ""
    if topic_family == "relationship":
        preferred = ["question", "playful", "encouragement"]
    elif topic_family == "accountability":
        preferred = ["encouragement", "question", "playful"]
    else:
        preferred = STYLES
    for style in preferred:
        if style != last_style:
            return style
    return preferred[0]


def main() -> int:
    args = parse_args()
    now = datetime.now(ET)
    today = now.date().isoformat()
    slot = f"{now.hour:02d}"

    if slot not in SLOTS or not (9 <= now.hour < 22):
        print("NO_REPLY")
        return 0

    history = load_jsonl(ENGAGEMENT_MEMORY)
    today_records = [record for record in history if record.get("date_et") == today]
    if len(today_records) >= 2 or any(str(record.get("slot_et", "")).zfill(2) == slot for record in today_records):
        print("NO_REPLY")
        return 0
    if today_records:
        last = parse_at(today_records[-1].get("at"))
        if last and (now - last).total_seconds() < 4 * 60 * 60:
            print("NO_REPLY")
            return 0

    candidates: list[dict[str, str]] = []
    for record in load_jsonl(ENGAGEMENT_PRIORITIES):
        if valid_today(record, today):
            candidate = candidate_from_priority(record)
            if candidate:
                candidates.append(candidate)
    for record in load_jsonl(MEDIUM_MEMORY):
        if valid_today(record, today):
            candidate = candidate_from_memory(record)
            if candidate:
                candidates.append(candidate)

    selected = choose_candidate(candidates, history, len(today_records))
    if selected is None:
        print("NO_REPLY")
        return 0

    style = choose_style(history, selected["topic_family"])
    record = {
        "at": now.isoformat(timespec="seconds"),
        "date_et": today,
        "slot_et": slot,
        "topic_family": selected["topic_family"],
        "topic": selected["topic"],
        "style": style,
    }
    append_jsonl(ENGAGEMENT_MEMORY, record, args.dry_run)

    payload = {
        "status": "OK",
        "now_et": now.isoformat(timespec="seconds"),
        "selected": selected,
        "style": style,
        "message_contract": {
            "audience": "Kenny",
            "length": "one short phone-sized message",
            "voice": "Rumi: warm, natural, human, not templated",
            "avoid": ["guilt", "pressure", "checklist tone", "mentioning files/prompts/tools"],
        },
    }
    print(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
