#!/usr/bin/env bash
set -euo pipefail

BLUEPRINT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIVE_OPENCLAW_HOME="${LIVE_OPENCLAW_HOME:-$BLUEPRINT_ROOT/.openclaw}"

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
        schedule = job.get("schedule") if isinstance(job.get("schedule"), dict) else {}
        if job.get("deleteAfterRun") is True and schedule.get("kind") == "at":
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
    "workspace/AGENTS.md": "Standing execution rules and workflow policy.",
    "workspace/USER.md": "Shared non-tool, non-rule preferences and context.",
    "workspace/TOOLS.md": "Tool account, calendar, Gmail, Todoist, Telegram, OpenClaw cron creation, and skill conventions.",
    "workspace/memory/medium_memory.jsonl": "Read and written by the memory plugin for time-bounded interactive context.",
    "workspace/memory/long_memory.jsonl": "Read by the memory plugin for durable context.",
    "workspace/memory/rolling_summary.json": "Optional dynamic context available to the memory plugin.",
    "workspace/skills/memory_manager.md": "Used by the memory plugin after interactive turns.",
}

rows = ["# Cron Dependencies", "", "Mira has no recurring cron prompts by default. This file tracks dependencies for future scheduled behavior if Kenny adds any.", ""]
rows.append("## Cron Prompts")
rows.append("")
if cron_files:
    for path in cron_files:
        rows.append(f"- `{path.relative_to(root)}`")
else:
    rows.append("- None configured.")
rows.append("")
rows.append("## Required Supporting Files")
rows.append("")
for dep, reason in known_dependencies.items():
    exists = "present" if (root / dep).exists() else "missing"
    rows.append(f"- `{dep}` ({exists}) - {reason}")
rows.append("")
rows.append("## QMD Recall Backend")
rows.append("")
rows.append("QMD is configured in `templates/openclaw.friend-safe.example.json` as a")
rows.append("read-only memory search backend over selected markdown sources:")
rows.append("")
rows.append("- root workspace docs (`workspace/*.md`)")
rows.append("- workspace skills (`workspace/skills/**/*.md`)")
rows.append("")
rows.append("QMD does not replace the curated JSONL files above. Historical JSONL memory is")
rows.append("not backfilled into QMD, and session transcript indexing is disabled by default.")
rows.append("Do not add QMD indexes, session exports, or `~/.openclaw/agents/*/qmd/` runtime")
rows.append("state to this dependency map or to the backup allowlist.")
rows.append("")
rows.append("## Sync Rule")
rows.append("")
rows.append("Run `scripts/sync-from-live.sh` after changing Mira behavior. It copies the allowlisted behavior files and reseeds memory files without copying accumulated private history.")
rows.append("")
(root / "docs" / "cron-dependencies.md").write_text("\n".join(rows))
PY
