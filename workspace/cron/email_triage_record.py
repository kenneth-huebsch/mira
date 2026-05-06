#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = WORKSPACE_ROOT / "memory/email_triage_state.jsonl"
REQUIRED_FIELDS = {
    "run_at",
    "class",
    "source",
    "from",
    "from_email",
    "subject",
    "message_id",
    "thread_id",
    "rfc_message_id",
    "gist",
    "drafted",
    "draft_id",
    "sent",
    "sent_at",
    "note",
}
ALLOWED_CLASSES = {"actionable_reply", "info_only", "forwarded_info"}
ALLOWED_SOURCES = {"rumi.openclaw@gmail.com", "kenny@dripr.ai", "kenny@0trust.email"}


def fail(message: str) -> int:
    print(f"email triage sidecar append failed: {message}", file=sys.stderr)
    return 1


def validate_record(record: dict[str, Any]) -> str | None:
    missing = sorted(REQUIRED_FIELDS - set(record))
    if missing:
        return f"missing fields: {', '.join(missing)}"
    if record.get("class") not in ALLOWED_CLASSES:
        return "invalid class"
    if record.get("source") not in ALLOWED_SOURCES:
        return "invalid source"
    if not isinstance(record.get("drafted"), bool):
        return "drafted must be boolean"
    if not isinstance(record.get("sent"), bool):
        return "sent must be boolean"
    return None


def append_jsonl(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = line.encode("utf-8") + b"\n"
    with path.open("ab+") as handle:
        handle.seek(0, 2)
        if handle.tell() > 0:
            handle.seek(-1, 2)
            if handle.read(1) != b"\n":
                handle.write(b"\n")
        handle.write(encoded)


def main() -> int:
    raw = sys.stdin.read().strip()
    if not raw:
        return fail("missing JSON record on stdin")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        return fail(f"invalid JSON: {exc}")
    if not isinstance(parsed, dict):
        return fail("record must be a JSON object")
    problem = validate_record(parsed)
    if problem:
        return fail(problem)
    line = json.dumps(parsed, separators=(",", ":"), ensure_ascii=False)
    try:
        append_jsonl(STATE_PATH, line)
    except OSError as exc:
        return fail(str(exc))
    print("RECORDED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
