#!/usr/bin/env python3
"""Check Mira's supported local-first memory stack."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


WORKSPACE = Path.cwd()
OPENCLAW_HOME = Path.home() / ".openclaw"
CONFIG_PATH = OPENCLAW_HOME / "openclaw.json"
REQUIRED_MEMORY_FILES = [
    "SESSION-STATE.md",
    "MEMORY.md",
    "DREAMS.md",
]
REQUIRED_TOOLS = {"memory_recall", "memory_store", "memory_forget"}


def load_config() -> dict[str, Any]:
    try:
        return json.loads(CONFIG_PATH.read_text())
    except FileNotFoundError as exc:
        raise RuntimeError(f"missing OpenClaw config: {CONFIG_PATH}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid OpenClaw config: {exc}") from exc


def nested(config: dict[str, Any], *keys: str) -> Any:
    value: Any = config
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def check_memory_files(errors: list[str]) -> None:
    for rel in REQUIRED_MEMORY_FILES:
        if not (WORKSPACE / rel).is_file():
            errors.append(f"missing memory file: {rel}")
    memory_dir = WORKSPACE / "memory"
    if not memory_dir.is_dir():
        errors.append("missing memory directory: memory/")
    elif not list(memory_dir.glob("*.md")):
        errors.append("memory/ has no daily markdown files")


def check_config(config: dict[str, Any], errors: list[str]) -> None:
    memory_search = nested(config, "agents", "defaults", "memorySearch")
    if not isinstance(memory_search, dict) or memory_search.get("enabled") is not True:
        errors.append("agents.defaults.memorySearch is not enabled")
    if nested(memory_search or {}, "remote", "apiKey") != "${OPENROUTER_API_KEY}":
        errors.append("memorySearch is not configured to use OPENROUTER_API_KEY")

    entries = nested(config, "plugins", "entries")
    if not isinstance(entries, dict):
        errors.append("plugins.entries is missing")
        entries = {}

    active_memory = entries.get("active-memory")
    if not isinstance(active_memory, dict) or active_memory.get("enabled") is not True:
        errors.append("active-memory plugin is not enabled")
    elif nested(active_memory, "config", "persistTranscripts") is not False:
        errors.append("active-memory should not persist transcripts")

    lancedb = entries.get("memory-lancedb")
    if not isinstance(lancedb, dict) or lancedb.get("enabled") is not True:
        errors.append("memory-lancedb plugin is not enabled")
    if nested(config, "plugins", "slots", "memory") != "memory-lancedb":
        errors.append("plugins.slots.memory is not memory-lancedb")

    tools = set(nested(config, "tools", "allow") or [])
    missing_tools = sorted(REQUIRED_TOOLS - tools)
    if missing_tools:
        errors.append(f"missing memory tools: {', '.join(missing_tools)}")

    skills = nested(config, "skills", "entries")
    if not isinstance(skills, dict):
        errors.append("skills.entries is missing")
        return
    if nested(skills, "mira-memory", "enabled") is not True:
        errors.append("mira-memory skill is not enabled")
    if nested(skills, "memory-cold-store", "enabled") is not True:
        errors.append("memory-cold-store skill is not enabled")


def check_cold_store(errors: list[str]) -> None:
    helper = WORKSPACE / "skills" / "memory-cold-store" / "memory_cold_store.py"
    if not helper.is_file():
        errors.append("missing cold-store helper")
        return
    proc = subprocess.run(
        [sys.executable, str(helper), "doctor"],
        cwd=WORKSPACE,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        errors.append(f"cold-store doctor failed: {detail}")
        return
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError:
        errors.append("cold-store doctor returned non-json output")
        return
    if result.get("noteRef") != "refs/notes/mira-memory":
        errors.append("cold-store note ref is not refs/notes/mira-memory")


def main() -> int:
    errors: list[str] = []
    check_memory_files(errors)
    config = load_config()
    check_config(config, errors)
    check_cold_store(errors)

    if errors:
        print(json.dumps({"ok": False, "errors": errors}, indent=2))
        return 1
    print(json.dumps({"ok": True, "checked": "mira-memory"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
