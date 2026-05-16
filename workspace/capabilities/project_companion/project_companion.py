#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
WORKSPACE_ROOT = Path(os.environ.get("OPENCLAW_WORKSPACE_DIR", "/home/node/.openclaw/workspace"))
MEMORY_DIR = WORKSPACE_ROOT / "memory"
PROJECTS_FILE = MEMORY_DIR / "projects.jsonl"
PROJECT_RUNS_FILE = MEMORY_DIR / "project_runs.jsonl"
PROJECT_DETAILS_FILE = MEMORY_DIR / "project_details.jsonl"

ACTIVE_STATUSES = {"active", "paused"}
TERMINAL_STATUSES = {"completed", "archived", "canceled"}
RUN_PENDING_STATUSES = {"queued", "in_progress", "pending_confirmation", "needs_input", "failed"}
RUN_TERMINAL_STATUSES = {"completed", "applied", "applied_with_errors", "canceled"}
DETAIL_STATUSES = {"active", "archived"}
TASK_HOMES = {"personal", "work"}
DEFAULT_TONE = "helpful, light, not naggy"
DEFAULT_STALE_MINUTES = 90
TODOIST_HOME_NAMES = {
    "personal": "Kennys Personal Tasks",
    "work": "Kennys Work Todo List",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage Rumi's long-running project companion state.")
    parser.add_argument("--now", help="Override current time for tests (ISO-8601).")
    parser.add_argument("--dry-run", action="store_true", help="Do not write state.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    upsert = subparsers.add_parser("upsert", help="Create or update a project from JSON.")
    upsert.add_argument("--json", required=True, help="Project JSON object.")

    list_parser = subparsers.add_parser("list", help="List projects.")
    list_parser.add_argument("--status", default="active", help="Project status to list, or 'all'.")
    list_parser.add_argument("--json", action="store_true", help="Print JSON instead of a text summary.")

    review = subparsers.add_parser("review", help="Select one project check-in if due.")
    review.add_argument("--json", action="store_true", help="Print explicit JSON NO_REPLY payloads.")

    complete = subparsers.add_parser("complete", help="Mark a project complete, archived, paused, active, or canceled.")
    complete.add_argument("--id", required=True, help="Project id.")
    complete.add_argument("--status", default="completed", choices=sorted(ACTIVE_STATUSES | TERMINAL_STATUSES))

    detail_upsert = subparsers.add_parser("detail-upsert", help="Create or update a project-scoped detail from JSON.")
    detail_upsert.add_argument("--json", required=True, help="Project detail JSON object or array.")

    details_upsert = subparsers.add_parser("details-upsert", help="Create or update one or more project-scoped details from JSON.")
    details_upsert.add_argument("--json", required=True, help="Project detail JSON object or array.")

    detail_list = subparsers.add_parser("detail-list", help="List project-scoped details.")
    detail_list.add_argument("--id", help="Project id.")
    detail_list.add_argument("--status", default="active", choices=["active", "archived", "all"])

    detail_archive = subparsers.add_parser("detail-archive", help="Archive a project-scoped detail.")
    detail_archive.add_argument("--detail-id", required=True, help="Project detail id.")

    plan = subparsers.add_parser("plan", help="Create a resumable planning run for a project.")
    plan.add_argument("--id", required=True, help="Project id.")
    plan.add_argument("--request", default="", help="Short description of Kenny's planning request.")
    plan.add_argument("--task-home", default="personal", choices=sorted(TASK_HOMES))

    next_worker = subparsers.add_parser("next-worker-run", help="Claim the next queued project planning run.")
    next_worker.add_argument("--stale-minutes", type=int, default=DEFAULT_STALE_MINUTES, help="Requeue in-progress runs older than this many minutes.")

    complete_run = subparsers.add_parser("complete-run", help="Save worker output for a claimed planning run.")
    complete_run.add_argument("--run-id", required=True, help="Planning run id.")
    complete_run.add_argument("--json", help="Worker result JSON.")
    complete_run.add_argument("--json-stdin", action="store_true", help="Read worker result JSON from stdin.")

    fail_run = subparsers.add_parser("fail-run", help="Record a worker failure for a planning run.")
    fail_run.add_argument("--run-id", required=True, help="Planning run id.")
    fail_run.add_argument("--error", required=True, help="Failure summary.")

    propose = subparsers.add_parser("propose", help="Return the latest pending proposal for a project or run.")
    propose.add_argument("--id", help="Project id.")
    propose.add_argument("--run-id", help="Planning run id.")

    apply = subparsers.add_parser("apply", help="Apply or record confirmed external changes for a planning run.")
    apply.add_argument("--run-id", required=True, help="Planning run id.")
    apply.add_argument("--confirmed-json", help="JSON describing the confirmed subset to apply.")
    apply.add_argument("--confirmed-json-stdin", action="store_true", help="Read confirmed subset JSON from stdin.")

    audit = subparsers.add_parser("audit", help="Show project and run state.")
    audit.add_argument("--id", help="Project id.")
    audit.add_argument("--run-id", help="Planning run id.")

    return parser.parse_args()


def now_et(raw: str | None = None) -> datetime:
    if not raw:
        return datetime.now(ET)
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ET)
    return parsed.astimezone(ET)


def today_from(now: datetime) -> str:
    return now.date().isoformat()


def iso_from(now: datetime) -> str:
    return now.isoformat(timespec="seconds")


def parse_iso(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ET)
    return parsed.astimezone(ET)


def add_days(day: str, days: int) -> str:
    return (date.fromisoformat(day) + timedelta(days=days)).isoformat()


def compact(value: Any, max_chars: int = 220) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "..."


def slug(value: Any, fallback: str = "project") -> str:
    text = compact(value, 80).lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return normalized or fallback


def first_present(raw: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = raw.get(key)
        if value is not None and value != "" and value != []:
            return value
    return None


def infer_category(raw: dict[str, Any], title: str) -> str:
    explicit = compact(raw.get("category"), 50)
    if explicit:
        return explicit
    haystack = f"{title} {raw.get('id') or ''}".lower()
    if any(term in haystack for term in ["trip", "travel", "vacation", "portugal", "airbnb", "flight", "lodging"]):
        return "travel"
    return "general"


def valid_date(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


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


def non_negative_int(value: Any) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return max(0, parsed)


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


def write_jsonl(path: Path, records: list[dict[str, Any]], dry_run: bool) -> None:
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n" for record in records)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(content)
        tmp = Path(handle.name)
    tmp.replace(path)


def normalize_project(raw: dict[str, Any], now: datetime) -> dict[str, Any] | None:
    title = compact(raw.get("title"), 120)
    project_id = slug(raw.get("id") or title)
    if not title or not project_id:
        return None

    today = today_from(now)
    status = compact(raw.get("status"), 24).lower() or "active"
    if status not in ACTIVE_STATUSES and status not in TERMINAL_STATUSES:
        status = "active"

    cadence = compact(raw.get("cadence"), 40).lower() or "daily_or_when_useful"
    todoist_task_ids = raw.get("todoist_task_ids") if isinstance(raw.get("todoist_task_ids"), list) else []
    calendar_event_ids = raw.get("calendar_event_ids") if isinstance(raw.get("calendar_event_ids"), list) else []
    starts_at = first_present(raw, "starts_at", "start_date", "target_date", "departure_date", "due_date")
    ends_at = first_present(raw, "ends_at", "end_date", "return_date", "finish_date")
    current_phase = first_present(raw, "current_phase", "phase", "stage")
    next_actions = first_present(raw, "next_actions", "actions", "tasks", "todos")
    return {
        "id": project_id,
        "title": title,
        "status": status,
        "category": infer_category(raw, title),
        "starts_at": valid_date(starts_at),
        "ends_at": valid_date(ends_at),
        "cadence": cadence,
        "current_phase": compact(current_phase, 80) or "planning",
        "next_actions": string_list(next_actions),
        "blockers": string_list(raw.get("blockers"), limit=6),
        "last_discussed_at": valid_date(raw.get("last_discussed_at")) or today,
        "last_nudged_at": valid_date(raw.get("last_nudged_at")),
        "next_checkin_after": valid_date(raw.get("next_checkin_after")) or today,
        "tone": compact(raw.get("tone"), 120) or DEFAULT_TONE,
        "latest_run_id": compact(raw.get("latest_run_id"), 80),
        "artifact_summary": compact(raw.get("artifact_summary"), 240),
        "todoist_task_ids": [compact(item, 80) for item in todoist_task_ids if compact(item, 80)],
        "calendar_event_ids": [compact(item, 120) for item in calendar_event_ids if compact(item, 120)],
        "pending_confirmation": bool(raw.get("pending_confirmation")),
        "last_audit_at": valid_date(raw.get("last_audit_at")),
        "created_at": valid_date(raw.get("created_at")) or today,
        "updated_at": today,
    }


def merge_project(existing: dict[str, Any] | None, incoming: dict[str, Any], now: datetime) -> dict[str, Any]:
    if existing is None:
        return incoming
    merged = dict(existing)
    for key, value in incoming.items():
        if key == "created_at":
            continue
        if value is not None and value != [] and value != "":
            merged[key] = value
    merged["created_at"] = valid_date(existing.get("created_at")) or incoming["created_at"]
    merged["updated_at"] = today_from(now)
    return normalize_project(merged, now) or incoming


def load_projects(now: datetime) -> list[dict[str, Any]]:
    return [project for raw in load_jsonl(PROJECTS_FILE) if (project := normalize_project(raw, now))]


def save_projects(projects: list[dict[str, Any]], dry_run: bool) -> None:
    write_jsonl(PROJECTS_FILE, sorted(projects, key=lambda item: item["id"]), dry_run)


def normalize_detail(raw: dict[str, Any], now: datetime) -> dict[str, Any] | None:
    project_id = compact(raw.get("project_id"), 80)
    title = compact(raw.get("title") or raw.get("name"), 120)
    value = compact(raw.get("value") or raw.get("summary") or raw.get("note"), 800)
    if not project_id or not (title or value):
        return None

    kind = slug(raw.get("kind") or "note", fallback="note")[:40]
    detail_id = slug(raw.get("detail_id") or raw.get("id") or f"{project_id}_{kind}_{title or value}", fallback="detail")[:100]
    status = compact(raw.get("status"), 24).lower() or "active"
    if status not in DETAIL_STATUSES:
        status = "active"
    today = today_from(now)
    metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
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
        "starts_at": compact(raw.get("starts_at") or raw.get("from"), 80),
        "ends_at": compact(raw.get("ends_at") or raw.get("to"), 80),
        "source": compact(raw.get("source"), 80) or "kenny",
        "url": compact(raw.get("url"), 300),
        "tags": string_list(raw.get("tags"), limit=8, max_chars=50),
        "status": status,
        "metadata": safe_metadata,
        "created_at": valid_date(raw.get("created_at")) or today,
        "updated_at": today,
    }


def merge_detail(existing: dict[str, Any] | None, incoming: dict[str, Any], now: datetime) -> dict[str, Any]:
    if existing is None:
        return incoming
    merged = dict(existing)
    for key, value in incoming.items():
        if key == "created_at":
            continue
        if value is not None and value != [] and value != "":
            merged[key] = value
    merged["created_at"] = valid_date(existing.get("created_at")) or incoming["created_at"]
    merged["updated_at"] = today_from(now)
    return normalize_detail(merged, now) or incoming


def load_details(now: datetime) -> list[dict[str, Any]]:
    return [detail for raw in load_jsonl(PROJECT_DETAILS_FILE) if (detail := normalize_detail(raw, now))]


def save_details(details: list[dict[str, Any]], dry_run: bool) -> None:
    write_jsonl(PROJECT_DETAILS_FILE, sorted(details, key=lambda item: (item["project_id"], item["kind"], item["detail_id"])), dry_run)


def details_for_project(details: list[dict[str, Any]], project_id: str, include_archived: bool = False, limit: int = 30) -> list[dict[str, Any]]:
    matches = [
        detail
        for detail in details
        if detail["project_id"] == project_id and (include_archived or detail.get("status") == "active")
    ]
    return sorted(matches, key=lambda item: (item.get("status") != "active", item.get("kind", ""), item.get("title", "")))[:limit]


def normalize_task_home(value: Any) -> str:
    home = compact(value, 20).lower()
    return home if home in TASK_HOMES else "personal"


def normalize_task(raw: dict[str, Any], default_home: str = "personal") -> dict[str, Any] | None:
    content = compact(raw.get("content") or raw.get("title"), 180)
    if not content:
        return None
    home = normalize_task_home(raw.get("task_home") or default_home)
    return {
        "content": content,
        "description": compact(raw.get("description"), 500),
        "due": compact(raw.get("due") or raw.get("due_string") or raw.get("dueString"), 80),
        "priority": compact(raw.get("priority"), 20),
        "task_home": home,
        "todoist_project": TODOIST_HOME_NAMES[home],
        "labels": string_list(raw.get("labels"), limit=8, max_chars=50),
        "external_id": compact(raw.get("external_id") or raw.get("id"), 100),
        "status": compact(raw.get("status"), 30) or "proposed",
    }


def normalize_calendar_event(raw: dict[str, Any]) -> dict[str, Any] | None:
    title = compact(raw.get("title") or raw.get("summary"), 180)
    if not title:
        return None
    return {
        "title": title,
        "calendar": compact(raw.get("calendar"), 120) or "kenneth.huebsch@gmail.com",
        "starts_at": compact(raw.get("starts_at") or raw.get("start") or raw.get("from"), 80),
        "ends_at": compact(raw.get("ends_at") or raw.get("end") or raw.get("to"), 80),
        "all_day": bool(raw.get("all_day", True)),
        "external_id": compact(raw.get("external_id") or raw.get("id"), 120),
        "status": compact(raw.get("status"), 30) or "proposed",
    }


def normalize_run(raw: dict[str, Any], now: datetime) -> dict[str, Any] | None:
    run_id = compact(raw.get("run_id"), 80)
    project_id = compact(raw.get("project_id"), 80)
    if not run_id or not project_id:
        return None
    status = compact(raw.get("status"), 40) or "queued"
    if status not in RUN_PENDING_STATUSES and status not in RUN_TERMINAL_STATUSES:
        status = "queued"
    proposed_tasks = []
    if isinstance(raw.get("proposed_tasks"), list):
        for item in raw["proposed_tasks"]:
            if isinstance(item, dict) and (task := normalize_task(item)):
                proposed_tasks.append(task)
    proposed_events = []
    if isinstance(raw.get("proposed_calendar_events"), list):
        for item in raw["proposed_calendar_events"]:
            if isinstance(item, dict) and (event := normalize_calendar_event(item)):
                proposed_events.append(event)
    applied_changes = raw.get("applied_changes") if isinstance(raw.get("applied_changes"), list) else []
    errors = raw.get("errors") if isinstance(raw.get("errors"), list) else []
    questions = string_list(raw.get("questions"), limit=12, max_chars=220)
    return {
        "run_id": run_id,
        "project_id": project_id,
        "status": status,
        "requested_at": compact(raw.get("requested_at"), 40) or iso_from(now),
        "claimed_at": compact(raw.get("claimed_at"), 40),
        "completed_at": compact(raw.get("completed_at"), 40),
        "request": compact(raw.get("request"), 500),
        "task_home": normalize_task_home(raw.get("task_home")),
        "summary": compact(raw.get("summary"), 800),
        "proposed_tasks": proposed_tasks,
        "proposed_calendar_events": proposed_events,
        "questions": questions,
        "errors": [compact(item, 500) for item in errors if compact(item, 500)],
        "applied_changes": [item for item in applied_changes if isinstance(item, dict)],
        "attempt_count": non_negative_int(raw.get("attempt_count")),
        "updated_at": compact(raw.get("updated_at"), 40) or iso_from(now),
    }


def load_runs(now: datetime) -> list[dict[str, Any]]:
    return [run for raw in load_jsonl(PROJECT_RUNS_FILE) if (run := normalize_run(raw, now))]


def save_runs(runs: list[dict[str, Any]], dry_run: bool) -> None:
    write_jsonl(PROJECT_RUNS_FILE, sorted(runs, key=lambda item: item["requested_at"]), dry_run)


def latest_run_for_project(runs: list[dict[str, Any]], project_id: str) -> dict[str, Any] | None:
    matches = [run for run in runs if run["project_id"] == project_id]
    if not matches:
        return None
    return sorted(matches, key=lambda item: item["requested_at"], reverse=True)[0]


def run_needs_attention(run: dict[str, Any]) -> bool:
    return run.get("status") in {"queued", "in_progress", "pending_confirmation", "needs_input", "failed"}


def run_has_pending_response(run: dict[str, Any]) -> bool:
    return run.get("status") in {"pending_confirmation", "needs_input", "failed"}


def requeue_stale_runs(runs: list[dict[str, Any]], now: datetime, stale_minutes: int) -> None:
    cutoff = now - timedelta(minutes=max(stale_minutes, 1))
    for run in runs:
        if run.get("status") != "in_progress":
            continue
        claimed_at = parse_iso(run.get("claimed_at"))
        if claimed_at and claimed_at >= cutoff:
            continue
        run["status"] = "queued"
        run["claimed_at"] = ""
        run["updated_at"] = iso_from(now)
        run["errors"].append("Worker run was requeued after going stale.")


def select_next_worker_run(runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    queued = [run for run in runs if run.get("status") == "queued"]
    if not queued:
        return None
    return sorted(queued, key=lambda item: item["requested_at"])[0]


def set_project_run_state(projects: list[dict[str, Any]], run: dict[str, Any], now: datetime) -> None:
    pending = run_has_pending_response(run)
    for project in projects:
        if project["id"] != run["project_id"]:
            continue
        project["latest_run_id"] = run["run_id"]
        project["pending_confirmation"] = pending
        if run.get("summary"):
            project["artifact_summary"] = run["summary"]
        project["updated_at"] = today_from(now)
        break


def project_score(project: dict[str, Any], today: str) -> tuple[int, str]:
    score = 0
    if project.get("next_actions"):
        score += 20
    if project.get("blockers"):
        score += 15
    if project.get("pending_confirmation"):
        score += 25
    starts_at = valid_date(project.get("starts_at"))
    if starts_at:
        days_until = (date.fromisoformat(starts_at) - date.fromisoformat(today)).days
        if 0 <= days_until <= 45:
            score += max(0, 45 - days_until)
        elif days_until < 0:
            score -= 10
    last_discussed = valid_date(project.get("last_discussed_at"))
    if last_discussed:
        days_since = (date.fromisoformat(today) - date.fromisoformat(last_discussed)).days
        score += min(max(days_since, 0), 14)
    return (score, str(project.get("updated_at") or ""))


def next_interval_days(cadence: str) -> int:
    normalized = cadence.lower().replace("-", "_")
    if normalized in {"daily", "daily_or_when_useful"}:
        return 1
    if normalized in {"twice_weekly", "every_few_days"}:
        return 3
    if normalized in {"weekly", "low"}:
        return 7
    return 2


def due_projects(projects: list[dict[str, Any]], today: str) -> list[dict[str, Any]]:
    due = []
    for project in projects:
        if project.get("status") != "active":
            continue
        if project.get("last_nudged_at") == today:
            continue
        next_checkin = valid_date(project.get("next_checkin_after")) or today
        if next_checkin > today:
            continue
        if not project.get("next_actions") and not project.get("blockers") and not project.get("pending_confirmation"):
            continue
        due.append(project)
    return sorted(due, key=lambda item: project_score(item, today), reverse=True)


def review_payload(project: dict[str, Any], today: str, project_details: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    starts_at = valid_date(project.get("starts_at"))
    days_until = None
    if starts_at:
        days_until = (date.fromisoformat(starts_at) - date.fromisoformat(today)).days
    active_details = project_details or []
    return {
        "status": "OK",
        "kind": "project_companion_checkin",
        "date_et": today,
        "project": {
            "id": project["id"],
            "title": project["title"],
            "category": project["category"],
            "current_phase": project["current_phase"],
            "starts_at": starts_at,
            "ends_at": project.get("ends_at"),
            "days_until_start": days_until,
            "next_actions": project.get("next_actions", [])[:5],
            "blockers": project.get("blockers", [])[:3],
            "pending_confirmation": project.get("pending_confirmation", False),
            "latest_run_id": project.get("latest_run_id"),
            "artifact_summary": project.get("artifact_summary"),
            "project_details": [
                {
                    "kind": detail["kind"],
                    "title": detail["title"],
                    "value": detail["value"],
                    "starts_at": detail.get("starts_at"),
                    "ends_at": detail.get("ends_at"),
                }
                for detail in active_details[:5]
            ],
            "tone": project.get("tone") or DEFAULT_TONE,
            "cadence": project.get("cadence"),
        },
        "message_guidance": {
            "goal": "Help Kenny make one concrete bit of progress on this long-running project.",
            "style": "One short, natural Rumi message. Be specific, low-pressure, and do not sound like a task manager.",
            "avoid": ["Reminder:", "checking in", "guilt", "multi-step lecture"],
        },
    }


def print_json(value: Any) -> None:
    print(json.dumps(value, separators=(",", ":"), ensure_ascii=False))


def command_upsert(args: argparse.Namespace, now: datetime) -> int:
    try:
        parsed = json.loads(args.json)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise SystemExit("project payload must be a JSON object")
    incoming = normalize_project(parsed, now)
    if incoming is None:
        raise SystemExit("project payload requires a title")

    projects = load_projects(now)
    existing_by_id = {project["id"]: project for project in projects}
    merged = merge_project(existing_by_id.get(incoming["id"]), incoming, now)
    existing_by_id[merged["id"]] = merged
    save_projects(list(existing_by_id.values()), args.dry_run)
    print_json({"status": "OK", "project": merged, "dry_run": args.dry_run})
    return 0


def command_list(args: argparse.Namespace, now: datetime) -> int:
    projects = load_projects(now)
    if args.status != "all":
        projects = [project for project in projects if project.get("status") == args.status]
    projects = sorted(projects, key=lambda item: (item.get("status") != "active", item.get("title", "")))
    if args.json:
        print_json({"status": "OK", "projects": projects})
    elif not projects:
        print("NO_PROJECTS")
    else:
        for project in projects:
            actions = "; ".join(project.get("next_actions", [])[:3])
            print(f"{project['id']}: {project['title']} ({project['status']}) {actions}".rstrip())
    return 0


def command_review(args: argparse.Namespace, now: datetime) -> int:
    today = today_from(now)
    projects = load_projects(now)
    due = due_projects(projects, today)
    if not due:
        if args.json:
            print_json({"status": "NO_REPLY", "reason": "no_due_projects"})
        else:
            print("NO_REPLY")
        return 0

    selected = due[0]
    detail_records = details_for_project(load_details(now), selected["id"], limit=5)
    payload = review_payload(selected, today, detail_records)
    for project in projects:
        if project["id"] == selected["id"]:
            project["last_nudged_at"] = today
            project["next_checkin_after"] = add_days(today, next_interval_days(str(project.get("cadence") or "")))
            project["updated_at"] = today
            break
    save_projects(projects, args.dry_run)
    if args.dry_run:
        payload["dry_run"] = True
    print_json(payload)
    return 0


def command_complete(args: argparse.Namespace, now: datetime) -> int:
    projects = load_projects(now)
    found = False
    today = today_from(now)
    for project in projects:
        if project["id"] == args.id:
            project["status"] = args.status
            project["updated_at"] = today
            found = True
            break
    if not found:
        raise SystemExit(f"unknown project id: {args.id}")
    save_projects(projects, args.dry_run)
    print_json({"status": "OK", "id": args.id, "project_status": args.status, "dry_run": args.dry_run})
    return 0


def command_detail_upsert(args: argparse.Namespace, now: datetime) -> int:
    return command_details_upsert(args, now, single_command=True)


def parse_detail_payload(raw_json: str) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON: {exc}") from exc
    if isinstance(parsed, dict):
        return [parsed]
    if isinstance(parsed, list) and all(isinstance(item, dict) for item in parsed):
        return parsed
    raise SystemExit("project detail payload must be a JSON object or array of objects")


def command_details_upsert(args: argparse.Namespace, now: datetime, single_command: bool = False) -> int:
    parsed_items = parse_detail_payload(args.json)
    incoming_details: list[dict[str, Any]] = []
    for parsed in parsed_items:
        incoming = normalize_detail(parsed, now)
        if incoming is None:
            raise SystemExit("project detail payload requires project_id and title or value")
        incoming_details.append(incoming)

    projects = load_projects(now)
    project_ids = {project["id"] for project in projects}
    for incoming in incoming_details:
        if incoming["project_id"] not in project_ids:
            raise SystemExit(f"unknown project id: {incoming['project_id']}")

    details = load_details(now)
    existing_by_id = {detail["detail_id"]: detail for detail in details}
    merged_details: list[dict[str, Any]] = []
    for incoming in incoming_details:
        merged = merge_detail(existing_by_id.get(incoming["detail_id"]), incoming, now)
        existing_by_id[merged["detail_id"]] = merged
        merged_details.append(merged)

    save_details(list(existing_by_id.values()), args.dry_run)
    if single_command and len(merged_details) == 1:
        print_json({"status": "OK", "detail": merged_details[0], "dry_run": args.dry_run})
    else:
        print_json({"status": "OK", "details": merged_details, "dry_run": args.dry_run})
    return 0


def command_detail_list(args: argparse.Namespace, now: datetime) -> int:
    details = load_details(now)
    if args.id:
        details = [detail for detail in details if detail["project_id"] == args.id]
    if args.status != "all":
        details = [detail for detail in details if detail.get("status") == args.status]
    print_json({"status": "OK", "details": details})
    return 0


def command_detail_archive(args: argparse.Namespace, now: datetime) -> int:
    details = load_details(now)
    found = False
    for detail in details:
        if detail["detail_id"] != args.detail_id:
            continue
        detail["status"] = "archived"
        detail["updated_at"] = today_from(now)
        found = True
        break
    if not found:
        raise SystemExit(f"unknown detail id: {args.detail_id}")
    save_details(details, args.dry_run)
    print_json({"status": "OK", "detail_id": args.detail_id, "detail_status": "archived", "dry_run": args.dry_run})
    return 0


def project_proposals(project: dict[str, Any], task_home: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    proposed_tasks = [
        normalize_task({"content": action, "task_home": task_home, "labels": [f"project:{project['id']}"]}, task_home)
        for action in project.get("next_actions", [])
    ]
    proposed_tasks = [task for task in proposed_tasks if task]
    questions: list[str] = []
    if not proposed_tasks:
        questions.append("What are the next concrete actions for this project?")
    if project.get("category") == "travel" and not project.get("starts_at"):
        questions.append("What is the trip start date?")
    return proposed_tasks, [], questions


def command_plan(args: argparse.Namespace, now: datetime) -> int:
    projects = load_projects(now)
    project = next((item for item in projects if item["id"] == args.id), None)
    if not project:
        raise SystemExit(f"unknown project id: {args.id}")
    task_home = normalize_task_home(args.task_home)
    run_id = f"{project['id']}_{today_from(now).replace('-', '')}_{uuid.uuid4().hex[:8]}"
    run = {
        "run_id": run_id,
        "project_id": project["id"],
        "status": "queued",
        "requested_at": iso_from(now),
        "claimed_at": "",
        "completed_at": "",
        "request": compact(args.request, 500),
        "task_home": task_home,
        "summary": f"Queued project planning worker run for {project['title']}.",
        "proposed_tasks": [],
        "proposed_calendar_events": [],
        "questions": [],
        "errors": [],
        "applied_changes": [],
        "attempt_count": 0,
        "updated_at": iso_from(now),
    }
    runs = load_runs(now)
    runs.append(normalize_run(run, now) or run)
    for item in projects:
        if item["id"] == project["id"]:
            item["latest_run_id"] = run_id
            item["pending_confirmation"] = False
            item["artifact_summary"] = run["summary"]
            item["updated_at"] = today_from(now)
            break
    save_runs(runs, args.dry_run)
    save_projects(projects, args.dry_run)
    print_json({"status": "OK", "run": run, "dry_run": args.dry_run})
    return 0


def command_next_worker_run(args: argparse.Namespace, now: datetime) -> int:
    runs = load_runs(now)
    requeue_stale_runs(runs, now, args.stale_minutes)
    run = select_next_worker_run(runs)
    if run is None:
        save_runs(runs, args.dry_run)
        print("NO_REPLY")
        return 0

    projects = load_projects(now)
    project = next((item for item in projects if item["id"] == run["project_id"]), None)
    if project is None:
        run["status"] = "failed"
        run["errors"].append(f"Unknown project id: {run['project_id']}")
        run["updated_at"] = iso_from(now)
        save_runs(runs, args.dry_run)
        print("NO_REPLY")
        return 0

    run["status"] = "in_progress"
    run["claimed_at"] = iso_from(now)
    run["attempt_count"] = int(run.get("attempt_count") or 0) + 1
    run["updated_at"] = iso_from(now)
    save_runs(runs, args.dry_run)
    project_details = details_for_project(load_details(now), project["id"], limit=40)
    print_json(
        {
            "status": "OK",
            "kind": "project_planning_worker_run",
            "run": run,
            "project": project,
            "project_details": project_details,
            "rules": {
                "todoist_task_homes": TODOIST_HOME_NAMES,
                "no_new_todoist_projects": True,
                "external_changes_require_confirmation": True,
                "write_output_with": "complete-run",
            },
            "dry_run": args.dry_run,
        }
    )
    return 0


def proposed_status(tasks: list[dict[str, Any]], events: list[dict[str, Any]], questions: list[str]) -> str:
    if tasks or events:
        return "pending_confirmation"
    if questions:
        return "needs_input"
    return "completed"


def command_complete_run(args: argparse.Namespace, now: datetime) -> int:
    raw_json = sys.stdin.read() if args.json_stdin else args.json
    if not raw_json:
        raise SystemExit("worker result requires --json or --json-stdin")
    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise SystemExit("worker result must be a JSON object")

    runs = load_runs(now)
    run = next((item for item in runs if item["run_id"] == args.run_id), None)
    if not run:
        raise SystemExit(f"unknown run id: {args.run_id}")

    task_home = normalize_task_home(parsed.get("task_home") or run.get("task_home"))
    tasks = []
    if isinstance(parsed.get("proposed_tasks"), list):
        for item in parsed["proposed_tasks"]:
            if isinstance(item, dict) and (task := normalize_task(item, task_home)):
                tasks.append(task)
    events = []
    if isinstance(parsed.get("proposed_calendar_events"), list):
        for item in parsed["proposed_calendar_events"]:
            if isinstance(item, dict) and (event := normalize_calendar_event(item)):
                events.append(event)
    questions = string_list(parsed.get("questions"), limit=12, max_chars=220)
    new_errors = string_list(parsed.get("errors"), limit=12, max_chars=500)

    run["task_home"] = task_home
    run["summary"] = compact(parsed.get("summary"), 800) or run["summary"]
    run["proposed_tasks"] = tasks
    run["proposed_calendar_events"] = events
    run["questions"] = questions
    run["errors"].extend(new_errors)
    run["status"] = "failed" if new_errors and not (tasks or events or questions) else proposed_status(tasks, events, questions)
    run["completed_at"] = iso_from(now)
    run["updated_at"] = iso_from(now)
    save_runs(runs, args.dry_run)

    projects = load_projects(now)
    set_project_run_state(projects, run, now)
    save_projects(projects, args.dry_run)
    print_json({"status": "OK", "run": run, "dry_run": args.dry_run})
    return 0


def command_fail_run(args: argparse.Namespace, now: datetime) -> int:
    runs = load_runs(now)
    run = next((item for item in runs if item["run_id"] == args.run_id), None)
    if not run:
        raise SystemExit(f"unknown run id: {args.run_id}")
    run["status"] = "failed"
    run["errors"].append(compact(args.error, 500))
    run["completed_at"] = iso_from(now)
    run["updated_at"] = iso_from(now)
    save_runs(runs, args.dry_run)

    projects = load_projects(now)
    set_project_run_state(projects, run, now)
    save_projects(projects, args.dry_run)
    print_json({"status": "OK", "run_id": run["run_id"], "project_id": run["project_id"], "dry_run": args.dry_run})
    return 0


def select_run(args: argparse.Namespace, now: datetime) -> dict[str, Any]:
    runs = load_runs(now)
    if getattr(args, "run_id", None):
        run = next((item for item in runs if item["run_id"] == args.run_id), None)
        if not run:
            raise SystemExit(f"unknown run id: {args.run_id}")
        return run
    if getattr(args, "id", None):
        run = latest_run_for_project(runs, args.id)
        if not run:
            raise SystemExit(f"no runs for project id: {args.id}")
        return run
    raise SystemExit("provide --id or --run-id")


def command_propose(args: argparse.Namespace, now: datetime) -> int:
    run = select_run(args, now)
    project_details = details_for_project(load_details(now), run["project_id"], limit=30)
    print_json(
        {
            "status": "OK",
            "run_id": run["run_id"],
            "project_id": run["project_id"],
            "run_status": run["status"],
            "request": run.get("request"),
            "summary": run["summary"],
            "proposed_tasks": run["proposed_tasks"],
            "proposed_calendar_events": run["proposed_calendar_events"],
            "project_details": project_details,
            "questions": run["questions"],
            "rules": {
                "todoist_task_homes": TODOIST_HOME_NAMES,
                "no_new_todoist_projects": True,
                "external_changes_require_confirmation": True,
            },
        }
    )
    return 0


def calendar_create(event: dict[str, Any]) -> dict[str, Any]:
    calendar = event["calendar"]
    command = [
        "gog",
        "calendar",
        "create",
        calendar,
        "--summary",
        event["title"],
        "--from",
        event["starts_at"],
        "--to",
        event["ends_at"],
        "--account",
        "rumi.openclaw@gmail.com",
        "--json",
    ]
    if event.get("all_day"):
        command.append("--all-day")
    proc = subprocess.run(command, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip() or "calendar create failed")
    parsed = json.loads(proc.stdout)
    created = parsed.get("event") if isinstance(parsed, dict) else None
    if not isinstance(created, dict):
        raise RuntimeError("calendar create returned unexpected JSON")
    return {"type": "calendar_event", "external_id": compact(created.get("id"), 120), "title": event["title"], "calendar": calendar}


def confirmed_subset(run: dict[str, Any], payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    task_indexes = payload.get("task_indexes")
    event_indexes = payload.get("calendar_event_indexes")
    tasks = run["proposed_tasks"]
    events = run["proposed_calendar_events"]
    task_home = normalize_task_home(payload.get("task_home") or run.get("task_home"))
    if isinstance(payload.get("tasks"), list):
        tasks = [
            task
            for item in payload["tasks"]
            if isinstance(item, dict) and (task := normalize_task(item, task_home))
        ]
    if isinstance(payload.get("calendar_events"), list):
        events = [
            event
            for item in payload["calendar_events"]
            if isinstance(item, dict) and (event := normalize_calendar_event(item))
        ]
    if isinstance(task_indexes, list):
        tasks = [task for index, task in enumerate(tasks) if index in task_indexes]
    if isinstance(event_indexes, list):
        events = [event for index, event in enumerate(events) if index in event_indexes]
    return tasks, events


def command_apply(args: argparse.Namespace, now: datetime) -> int:
    raw_json = sys.stdin.read() if args.confirmed_json_stdin else args.confirmed_json
    if not raw_json:
        raise SystemExit("confirmed payload requires --confirmed-json or --confirmed-json-stdin")
    try:
        confirmed = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid confirmed JSON: {exc}") from exc
    if not isinstance(confirmed, dict):
        raise SystemExit("confirmed payload must be a JSON object")
    if not confirmed.get("confirmed"):
        raise SystemExit("confirmed payload must include confirmed: true")

    runs = load_runs(now)
    run = next((item for item in runs if item["run_id"] == args.run_id), None)
    if not run:
        raise SystemExit(f"unknown run id: {args.run_id}")
    tasks, events = confirmed_subset(run, confirmed)
    run["proposed_tasks"] = tasks
    run["proposed_calendar_events"] = events
    applied_changes: list[dict[str, Any]] = []
    errors: list[str] = []

    for task in tasks:
        # Todoist is MCP-only in this workspace. Record a validated apply instruction
        # for Rumi to execute with Todoist MCP after explicit confirmation.
        applied_changes.append(
            {
                "type": "todoist_task_instruction",
                "content": task["content"],
                "task_home": task["task_home"],
                "todoist_project": task["todoist_project"],
                "status": "ready_for_mcp_apply",
            }
        )

    for event in events:
        if not event.get("starts_at") or not event.get("ends_at"):
            errors.append(f"calendar event missing start/end: {event['title']}")
            continue
        try:
            applied_changes.append(calendar_create(event) if not args.dry_run else {"type": "calendar_event", "title": event["title"], "dry_run": True})
        except Exception as exc:  # noqa: BLE001 - preserve per-item failure for retry.
            errors.append(f"{event['title']}: {exc}")

    run["applied_changes"].extend(applied_changes)
    run["errors"].extend(errors)
    run["status"] = "applied_with_errors" if errors else "applied"
    run["updated_at"] = iso_from(now)
    run["completed_at"] = iso_from(now)
    save_runs(runs, args.dry_run)

    projects = load_projects(now)
    for project in projects:
        if project["id"] != run["project_id"]:
            continue
        project["pending_confirmation"] = bool(errors)
        project["artifact_summary"] = run.get("summary", project.get("artifact_summary"))
        project["last_audit_at"] = today_from(now)
        project["updated_at"] = today_from(now)
        for change in applied_changes:
            if change.get("type") == "calendar_event" and change.get("external_id"):
                project["calendar_event_ids"].append(change["external_id"])
        break
    save_projects(projects, args.dry_run)

    print_json({"status": "OK", "run_id": run["run_id"], "applied_changes": applied_changes, "errors": errors, "dry_run": args.dry_run})
    return 0


def command_audit(args: argparse.Namespace, now: datetime) -> int:
    projects = load_projects(now)
    runs = load_runs(now)
    details = load_details(now)
    selected_project = None
    selected_runs = runs
    selected_details = details
    if args.id:
        selected_project = next((item for item in projects if item["id"] == args.id), None)
        selected_runs = [run for run in runs if run["project_id"] == args.id]
        selected_details = details_for_project(details, args.id, include_archived=True, limit=50)
    if args.run_id:
        selected_runs = [run for run in runs if run["run_id"] == args.run_id]
        if selected_runs:
            selected_project = next((item for item in projects if item["id"] == selected_runs[0]["project_id"]), selected_project)
            selected_details = details_for_project(details, selected_runs[0]["project_id"], include_archived=True, limit=50)
    print_json({"status": "OK", "project": selected_project, "project_details": selected_details, "runs": selected_runs[-10:]})
    return 0


def main() -> int:
    args = parse_args()
    now = now_et(args.now)
    if args.command == "upsert":
        return command_upsert(args, now)
    if args.command == "list":
        return command_list(args, now)
    if args.command == "review":
        return command_review(args, now)
    if args.command == "complete":
        return command_complete(args, now)
    if args.command == "detail-upsert":
        return command_detail_upsert(args, now)
    if args.command == "details-upsert":
        return command_details_upsert(args, now)
    if args.command == "detail-list":
        return command_detail_list(args, now)
    if args.command == "detail-archive":
        return command_detail_archive(args, now)
    if args.command == "plan":
        return command_plan(args, now)
    if args.command == "next-worker-run":
        return command_next_worker_run(args, now)
    if args.command == "complete-run":
        return command_complete_run(args, now)
    if args.command == "fail-run":
        return command_fail_run(args, now)
    if args.command == "propose":
        return command_propose(args, now)
    if args.command == "apply":
        return command_apply(args, now)
    if args.command == "audit":
        return command_audit(args, now)
    raise SystemExit(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
