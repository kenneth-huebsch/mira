#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from html import unescape
from typing import Any

ACCOUNT = "rumi.openclaw@gmail.com"
FORWARDED_SOURCES = {"kenny@dripr.ai", "kenny@0trust.email"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch compact Gmail records for email triage crons.")
    parser.add_argument("mode", choices=["rumis", "kennys"])
    parser.add_argument("--max", type=int, default=None)
    return parser.parse_args()


def run_json(args: list[str]) -> dict[str, Any]:
    proc = subprocess.run(args, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip() or "command failed")
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON from {' '.join(args[:3])}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("expected JSON object")
    return parsed


def list_items(data: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


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


def clean_body(value: Any, max_chars: int = 900) -> str:
    text = str(value or "")
    text = unescape(text)
    text = text.replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "..."


def email_from(value: str) -> str | None:
    match = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", value or "")
    return match.group(0).lower() if match else None


def resolve_source(headers: dict[str, str]) -> str | None:
    for key in ["x-pm-forwarded-from", "x-original-to", "delivered-to", "to"]:
        found = email_from(headers.get(key, ""))
        if found in FORWARDED_SOURCES:
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


def fetch_full(message_id: str) -> dict[str, Any]:
    return run_json(["gog", "gmail", "get", message_id, "--account", ACCOUNT, "--json"])


def compact_message(stub: dict[str, Any], mode: str) -> dict[str, Any]:
    message_id = str(stub.get("id") or stub.get("messageId") or "").strip()
    if not message_id:
        raise RuntimeError("message stub missing id")
    full = fetch_full(message_id)
    headers = header_map(full)
    source = resolve_source(headers)
    message_obj = full.get("message") if isinstance(full.get("message"), dict) else {}
    thread_id = str(message_obj.get("threadId") or full.get("threadId") or stub.get("threadId") or "")
    rfc_message_id = headers.get("message-id") or headers.get("message-id".lower())
    compact = {
        "message_id": message_id,
        "thread_id": thread_id,
        "rfc_message_id": rfc_message_id,
        "source": source or ("rumi.openclaw@gmail.com" if mode == "rumis" else None),
        "from": headers.get("from", ""),
        "from_email": email_from(headers.get("from", "")),
        "to": headers.get("to", ""),
        "subject": headers.get("subject", ""),
        "date": headers.get("date", ""),
        "body_excerpt": clean_body(full.get("body") or message_obj.get("snippet") or full.get("snippet")),
        "python_hints": bulk_hints(headers),
        "labels": message_obj.get("labelIds") if isinstance(message_obj.get("labelIds"), list) else [],
    }
    if mode == "rumis" and source in FORWARDED_SOURCES:
        compact["mechanical_route"] = "skip_forwarded_for_kennys_cron"
    elif mode == "kennys" and source not in FORWARDED_SOURCES:
        compact["mechanical_route"] = "source_unresolved_needs_model_caution"
    else:
        compact["mechanical_route"] = "needs_model_review"
    return compact


def main() -> int:
    args = parse_args()
    if args.mode == "rumis":
        query = "in:inbox is:unread deliveredto:rumi.openclaw@gmail.com"
        max_results = args.max or 50
    else:
        query = "in:inbox is:unread deliveredto:rumi.openclaw@gmail.com (to:kenny@dripr.ai OR to:kenny@0trust.email)"
        max_results = args.max or 100

    search = run_json(
        [
            "gog",
            "gmail",
            "messages",
            "search",
            query,
            "--max",
            str(max_results),
            "--account",
            ACCOUNT,
            "--json",
        ]
    )
    stubs = list_items(search, "messages", "items")
    if not stubs:
        print("NO_REPLY")
        return 0

    messages = [compact_message(stub, args.mode) for stub in stubs]
    if args.mode == "rumis" and all(msg.get("mechanical_route") == "skip_forwarded_for_kennys_cron" for msg in messages):
        print("NO_REPLY")
        return 0

    payload = {
        "status": "OK",
        "mode": args.mode,
        "message_count": len(messages),
        "messages": messages,
        "model_contract": {
            "classify": "Use judgment for importance and reply needs; Python hints are not final labels.",
            "mutations": "Only mutate Gmail or sidecar according to the cron prompt after model review.",
        },
    }
    print(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
