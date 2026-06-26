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
    version = config.get("version", 1) if isinstance(config, dict) else 1
    return {"version": version, "jobs": []}


def read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return None


jobs_config = read_json(live_home / "cron" / "jobs.json")
if jobs_config is not None:
    write_json(root / "templates" / "cron-jobs.friend-safe.example.json", cron_restore_template(jobs_config))

cron_dir = workspace / "cron"
cron_files = sorted(cron_dir.glob("*.md")) if cron_dir.exists() else []
known_dependencies = {
    "workspace/AGENTS.md": "Standing coding workflow, privacy, Gmail, Telegram, and cron policy.",
    "workspace/USER.md": "Kenny's coding collaboration preferences.",
    "workspace/TOOLS.md": "Coding tool, on-demand Gmail, Telegram, and cron conventions.",
}

rows = ["# Cron Dependencies", "", "This file documents behavior-bearing files that cron jobs or cron context injection depend on.", ""]
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
rows.append("QMD is not configured by default in the coding-only Mira template.")
rows.append("")
rows.append("Do not add QMD indexes, session exports, or `~/.openclaw/agents/*/qmd/` runtime state to this dependency map or to the backup allowlist.")
rows.append("")
rows.append("## Sync Rule")
rows.append("")
rows.append("Run `scripts/sync-from-live.sh` after changing Mira behavior. It copies the manifest-listed behavior files without copying accumulated private history.")
rows.append("")
(root / "docs" / "cron-dependencies.md").write_text("\n".join(rows))
PY
