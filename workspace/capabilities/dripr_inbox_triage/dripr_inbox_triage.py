#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from html import unescape
from typing import Any

DEFAULT_ACCOUNT = "mira.agentops@gmail.com"
SOURCE_ADDRESSES = {"info@dripr.ai", "kenny@dripr.ai"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch compact dripr inbox records for Mira.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    review = subparsers.add_parser("review", help="Search unread dripr mail and print compact JSON.")
    review.add_argument("--max", type=int, default=100)
    process = subparsers.add_parser("process", help="Review, summarize, and mark matching dripr mail read.")
    process.add_argument("--max", type=int, default=100)
    mark_read = subparsers.add_parser("mark-read", help="Remove UNREAD from a reviewed Gmail message.")
    mark_read.add_argument("message_id")
    return parser.parse_args()


def account() -> str:
    return os.environ.get("MIRA_GMAIL_ACCOUNT") or os.environ.get("GOG_ACCOUNT") or DEFAULT_ACCOUNT


def gog_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("XDG_CONFIG_HOME", "/home/node/.openclaw")
    env.setdefault("GOG_KEYRING_BACKEND", "file")
    env.setdefault("GOG_KEYRING_PASSWORD", "")
    return env


def run_json(args: list[str]) -> dict[str, Any]:
    proc = subprocess.run(args, text=True, capture_output=True, env=gog_env())
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip() or "command failed")
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON from {' '.join(args[:3])}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("expected JSON object")
    return parsed


def run_command(args: list[str]) -> str:
    proc = subprocess.run(args, text=True, capture_output=True, env=gog_env())
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip() or "command failed")
    return proc.stdout.strip()


def gog_args(*args: str) -> list[str]:
    return ["gog", *args]


