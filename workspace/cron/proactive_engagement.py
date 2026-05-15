#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import random
import re
from datetime import date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
WORKSPACE_ROOT = Path(os.environ.get("OPENCLAW_WORKSPACE_DIR", "/home/node/.openclaw/workspace"))
MEMORY_DIR = WORKSPACE_ROOT / "memory"
ENGAGEMENT_MEMORY = MEMORY_DIR / "engagement_memory.jsonl"
MEDIUM_MEMORY = MEMORY_DIR / "medium_memory.jsonl"
LONG_MEMORY = MEMORY_DIR / "long_memory.jsonl"
ACTIVE_START = time(10, 0)
ACTIVE_END = time(21, 0)
WINDOW_MINUTES = (21 - 10) * 60
STYLES = ["question", "encouragement", "playful"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Select a proactive engagement topic and record it.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--now", help="Override current time for tests (ISO-8601).")
    parser.add_argument("--seed", type=int, help="Seed topic selection for repeatable dry-run checks.")
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


def today_from(now: datetime) -> str:
    return now.date().isoformat()


def parse_date(raw: Any) -> date | None:
    try:
        return date.fromisoformat(str(raw or "").strip()[:10])
    except ValueError:
        return None


def token_set(value: str) -> set[str]:
    stop_words = {
        "a",
        "an",
        "and",
        "about",
        "for",
        "he",
        "his",
        "how",
        "if",
        "is",
        "it",
        "of",
        "on",
        "or",
        "the",
        "to",
        "today",
        "with",
    }
    return {token for token in re.split(r"[^a-z0-9]+", value.lower()) if token and token not in stop_words}


def similarity(left: str, right: str) -> float:
    left_tokens = token_set(left)
    right_tokens = token_set(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def candidate_from_memory(record: dict[str, Any], source: str) -> dict[str, str] | None:
    summary = short(record.get("summary"))
    if not summary:
        return None
    lowered = summary.lower()
    operational_markers = [
        "api",
        "agent-browser",
        "browser automation",
        "calendar event added",
        "cloud console",
        "enabled on the current project",
        "phone:",
        "preferred haircut barber",
        "reminder sc",
        "reminder scheduled",
        "scheduled and set to",
        "session key:",
        "spawn_failed",
        "telegram user id",
    ]
    if any(marker in lowered for marker in operational_markers):
        return None
    family = "medium_memory" if source == "medium_memory" else "relationship"
    prompt_prefix = (
        "Check in naturally about this current context"
        if source == "medium_memory"
        else "Use this durable context for a warm, human note"
    )
    return {
        "topic": norm_topic(summary),
        "topic_family": family,
        "prompt": f"{prompt_prefix}: {summary}",
        "source": source,
        "created_at": short(record.get("created_at"), 20),
        "expires_at": short(record.get("expires_at"), 20),
    }


def relationship_candidates(memory_summaries: list[str]) -> list[dict[str, str]]:
    joined = " ".join(memory_summaries).lower()
    candidates = [
        {
            "topic": "day_presence",
            "topic_family": "relationship",
            "prompt": "Send a short, specific note that feels like Rumi is present in Kenny's day, not checking a box.",
            "source": "relationship_pool",
            "created_at": "",
            "expires_at": "",
        },
        {
            "topic": "grounded_encouragement",
            "topic_family": "relationship",
            "prompt": "Offer one grounded bit of encouragement tied loosely to Kenny's current life, without advice or pressure.",
            "source": "relationship_pool",
            "created_at": "",
            "expires_at": "",
        },
        {
            "topic": "curiosity",
            "topic_family": "relationship",
            "prompt": "Ask one thoughtful, easy-to-answer question that helps Rumi know Kenny better.",
            "source": "relationship_pool",
            "created_at": "",
            "expires_at": "",
        },
        {
            "topic": "playful_warmth",
            "topic_family": "relationship",
            "prompt": "Use a little playful warmth or teasing, only if it stays kind and phone-sized.",
            "source": "relationship_pool",
            "created_at": "",
            "expires_at": "",
        },
    ]
    if "wife" in joined or "cayce" in joined:
        candidates.append(
            {
                "topic": "wife_warmth",
                "topic_family": "relationship",
                "prompt": "Nudge toward one small warm thought or gesture for Cayce, with no guilt or checklist tone.",
                "source": "relationship_pool",
                "created_at": "",
                "expires_at": "",
            }
        )
    if "sports" in joined or "philadelphia" in joined or "phillies" in joined:
        candidates.append(
            {
                "topic": "philly_sports",
                "topic_family": "relationship",
                "prompt": "Make a light fan-to-fan Philadelphia sports note without pretending to know live scores.",
                "source": "relationship_pool",
                "created_at": "",
                "expires_at": "",
            }
        )
    if "portugal" in joined:
        candidates.append(
            {
                "topic": "portugal_anticipation",
                "topic_family": "relationship",
                "prompt": "Say something warm about Portugal getting closer, without turning it into a task list.",
                "source": "relationship_pool",
                "created_at": "",
                "expires_at": "",
            }
        )
    if "plant" in joined or "monstera" in joined or "lemon tree" in joined:
        candidates.append(
            {
                "topic": "plant_person",
                "topic_family": "relationship",
                "prompt": "Make a small affectionate note about Kenny's plants and how much they seem to matter to him.",
                "source": "relationship_pool",
                "created_at": "",
                "expires_at": "",
            }
        )
    return candidates


def choose_candidate(
    candidates: list[dict[str, str]],
    history: list[dict[str, Any]],
    today_count: int,
    now: datetime,
    rng: random.Random,
) -> dict[str, str] | None:
    if not candidates:
        return None
    recent_topics = [str(record.get("topic") or "") for record in history[-10:]]
    recent_families = [str(record.get("topic_family") or "") for record in history[-8:]]
    recent_similar_topics = [str(record.get("topic") or "") for record in history[-14:]]
    broader_topics = [str(record.get("topic") or "") for record in history[-30:]]
    today_families = [
        str(record.get("topic_family") or "")
        for record in history
        if record.get("date_et") == today_from(now)
    ]

    def score(candidate: dict[str, str]) -> int:
        score_value = 0
        if candidate["topic"] in recent_topics:
            score_value += 160
        score_value += broader_topics.count(candidate["topic"]) * 18
        if today_count and candidate["topic_family"] in today_families:
            score_value += 60
        score_value += recent_families.count(candidate["topic_family"]) * 10
        if candidate["source"] == "medium_memory":
            score_value += 8
        if candidate["source"] == "relationship_pool":
            score_value += 22
        if any(similarity(candidate["topic"], recent) >= 0.45 for recent in recent_similar_topics):
            score_value += 70
        if candidate["topic"] == "phone_box_after_work" and now.hour < 16:
            score_value += 90
        expires_at = parse_date(candidate.get("expires_at"))
        if expires_at:
            days_until_expiry = (expires_at - now.date()).days
            if days_until_expiry < 0:
                score_value += 200
            elif days_until_expiry <= 3:
                score_value -= 12
        return score_value

    scored = sorted(
        (score(candidate), candidate["topic"], candidate)
        for candidate in candidates
    )
    best_score = scored[0][0]
    pool = [(value, candidate) for value, _topic, candidate in scored if value <= best_score + 55][:6]
    weights = [max(1, 70 - (value - best_score)) for value, _candidate in pool]
    return rng.choices([candidate for _value, candidate in pool], weights=weights, k=1)[0]


def random_target_for_day(today: str, seed: int | None = None) -> str:
    seed_value = f"{today}:{seed}" if seed is not None else today
    rng = random.Random(seed_value)
    minute_offset = rng.randint(0, WINDOW_MINUTES)
    hour = 10 + minute_offset // 60
    minute = minute_offset % 60
    return f"{hour:02d}:{minute:02d}"


def target_reached(now: datetime, target: str) -> bool:
    hour, minute = (int(part) for part in target.split(":", 1))
    target_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return now >= target_dt


def dry_no_reply(reason: str, today: str, now: datetime, target: str) -> None:
    print(
        json.dumps(
            {
                "status": "NO_REPLY",
                "reason": reason,
                "date_et": today,
                "now_et": now.isoformat(timespec="seconds"),
                "target_time_et": target,
            },
            separators=(",", ":"),
            ensure_ascii=False,
        )
    )


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
    now = parse_at(args.now) if args.now else datetime.now(ET)
    if now is None:
        print("NO_REPLY")
        return 0
    today = today_from(now)
    target = random_target_for_day(today, args.seed)

    if not (ACTIVE_START <= now.timetz().replace(tzinfo=None) <= ACTIVE_END):
        if args.dry_run:
            dry_no_reply("outside_active_window", today, now, target)
        else:
            print("NO_REPLY")
        return 0
    if not target_reached(now, target):
        if args.dry_run:
            dry_no_reply("before_daily_target", today, now, target)
        else:
            print("NO_REPLY")
        return 0

    history = load_jsonl(ENGAGEMENT_MEMORY)
    today_records = [record for record in history if record.get("date_et") == today]
    if today_records:
        if args.dry_run:
            dry_no_reply("already_sent_today", today, now, target)
        else:
            print("NO_REPLY")
        return 0

    candidates: list[dict[str, str]] = []
    memory_summaries: list[str] = []
    for record in load_jsonl(MEDIUM_MEMORY):
        if valid_today(record, today):
            memory_summaries.append(short(record.get("summary")))
            candidate = candidate_from_memory(record, "medium_memory")
            if candidate:
                candidates.append(candidate)
    for record in load_jsonl(LONG_MEMORY):
        memory_summaries.append(short(record.get("summary")))
        candidate = candidate_from_memory(record, "long_memory")
        if candidate:
            candidates.append(candidate)
    candidates.extend(relationship_candidates(memory_summaries))

    rng = random.Random(args.seed) if args.seed is not None else random.SystemRandom()
    selected = choose_candidate(candidates, history, len(today_records), now, rng)
    if selected is None:
        print("NO_REPLY")
        return 0

    style = choose_style(history, selected["topic_family"])
    record = {
        "at": now.isoformat(timespec="seconds"),
        "date_et": today,
        "target_time_et": target,
        "topic_family": selected["topic_family"],
        "topic": selected["topic"],
        "style": style,
    }
    append_jsonl(ENGAGEMENT_MEMORY, record, args.dry_run)

    payload = {
        "status": "OK",
        "now_et": now.isoformat(timespec="seconds"),
        "target_time_et": target,
        "selected": selected,
        "style": style,
        "message_contract": {
            "audience": "Kenny",
            "length": "one short phone-sized message",
            "voice": "Rumi: warm, natural, human, emotionally intelligent, not templated",
            "allow": [
                "occasional relationship-building presence",
                "warm curiosity",
                "light playful teasing",
                "grounded encouragement",
            ],
            "avoid": ["guilt", "pressure", "checklist tone", "generic checking in", "mentioning files/prompts/tools"],
        },
    }
    print(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
