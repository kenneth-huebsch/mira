#!/usr/bin/env bash
set -euo pipefail

BLUEPRINT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIVE_OPENCLAW_HOME="${LIVE_OPENCLAW_HOME:-$HOME/.openclaw}"

python3 - "$BLUEPRINT_ROOT" "$LIVE_OPENCLAW_HOME" <<'PY'
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
live_home = Path(sys.argv[2])
workspace = root / "workspace"

SECRET_KEY_RE = re.compile(
    r"(authorization|token|secret|password|passwd|credential|credentials|api[_-]?key|private[_-]?key|refresh[_-]?token|access[_-]?token)",
    re.I,
)
SECRET_VALUE_RE = re.compile(
    r"^(Bearer\s+)?([A-Za-z0-9_-]{32,}|sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9_]{20,}|ya29\.[A-Za-z0-9_-]+)$",
    re.I,
)


def redact(value):
    if isinstance(value, dict):
        out = {}
        for key, child in value.items():
            if SECRET_KEY_RE.search(str(key)):
                out[key] = "<set manually>"
            else:
                out[key] = redact(child)
        return out
    if isinstance(value, list):
        return [redact(child) for child in value]
    if isinstance(value, str) and SECRET_VALUE_RE.search(value.strip()):
        return "<set manually>"
    return value


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def cron_restore_template(config):
    if not isinstance(config, dict):
        return config
    jobs = []
    for job in config.get("jobs", []):
        if not isinstance(job, dict):
            continue
        cleaned = {
            key: redact(value)
            for key, value in job.items()
            if key not in {"createdAtMs", "updatedAtMs", "state"}
        }
        jobs.append(cleaned)
    return {"version": config.get("version", 1), "jobs": jobs}


def read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return None


openclaw_config = read_json(live_home / "openclaw.json")
if openclaw_config is not None:
    write_json(root / "templates" / "openclaw.friend-safe.example.json", redact(openclaw_config))

jobs_config = read_json(live_home / "cron" / "jobs.json")
if jobs_config is not None:
    write_json(root / "templates" / "cron-jobs.friend-safe.example.json", cron_restore_template(jobs_config))

cron_files = sorted((workspace / "cron").glob("*.md"))
known_dependencies = {
    "workspace/AGENTS.md": "Standing execution rules and schemas referenced by cron prompts.",
    "workspace/TOOLS.md": "Tool account, calendar, Gmail, Todoist, Telegram, and skill conventions.",
    "workspace/memory/medium_memory.jsonl": "Read by Morning Brief, Memory Consolidation, Proactive Engagement, and the memory plugin.",
    "workspace/memory/long_memory.jsonl": "Read and rewritten by Memory Consolidation and loaded by the memory plugin.",
    "workspace/memory/engagement_memory.jsonl": "Read and appended by Proactive Engagement.",
    "workspace/memory/engagement_priorities.jsonl": "Read and rewritten by Proactive Engagement, Memory Consolidation, and the memory plugin.",
    "workspace/memory/email_triage_state.jsonl": "Written by email crons and compacted by Memory Consolidation.",
    "workspace/memory/rolling_summary.json": "Optional dynamic context loaded by the memory plugin when cron frontmatter asks for rolling_summary.",
    "workspace/memory/ACTIVE_PRIORITIES.md": "Optional dynamic context loaded by the memory plugin when cron frontmatter asks for active_priorities.",
    "workspace/skills/memory_manager.md": "Used by the memory plugin after interactive turns.",
    "workspace/skills/engagement_priorities_manager.md": "Used by the memory plugin after interactive turns.",
}

rows = ["# Cron Dependencies", "", "This file documents behavior-bearing files that cron jobs or cron context injection depend on.", ""]
rows.append("## Cron Prompts")
rows.append("")
for path in cron_files:
    rows.append(f"- `{path.relative_to(root)}`")
rows.append("")
rows.append("## Required Supporting Files")
rows.append("")
for dep, reason in known_dependencies.items():
    exists = "present" if (root / dep).exists() else "missing"
    rows.append(f"- `{dep}` ({exists}) - {reason}")
rows.append("")
rows.append("## Sync Rule")
rows.append("")
rows.append("Run `scripts/sync-from-live.sh` after changing Rumi behavior. It copies the allowlisted behavior files and reseeds memory/state files without copying accumulated private history.")
rows.append("")
(root / "docs" / "cron-dependencies.md").write_text("\n".join(rows))
PY