def list_items(data: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def email_from(value: str) -> str | None:
    match = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", value or "")
    return match.group(0).lower() if match else None


def header_map(message: dict[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = {}
    top = message.get("headers")
    if isinstance(top, dict):
        for key, value in top.items():
            headers[str(key).lower()] = str(value)

    payload = message.get("message", {}).get("payload", {}) if isinstance(message.get("message"), dict) else {}
    raw_headers = payload.get("headers") if isinstance(payload, dict) else None
    if isinstance(raw_headers, list):
        for item in raw_headers:
            if isinstance(item, dict) and item.get("name"):
                headers[str(item["name"]).lower()] = str(item.get("value") or "")
    return headers


def clean_body(value: Any, max_chars: int = 1200) -> str:
    text = str(value or "")
    text = unescape(text)
    text = text.replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "..."


def resolve_source(headers: dict[str, str]) -> str | None:
    for key in ["x-pm-forwarded-from", "x-original-to", "to"]:
        found = email_from(headers.get(key, ""))
        if found in SOURCE_ADDRESSES:
            return found
    return None


def bulk_hints(headers: dict[str, str]) -> list[str]:
    hints: list[str] = []
    if headers.get("list-unsubscribe"):
        hints.append("list_unsubscribe")
    if headers.get("precedence", "").lower() in {"bulk", "list", "junk"}:
        hints.append(f"precedence:{headers['precedence'].lower()}")
    sender = headers.get("from", "").lower()
    if any(token in sender for token in ["no-reply", "noreply", "newsletter", "notification"]):
        hints.append("automated_sender")
    return hints


def fetch_full(message_id: str, acct: str) -> dict[str, Any]:
    return run_json(gog_args("gmail", "get", message_id, "--account", acct, "--json"))


def compact_message(stub: dict[str, Any], acct: str) -> dict[str, Any] | None:
    message_id = str(stub.get("id") or stub.get("messageId") or "").strip()
    if not message_id:
        raise RuntimeError("message stub missing id")

    full = fetch_full(message_id, acct)
    headers = header_map(full)
    source = resolve_source(headers)
    if source not in SOURCE_ADDRESSES:
        return None

    message_obj = full.get("message") if isinstance(full.get("message"), dict) else {}
    thread_id = str(message_obj.get("threadId") or full.get("threadId") or stub.get("threadId") or "")
    body = full.get("body") or message_obj.get("snippet") or full.get("snippet")

    return {
        "message_id": message_id,
        "thread_id": thread_id,
        "rfc_message_id": headers.get("message-id"),
        "source": source,
        "source_kind": "form_inbox" if source == "info@dripr.ai" else "business_email",
        "from": headers.get("from", ""),
        "from_email": email_from(headers.get("from", "")),
        "to": headers.get("to", ""),
        "subject": headers.get("subject", ""),
        "date": headers.get("date", ""),
        "body_excerpt": clean_body(body),
        "python_hints": bulk_hints(headers),
        "labels": message_obj.get("labelIds") if isinstance(message_obj.get("labelIds"), list) else [],
    }


def collect_messages(max_results: int) -> list[dict[str, Any]]:
    acct = account()
    query = f"in:inbox is:unread deliveredto:{acct}"
    search = run_json(
        [
            *gog_args(
                "gmail",
                "messages",
                "search",
                query,
                "--max",
                str(max_results),
                "--account",
                acct,
                "--json",
            ),
        ]
    )
    stubs = list_items(search, "messages", "items")
    if not stubs:
        return []

    messages: list[dict[str, Any]] = []
    for stub in stubs:
        compact = compact_message(stub, acct)
        if compact is not None:
            messages.append(compact)
    return messages


def review(max_results: int) -> int:
    acct = account()
    messages = collect_messages(max_results)

    if not messages:
        print("NO_REPLY")
        return 0

    payload = {
        "status": "OK",
        "account": acct,
        "source_addresses": sorted(SOURCE_ADDRESSES),
        "message_count": len(messages),
        "messages": messages,
        "model_contract": {
            "classify": "Use judgment for attention vs noise; Python hints are not final labels.",
            "mutations": "Only remove UNREAD after reviewing matching messages.",
        },
    }
    print(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    return 0


def strip_htmlish(text: str) -> str:
    cleaned = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = unescape(cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    return cleaned.strip()


def form_summary(message: dict[str, Any]) -> str:
    body = strip_htmlish(str(message.get("body_excerpt") or ""))
    fields: dict[str, str] = {}
    for line in body.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        normalized = key.strip().lower()
        if normalized in {"name", "name 2", "email", "availability", "address", "message"}:
            fields[normalized] = value.strip()
    name = fields.get("name") or fields.get("name 2")
    email = fields.get("email")
    availability = fields.get("availability") or fields.get("message")
    pieces = []
    if name:
        pieces.append(name)
    if email:
        pieces.append(email)
    if availability:
        pieces.append(availability)
    if not pieces:
        pieces.append(str(message.get("subject") or "new form submission"))
    return "; ".join(pieces)


def business_summary(message: dict[str, Any]) -> str:
    sender = str(message.get("from") or message.get("from_email") or "Unknown sender")
    subject = str(message.get("subject") or "(no subject)")
    body = strip_htmlish(str(message.get("body_excerpt") or ""))
    first_line = next((line.strip() for line in body.splitlines() if line.strip()), "")
    if first_line:
        return f"{sender} on {subject}: {first_line}"
    return f"{sender} on {subject}"


def is_attention(message: dict[str, Any]) -> bool:
    if message.get("source_kind") == "form_inbox":
        return True
    hints = set(message.get("python_hints") or [])
    if "list_unsubscribe" in hints:
        return False
    sender = str(message.get("from_email") or "").lower()
    if sender.startswith("no-reply") or sender.startswith("noreply"):
        return False
    return message.get("source_kind") == "business_email"


def process(max_results: int) -> int:
    messages = collect_messages(max_results)
    if not messages:
        print("NO_REPLY")
        return 0

    attention = [message for message in messages if is_attention(message)]
    mark_failures: list[str] = []
    for message in messages:
        try:
            mark_read(str(message.get("message_id") or ""), emit=False)
        except RuntimeError:
            mark_failures.append(str(message.get("message_id") or "unknown"))

    if not attention:
        if mark_failures:
            print("Mira dripr inbox triage failed: could not mark reviewed mail read.")
        else:
            print("NO_REPLY")
        return 0

    lines = ["Dripr inbox:"]
    for message in attention:
        if message.get("source_kind") == "form_inbox":
            lines.append(f"- Form submission: {form_summary(message)}")
        else:
            lines.append(f"- Business email: {business_summary(message)}")
    if mark_failures:
        lines.append("I could not mark one or more reviewed messages read.")
    print("\n".join(lines))
    return 0


def mark_read(message_id: str, *, emit: bool = True) -> int:
    clean_id = message_id.strip()
    if not clean_id:
        raise RuntimeError("missing message id")
    run_command(
        gog_args(
            "gmail",
            "messages",
            "modify",
            clean_id,
            "--remove",
            "UNREAD",
            "--account",
            account(),
        )
    )
    if emit:
        print("MARKED_READ")
    return 0


def main() -> int:
    args = parse_args()
    try:
        if args.command == "review":
            return review(args.max)
        if args.command == "process":
            return process(args.max)
        if args.command == "mark-read":
            return mark_read(args.message_id)
    except RuntimeError as exc:
        print(f"dripr inbox preflight failed: {exc}", file=sys.stderr)
        return 1
    raise RuntimeError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
