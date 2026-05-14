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
    "workspace/AGENTS.md": "Standing execution rules and schemas referenced by cron prompts.",
    "workspace/USER.md": "Shared non-tool, non-rule preferences and context. Cron jobs that draft, summarize, or proactively message using personal context should honor relevant preferences here.",
    "workspace/TOOLS.md": "Tool account, calendar, Gmail, Todoist, Telegram, OpenClaw cron creation, and skill conventions.",
    "workspace/cron/memory_consolidation.py": "Helper used by Memory Consolidation to perform deterministic JSONL hygiene and sidecar compaction.",
    "workspace/cron/proactive_engagement.py": "Helper used by Proactive Engagement to enforce eligibility, select a topic/style, and append engagement state.",
    "workspace/cron/engagement_followups.py": "Helper used by Engagement Follow-Ups to validate queued instructions, process due follow-ups, run supported live checks, and append engagement state.",
    "workspace/cron/email_triage_preflight.py": "Helper used by email triage crons to search Gmail and prepare compact message records.",
    "workspace/cron/morning_brief_collect.py": "Helper used by Morning Brief to collect calendar and memory facts before model-written prose.",
    "workspace/cron/nightly_session_reflection.py": "Helper used by Nightly Session Reflection to collect interactive transcript context, validate memory writes, audit results, and gate reset behavior.",
    "workspace/memory/medium_memory.jsonl": "Read by Morning Brief, Memory Consolidation, Nightly Session Reflection, Proactive Engagement, and the memory plugin; written by Nightly Session Reflection and the memory plugin.",
    "workspace/memory/long_memory.jsonl": "Read by Memory Consolidation, Nightly Session Reflection, and the memory plugin; written by Nightly Session Reflection when Kenny reveals durable facts.",
    "workspace/memory/engagement_memory.jsonl": "Read and appended by Proactive Engagement and Engagement Follow-Ups.",
    "workspace/memory/engagement_priorities.jsonl": "Read and rewritten by Proactive Engagement, Memory Consolidation, Nightly Session Reflection, and the memory plugin.",
    "workspace/memory/engagement_followups.jsonl": "Short-lived queue written by interactive Rumi through the engagement follow-up helper and processed by Engagement Follow-Ups.",
    "workspace/memory/email_triage_state.jsonl": "Written by email crons and compacted by Memory Consolidation.",
    "workspace/memory/nightly_session_reflection_state.jsonl": "Audit sidecar written by Nightly Session Reflection with counts and reset status, not transcript contents.",
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
rows.append("## QMD Recall Backend")
rows.append("")
rows.append("QMD is configured in `templates/openclaw.friend-safe.example.json` as a")
rows.append("read-only memory search backend over selected markdown sources:")
rows.append("")
rows.append("- root workspace docs (`workspace/*.md`)")
rows.append("- cron prompts (`workspace/cron/*.md`)")
rows.append("- workspace skills (`workspace/skills/**/*.md`)")
rows.append("")
rows.append("QMD does not replace the curated JSONL files above. Historical JSONL memory is")
rows.append("not backfilled into QMD, and session transcript indexing is disabled by default.")
rows.append("Do not add QMD indexes, session exports, or `~/.openclaw/agents/*/qmd/` runtime")
rows.append("state to this dependency map or to the backup allowlist.")
rows.append("")
rows.append("## Sync Rule")
rows.append("")
rows.append("Run `scripts/sync-from-live.sh` after changing Rumi behavior. It copies the allowlisted behavior files and reseeds memory/state files without copying accumulated private history.")
rows.append("")
(root / "docs" / "cron-dependencies.md").write_text("\n".join(rows))
PY
