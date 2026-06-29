#!/usr/bin/env python3
"""Mira cold memory helper backed by git-notes.

The helper stores structured memory notes in an ignored runtime git repository.
Tracked Mira files contain this helper and policy only; note data stays under
~/.openclaw/memory/git-notes unless MIRA_MEMORY_COLD_STORE_DIR overrides it.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


NOTE_REF = "refs/notes/mira-memory"
DEFAULT_STORE = Path.home() / ".openclaw" / "memory" / "git-notes"


class ColdStoreError(RuntimeError):
    """Raised when a cold-store operation cannot complete safely."""


def store_dir() -> Path:
    override = os.environ.get("MIRA_MEMORY_COLD_STORE_DIR")
    return Path(override).expanduser() if override else DEFAULT_STORE


def git_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("GIT_AUTHOR_NAME", "Mira")
    env.setdefault("GIT_AUTHOR_EMAIL", "mira-memory@local")
    env.setdefault("GIT_COMMITTER_NAME", "Mira")
    env.setdefault("GIT_COMMITTER_EMAIL", "mira-memory@local")
    return env


def run_git(args: list[str], *, input_text: str | None = None, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=store_dir(),
        input=input_text,
        text=True,
        capture_output=True,
        env=git_env(),
        check=False,
    )
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise ColdStoreError(detail or f"git {' '.join(args)} failed")
    return proc.stdout.strip()


def ensure_repo() -> Path:
    path = store_dir()
    path.mkdir(parents=True, exist_ok=True)
    if not (path / ".git").exists():
        subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True, text=True)
    return path


def canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def note_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)


def parse_note(raw: str, obj: str) -> dict[str, Any] | None:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict):
        return None
    value.setdefault("object", obj)
    return value


def iter_notes() -> list[dict[str, Any]]:
    ensure_repo()
    listing = run_git(["notes", "--ref", NOTE_REF, "list"], check=False)
    notes: list[dict[str, Any]] = []
    for line in listing.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        _, obj = parts
        raw = run_git(["notes", "--ref", NOTE_REF, "show", obj], check=False)
        parsed = parse_note(raw, obj)
        if parsed:
            notes.append(parsed)
    return sorted(notes, key=lambda item: str(item.get("createdAt", "")), reverse=True)


def remember(args: argparse.Namespace) -> int:
    ensure_repo()
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    entry = {
        "id": f"cold_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}",
        "type": args.type,
        "topic": args.topic,
        "importance": args.importance,
        "content": args.content.strip(),
        "createdAt": now,
        "source": "mira-memory-cold-store",
    }
    if not entry["content"]:
        raise ColdStoreError("content must not be empty")

    obj = run_git(["hash-object", "-w", "--stdin"], input_text=canonical_json(entry))
    entry["object"] = obj
    run_git(["notes", "--ref", NOTE_REF, "add", "-f", "-m", note_json(entry), obj])
    print(note_json(entry) if args.json else f"stored {entry['id']} ({obj})")
    return 0


def list_notes(args: argparse.Namespace) -> int:
    notes = iter_notes()
    if args.json:
        print(json.dumps(notes, ensure_ascii=False, indent=2))
        return 0
    if not notes:
        print("no cold memories")
        return 0
    for note in notes:
        print(f"{note.get('id')} [{note.get('type')}/{note.get('importance')}] {note.get('topic')}: {note.get('content')}")
    return 0


def search(args: argparse.Namespace) -> int:
    query = args.query.lower()
    matches = []
    for note in iter_notes():
        haystack = " ".join(
            str(note.get(key, "")) for key in ("id", "type", "topic", "importance", "content", "createdAt")
        ).lower()
        if query in haystack:
            matches.append(note)
    if args.json:
        print(json.dumps(matches, ensure_ascii=False, indent=2))
        return 0
    if not matches:
        print("no matching cold memories")
        return 1
    for note in matches:
        print(f"{note.get('id')} [{note.get('type')}/{note.get('importance')}] {note.get('topic')}: {note.get('content')}")
    return 0


def get(args: argparse.Namespace) -> int:
    needle = args.id_or_object
    for note in iter_notes():
        if needle in {str(note.get("id")), str(note.get("object"))}:
            print(note_json(note) if args.json else note.get("content", ""))
            return 0
    print(f"not found: {needle}", file=sys.stderr)
    return 1


def export(args: argparse.Namespace) -> int:
    notes = iter_notes()
    print(json.dumps(notes, ensure_ascii=False, indent=2))
    return 0


def doctor(args: argparse.Namespace) -> int:
    path = ensure_repo()
    count = len(iter_notes())
    print(json.dumps({"store": str(path), "noteRef": NOTE_REF, "count": count}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mira git-notes cold memory helper")
    sub = parser.add_subparsers(dest="command", required=True)

    remember_cmd = sub.add_parser("remember", help="Store a durable cold memory")
    remember_cmd.add_argument("content")
    remember_cmd.add_argument("--type", choices=["decision", "lesson", "fact", "handoff", "preference"], default="fact")
    remember_cmd.add_argument("--topic", default="general")
    remember_cmd.add_argument("--importance", choices=["low", "medium", "high"], default="medium")
    remember_cmd.add_argument("--json", action="store_true")
    remember_cmd.set_defaults(func=remember)

    list_cmd = sub.add_parser("list", help="List cold memories")
    list_cmd.add_argument("--json", action="store_true")
    list_cmd.set_defaults(func=list_notes)

    search_cmd = sub.add_parser("search", help="Search cold memories by substring")
    search_cmd.add_argument("query")
    search_cmd.add_argument("--json", action="store_true")
    search_cmd.set_defaults(func=search)

    get_cmd = sub.add_parser("get", help="Get a memory by id or git object id")
    get_cmd.add_argument("id_or_object")
    get_cmd.add_argument("--json", action="store_true")
    get_cmd.set_defaults(func=get)

    export_cmd = sub.add_parser("export", help="Export all cold memories as JSON")
    export_cmd.set_defaults(func=export)

    doctor_cmd = sub.add_parser("doctor", help="Show store path and count")
    doctor_cmd.set_defaults(func=doctor)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except (ColdStoreError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
