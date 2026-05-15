#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
WORKSPACE_ROOT = Path(os.environ.get("OPENCLAW_WORKSPACE_DIR", "/home/node/.openclaw/workspace"))
MEMORY_DIR = WORKSPACE_ROOT / "memory"
MEDIUM_MEMORY = MEMORY_DIR / "medium_memory.jsonl"
LONG_MEMORY = MEMORY_DIR / "long_memory.jsonl"
EMAIL_TRIAGE_STATE = MEMORY_DIR / "email_triage_state.jsonl"
PROJECTS_FILE = MEMORY_DIR / "projects.jsonl"
PROJECT_RUNS_FILE = MEMORY_DIR / "project_runs.jsonl"
PROJECT_DETAILS_FILE = MEMORY_DIR / "project_details.jsonl"


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


def compact(value: Any, max_chars: int = 220) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "..."


def string_list(value: Any, limit: int = 12, max_chars: int = 160) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = compact(item, max_chars)
        if text:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def project_record(record: dict[str, Any], today: str) -> dict[str, Any] | None:
    project_id = re.sub(r"[^a-z0-9]+", "_", str(record.get("id") or "").strip().lower()).strip("_")[:80]
    title = compact(record.get("title"), 120)
    if not project_id or not title:
        return None

    status = compact(record.get("status"), 24).lower() or "active"
    if status not in {"active", "paused", "completed", "archived", "canceled"}:
        status = "active"

    project = {
        "id": project_id,
        "title": title,
        "status": status,
        "category": compact(record.get("category"), 50) or "general",
        "starts_at": valid_date(record.get("starts_at")),
        "ends_at": valid_date(record.get("ends_at")),
        "cadence": compact(record.get("cadence"), 40).lower() or "daily_or_when_useful",
        "current_phase": compact(record.get("current_phase"), 80) or "planning",
        "next_actions": string_list(record.get("next_actions")),
        "blockers": string_list(record.get("blockers"), limit=6),
        "last_discussed_at": valid_date(record.get("last_discussed_at")) or today,
        "last_nudged_at": valid_date(record.get("last_nudged_at")),
        "next_checkin_after": valid_date(record.get("next_checkin_after")) or today,
        "tone": compact(record.get("tone"), 120) or "helpful, light, not naggy",
        "created_at": valid_date(record.get("created_at")) or today,
        "updated_at": valid_date(record.get("updated_at")) or today,
    }
    return project


def project_run_record(record: dict[str, Any]) -> dict[str, Any] | None:
    run_id = compact(record.get("run_id"), 80)
    project_id = compact(record.get("project_id"), 80)
    if not run_id or not project_id:
        return None
    proposed_tasks = record.get("proposed_tasks") if isinstance(record.get("proposed_tasks"), list) else []
    proposed_calendar_events = (
        record.get("proposed_calendar_events")
        if isinstance(record.get("proposed_calendar_events"), list)
        else []
    )
    questions = string_list(record.get("questions"), limit=12, max_chars=220)
    errors = string_list(record.get("errors"), limit=20, max_chars=500)
    applied_changes = record.get("applied_changes") if isinstance(record.get("applied_changes"), list) else []
    return {
        "run_id": run_id,
        "project_id": project_id,
        "status": compact(record.get("status"), 40) or "pending_confirmation",
        "requested_at": compact(record.get("requested_at"), 40),
        "completed_at": compact(record.get("completed_at"), 40),
        "request": compact(record.get("request"), 500),
        "summary": compact(record.get("summary"), 800),
        "proposed_tasks": [item for item in proposed_tasks if isinstance(item, dict)],
        "proposed_calendar_events": [item for item in proposed_calendar_events if isinstance(item, dict)],
        "questions": questions,
        "errors": errors,
        "applied_changes": [item for item in applied_changes if isinstance(item, dict)],
        "updated_at": compact(record.get("updated_at"), 40),
    }


