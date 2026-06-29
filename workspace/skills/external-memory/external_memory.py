#!/usr/bin/env python3
"""Explicit external memory helper for Mira.

Dry-run is the default. Live calls require --live plus MEM0_API_KEY. This helper
is intentionally narrow: send curated durable snippets only, never raw
transcripts, email bodies, logs, credentials, tokens, or browser/session state.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any


DEFAULT_USER = "mira"
SECRET_PATTERNS = [
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{20,}", re.IGNORECASE),
    re.compile(r"gh[pousr]_[0-9A-Za-z_]{20,}"),
    re.compile(r"sk-[0-9A-Za-z_-]{20,}"),
    re.compile(r"sk-or-v1-[0-9A-Za-z_-]{20,}"),
    re.compile(r"ya29\.[0-9A-Za-z_-]+"),
    re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
    re.compile(r"BEGIN (RSA|OPENSSH|PRIVATE) KEY"),
]
BLOCKED_HINTS = [
    "oauth",
    "token",
    "password",
    "authorization",
    "cookie",
    "set-cookie",
    "private key",
    "session transcript",
    "raw email",
    "browser state",
]


class ExternalMemoryError(RuntimeError):
    """Raised when an external memory action is unsafe or failed."""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def reject_unsafe(text: str) -> None:
    lowered = text.lower()
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            raise ExternalMemoryError("content looks like it contains a secret or token")
    for hint in BLOCKED_HINTS:
        if hint in lowered:
            raise ExternalMemoryError(f"content contains blocked privacy hint: {hint}")


def metadata(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "source": "mira-external-memory-helper",
        "category": args.category,
        "createdAt": now_iso(),
    }


def print_payload(args: argparse.Namespace, payload: dict[str, Any]) -> int:
    print(json.dumps({"dryRun": not args.live, "provider": "mem0", "payload": payload}, indent=2))
    return 0


def mem0_client() -> Any:
    try:
        from mem0 import MemoryClient  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on optional package
        raise ExternalMemoryError("mem0ai package is not installed in this runtime") from exc
    api_key = os.environ.get("MEM0_API_KEY")
    if not api_key:
        raise ExternalMemoryError("MEM0_API_KEY is not set")
    return MemoryClient(api_key=api_key)


def mem0_add(args: argparse.Namespace) -> int:
    reject_unsafe(args.content)
    messages = [{"role": "user", "content": args.content}]
    payload = {
        "messages": messages,
        "user_id": args.user,
        "metadata": metadata(args),
        "infer": True,
    }
    if not args.live:
        return print_payload(args, payload)
    result = mem0_client().add(
        messages=messages,
        user_id=args.user,
        metadata=metadata(args),
        infer=True,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0


def mem0_search(args: argparse.Namespace) -> int:
    reject_unsafe(args.query)
    payload = {
        "query": args.query,
        "filters": {"user_id": args.user},
        "top_k": args.limit,
    }
    if not args.live:
        return print_payload(args, payload)
    result = mem0_client().search(
        args.query,
        filters={"user_id": args.user},
        top_k=args.limit,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mira external memory helper")
    parser.add_argument("--live", action="store_true", help="Perform the external API call")
    sub = parser.add_subparsers(dest="command", required=True)

    add_cmd = sub.add_parser("add", help="Add a curated memory snippet")
    add_cmd.add_argument("content")
    add_cmd.add_argument("--category", default="general")
    add_cmd.add_argument("--user", default=DEFAULT_USER)
    add_cmd.set_defaults(func=mem0_add)

    search_cmd = sub.add_parser("search", help="Search external memory")
    search_cmd.add_argument("query")
    search_cmd.add_argument("--user", default=DEFAULT_USER)
    search_cmd.add_argument("--limit", type=int, default=5)
    search_cmd.set_defaults(func=mem0_search)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except ExternalMemoryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
