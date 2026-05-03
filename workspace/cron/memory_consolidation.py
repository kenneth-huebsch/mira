#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
WORKSPACE_ROOT = Path("/home/node/.openclaw/workspace")
MEMORY_DIR = WORKSPACE_ROOT / "memory"
MEDIUM_MEMORY = MEMORY_DIR / "medium_memory.jsonl"
LONG_MEMORY = MEMORY_DIR / "long_memory.jsonl"
ENGAGEMENT_PRIORITIES = MEMORY_DIR / "engagement_priorities.jsonl"
EMAIL_TRIAGE_STATE = MEMORY_DIR / "email_triage_state.jsonl"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deterministic memory and sidecar hygiene.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print JSON audit instead of NO_REPLY.")
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


def write_jsonl(path: Path, records: list[dict[str, Any]], dry_run: bool = False) -> None:
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        path.write_text("", encoding="utf-8")
        return
    content = "".join(json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n" for record in records)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(content)
        tmp = Path(handle.name)
    tmp.replace(path)


def valid_date(value: Any) -> str | None:
    text = str(value or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return None
    try:
        datetime.fromisoformat(f"{text}T00:00:00+00:00")
    except ValueError:
        return None
    return text


def normalized_key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def memory_record(record: dict[str, Any]) -> dict[str, str] | None:
    summary = re.sub(r"\s+", " ", str(record.get("summary") or "").strip())
    created_at = valid_date(record.get("created_at"))
    expires_at = valid_date(record.get("expires_at"))
    if not summary or not created_at or not expires_at:
        return None
    return {"summary": summary, "created_at": created_at, "expires_at": expires_at}


def dedupe_memory(records: list[dict[str, str]], already_seen: set[str] | None = None) -> list[dict[str, str]]:
    seen = already_seen if already_seen is not None else set()
    result: list[dict[str, str]] = []
    for record in records:
        key = normalized_key(record["summary"])
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(record)
    return result


def priority_record(record: dict[str, Any]) -> dict[str, str] | None:
    topic = re.sub(r"[^a-z0-9]+", "_", str(record.get("topic") or "").lower()).strip("_")[:80]
    kind = str(record.get("kind") or "general").strip().lower()
    if kind not in {"accountability", "relationship", "general", "medium_memory"}:
        kind = "general"
    prompt = re.sub(r"\s+", " ", str(record.get("prompt") or "").strip())
    created_at = valid_date(record.get("created_at"))
    expires_at = valid_date(record.get("expires_at"))
    if not topic or not prompt or not created_at or not expires_at:
        return None
    return {
        "topic": topic,
        "kind": kind,
        "prompt": prompt[:240],
        "created_at": created_at,
        "expires_at": expires_at,
    }


def parse_run_at(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def main() -> int:
    args = parse_args()
    today = datetime.now(ET).date().isoformat()
    now_utc = datetime.now(timezone.utc)
    email_cutoff = now_utc - timedelta(days=7)
    priority_created_cutoff = (datetime.now(ET).date() - timedelta(days=30)).isoformat()

    long_records = [record for raw in load_jsonl(LONG_MEMORY) if (record := memory_record(raw))]
    long_records = dedupe_memory(long_records)
    long_keys = {normalized_key(record["summary"]) for record in long_records}

    medium_records = []
    for raw in load_jsonl(MEDIUM_MEMORY):
        record = memory_record(raw)
        if not record:
            continue
        if record["expires_at"] < today:
            continue
        medium_records.append(record)
    medium_records = dedupe_memory(medium_records, already_seen=set(long_keys))

    priorities = []
    seen_topics: set[str] = set()
    for raw in load_jsonl(ENGAGEMENT_PRIORITIES):
        record = priority_record(raw)
        if not record:
            continue
        if record["expires_at"] < today or record["created_at"] < priority_created_cutoff:
            continue
        if record["topic"] in seen_topics:
            continue
        seen_topics.add(record["topic"])
        priorities.append(record)

    email_records = []
    for record in load_jsonl(EMAIL_TRIAGE_STATE):
        run_at = parse_run_at(record.get("run_at"))
        if run_at is not None and run_at >= email_cutoff:
            email_records.append(record)

    write_jsonl(LONG_MEMORY, long_records, args.dry_run)
    write_jsonl(MEDIUM_MEMORY, medium_records, args.dry_run)
    write_jsonl(ENGAGEMENT_PRIORITIES, priorities, args.dry_run)
    write_jsonl(EMAIL_TRIAGE_STATE, email_records, args.dry_run)

    audit = {
        "ok": True,
        "dry_run": args.dry_run,
        "medium_memory": len(medium_records),
        "long_memory": len(long_records),
        "engagement_priorities": len(priorities),
        "email_triage_state": len(email_records),
    }
    if args.json:
        print(json.dumps(audit, separators=(",", ":"), ensure_ascii=False))
    else:
        print("NO_REPLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