def project_detail_record(record: dict[str, Any], today: str) -> dict[str, Any] | None:
    project_id = compact(record.get("project_id"), 80)
    title = compact(record.get("title") or record.get("name"), 120)
    value = compact(record.get("value") or record.get("summary") or record.get("note"), 800)
    if not project_id or not (title or value):
        return None

    kind = re.sub(r"[^a-z0-9]+", "_", str(record.get("kind") or "note").strip().lower()).strip("_")[:40] or "note"
    detail_id_source = record.get("detail_id") or record.get("id") or f"{project_id}_{kind}_{title or value}"
    detail_id = re.sub(r"[^a-z0-9]+", "_", str(detail_id_source).strip().lower()).strip("_")[:100]
    if not detail_id:
        return None
    status = compact(record.get("status"), 24).lower() or "active"
    if status not in {"active", "archived"}:
        status = "active"
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    safe_metadata = {
        compact(key, 50): compact(value, 200)
        for key, value in metadata.items()
        if compact(key, 50) and compact(value, 200)
    }
    return {
        "detail_id": detail_id,
        "project_id": project_id,
        "kind": kind,
        "title": title or kind.replace("_", " "),
        "value": value,
        "starts_at": compact(record.get("starts_at") or record.get("from"), 80),
        "ends_at": compact(record.get("ends_at") or record.get("to"), 80),
        "source": compact(record.get("source"), 80) or "kenny",
        "url": compact(record.get("url"), 300),
        "tags": string_list(record.get("tags"), limit=8, max_chars=50),
        "status": status,
        "metadata": safe_metadata,
        "created_at": valid_date(record.get("created_at")) or today,
        "updated_at": valid_date(record.get("updated_at")) or today,
    }


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

    email_records = []
    for record in load_jsonl(EMAIL_TRIAGE_STATE):
        run_at = parse_run_at(record.get("run_at"))
        if run_at is not None and run_at >= email_cutoff:
            email_records.append(record)

    project_records_by_id = {}
    for raw in load_jsonl(PROJECTS_FILE):
        record = project_record(raw, today)
        if not record:
            continue
        project_records_by_id[record["id"]] = record
    project_records = sorted(project_records_by_id.values(), key=lambda item: item["id"])

    project_detail_records_by_id = {}
    for raw in load_jsonl(PROJECT_DETAILS_FILE):
        record = project_detail_record(raw, today)
        if not record:
            continue
        project_detail_records_by_id[record["detail_id"]] = record
    project_detail_records = sorted(
        project_detail_records_by_id.values(),
        key=lambda item: (str(item.get("project_id") or ""), str(item.get("kind") or ""), str(item.get("detail_id") or "")),
    )[-500:]

    project_run_records_by_id = {}
    for raw in load_jsonl(PROJECT_RUNS_FILE):
        record = project_run_record(raw)
        if not record:
            continue
        project_run_records_by_id[record["run_id"]] = record
    project_run_records = sorted(
        project_run_records_by_id.values(),
        key=lambda item: str(item.get("requested_at") or ""),
    )[-200:]

    write_jsonl(LONG_MEMORY, long_records, args.dry_run)
    write_jsonl(MEDIUM_MEMORY, medium_records, args.dry_run)
    write_jsonl(EMAIL_TRIAGE_STATE, email_records, args.dry_run)
    write_jsonl(PROJECTS_FILE, project_records, args.dry_run)
    write_jsonl(PROJECT_DETAILS_FILE, project_detail_records, args.dry_run)
    write_jsonl(PROJECT_RUNS_FILE, project_run_records, args.dry_run)

    audit = {
        "ok": True,
        "dry_run": args.dry_run,
        "medium_memory": len(medium_records),
        "long_memory": len(long_records),
        "email_triage_state": len(email_records),
        "projects": len(project_records),
        "project_details": len(project_detail_records),
        "project_runs": len(project_run_records),
    }
    if args.json:
        print(json.dumps(audit, separators=(",", ":"), ensure_ascii=False))
    else:
        print("NO_REPLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
