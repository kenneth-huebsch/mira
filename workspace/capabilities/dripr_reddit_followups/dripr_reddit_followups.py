#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

WORKSPACE_ROOT = Path(os.environ.get("OPENCLAW_WORKSPACE_DIR", "/home/node/.openclaw/workspace"))
OPENCLAW_ROOT = WORKSPACE_ROOT.parent
DEFAULT_ENV_FILE = OPENCLAW_ROOT / "secrets" / "dripr-reddit-airtable.env"
DEFAULT_BASE_ID = "appmU4swFIn5T7d3U"
AIRTABLE_SCRIPT = WORKSPACE_ROOT / "skills" / "native-airtable" / "scripts" / "airtable.py"
REQUIRED_FIELDS = ("followed_up", "why_relevant", "url")
DEFAULT_MAX_ROWS = 3
MAX_FIELD_CHARS = 500
MAX_ERROR_CHARS = 220


class SetupError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check Dripr Reddit follow-ups in Airtable.")
    parser.add_argument("--env-file", default=os.environ.get("DRIPR_REDDIT_AIRTABLE_ENV", str(DEFAULT_ENV_FILE)))
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("review", help="Return compact follow-up rows or NO_REPLY.")
    subparsers.add_parser("check-config", help="Validate configuration without querying records.")
    return parser.parse_args()


def parse_env_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    key, value = stripped.split("=", 1)
    key = key.strip()
    value = value.strip()
    if not key:
        return None
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        value = value[1:-1]
    return key, value


def load_env(path: Path) -> dict[str, str]:
    if not path.exists():
        raise SetupError(f"missing env file: {path}")
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        parsed = parse_env_line(line)
        if parsed:
            key, value = parsed
            values[key] = value
    return values


def env_value(values: dict[str, str], key: str, default: str | None = None) -> str | None:
    return os.environ.get(key) or values.get(key) or default


def required_env(values: dict[str, str], key: str) -> str:
    value = env_value(values, key)
    if not value:
        raise SetupError(f"missing {key}")
    return value


def compact(value: Any, max_chars: int = MAX_FIELD_CHARS) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value).strip())
    if not text:
        return None
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "..."


def compact_error(error: BaseException) -> str:
    return str(error).replace("\n", " ")[:MAX_ERROR_CHARS]


def airtable_env(values: dict[str, str]) -> dict[str, str]:
    env = os.environ.copy()
    env["AIRTABLE_PAT"] = required_env(values, "AIRTABLE_PAT")
    return env


def run_airtable(values: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    if not AIRTABLE_SCRIPT.exists():
        raise SetupError("native-airtable skill is not installed in workspace/skills/native-airtable")
    return subprocess.run(
        ["python3", str(AIRTABLE_SCRIPT), *args],
        capture_output=True,
        text=True,
        env=airtable_env(values),
        check=False,
    )


def load_airtable_module():
    spec = importlib.util.spec_from_file_location("native_airtable_skill", AIRTABLE_SCRIPT)
    if spec is None or spec.loader is None:
        raise SetupError("could not load native-airtable skill module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tables_from_metadata(values: dict[str, str], base_id: str) -> list[dict[str, str]]:
    previous_pat = os.environ.get("AIRTABLE_PAT")
    os.environ["AIRTABLE_PAT"] = required_env(values, "AIRTABLE_PAT")
    try:
        module = load_airtable_module()
        result = module.request("GET", f"{module.META_URL}/bases/{base_id}/tables")
    finally:
        if previous_pat is None:
            os.environ.pop("AIRTABLE_PAT", None)
        else:
            os.environ["AIRTABLE_PAT"] = previous_pat

    tables: list[dict[str, str]] = []
    for table in result.get("tables", []):
        field_names = [field["name"] for field in table.get("fields", [])]
        tables.append({"id": table["id"], "name": table["name"], "fields": field_names})
    return tables


def parse_tables_output(stdout: str) -> list[dict[str, str]]:
    tables: list[dict[str, str]] = []
    for line in stdout.splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        table_id, table_name = parts[0], parts[1]
        field_blob = parts[2] if len(parts) > 2 else ""
        field_names = [name.strip() for name in re.findall(r"[^,\[\]]+", field_blob) if name.strip()]
        tables.append({"id": table_id, "name": table_name, "fields": field_names})
    return tables


def discover_table(values: dict[str, str], base_id: str) -> tuple[str, str]:
    table_id = env_value(values, "AIRTABLE_TABLE_ID")
    table_name = env_value(values, "AIRTABLE_TABLE_NAME")
    if table_id and table_name:
        return table_id, table_name
    if table_id or table_name:
        chosen_id = table_id or table_name or ""
        chosen_name = table_name or table_id or ""
        return chosen_id, chosen_name

    try:
        tables = tables_from_metadata(values, base_id)
    except Exception:
        result = run_airtable(values, "list-tables", base_id)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "list-tables failed")
        tables = parse_tables_output(result.stdout)

    matches: list[dict[str, str]] = []
    for table in tables:
        field_set = {field.lower() for field in table["fields"]}
        if all(field in field_set for field in REQUIRED_FIELDS):
            matches.append(table)

    if not matches:
        raise SetupError(
            "could not find a table with fields followed_up, why_relevant, and url; set AIRTABLE_TABLE_ID or AIRTABLE_TABLE_NAME"
        )
    if len(matches) > 1:
        names = ", ".join(table["name"] for table in matches)
        raise SetupError(f"multiple matching tables found ({names}); set AIRTABLE_TABLE_ID or AIRTABLE_TABLE_NAME")
    return matches[0]["id"], matches[0]["name"]


def parse_records_output(stdout: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        if not line or line.startswith("#"):
            continue
        records.append(json.loads(line))
    return records


def followed_up_is_no(value: Any) -> bool:
    if value is False or value is None:
        return False
    if isinstance(value, (int, float)) and value == 0:
        return False
    text = str(value).strip().lower()
    return text in {"no", "false", "0"}


def max_rows(values: dict[str, str]) -> int:
    raw = env_value(values, "DRIPR_REDDIT_FOLLOWUPS_MAX_ROWS", str(DEFAULT_MAX_ROWS))
    try:
        parsed = int(raw or str(DEFAULT_MAX_ROWS))
    except ValueError:
        parsed = DEFAULT_MAX_ROWS
    return max(1, min(parsed, DEFAULT_MAX_ROWS))


def fetch_followups(values: dict[str, str]) -> tuple[list[dict[str, str]], bool]:
    base_id = env_value(values, "AIRTABLE_BASE_ID", DEFAULT_BASE_ID) or DEFAULT_BASE_ID
    table_id, table_name = discover_table(values, base_id)
    table_ref = table_id or table_name
    limit = max_rows(values)
    args = [
        "list-records",
        base_id,
        table_ref,
        "--limit",
        str(limit + 1),
        "--filter",
        "{followed_up}='no'",
    ]
    result = run_airtable(values, *args)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "list-records failed")

    rows: list[dict[str, str]] = []
    for record in parse_records_output(result.stdout):
        fields = {key: record.get(key) for key in REQUIRED_FIELDS if key in record}
        if not followed_up_is_no(fields.get("followed_up")):
            continue
        why_relevant = compact(fields.get("why_relevant"))
        url = compact(fields.get("url"))
        if not why_relevant and not url:
            continue
        rows.append(
            {
                "record_id": compact(record.get("id"), 40) or "",
                "why_relevant": why_relevant or "",
                "url": url or "",
            }
        )
    truncated = len(rows) > limit
    return rows[:limit], truncated


def review(values: dict[str, str]) -> dict[str, Any] | str:
    rows, truncated = fetch_followups(values)
    if not rows:
        return "NO_REPLY"
    return {
        "status": "OK",
        "row_count": len(rows),
        "truncated": truncated,
        "followups": rows,
    }


def main() -> int:
    args = parse_args()
    try:
        values = load_env(Path(args.env_file))
        if args.command == "check-config":
            if not env_value(values, "AIRTABLE_PAT"):
                raise SetupError("missing AIRTABLE_PAT")
            if not AIRTABLE_SCRIPT.exists():
                raise SetupError("native-airtable skill is not installed")
            discover_table(values, env_value(values, "AIRTABLE_BASE_ID", DEFAULT_BASE_ID) or DEFAULT_BASE_ID)
            print(json.dumps({"status": "OK"}, sort_keys=True))
            return 0
        result = review(values)
    except SetupError as error:
        result = {"status": "SETUP_REQUIRED", "reason": compact_error(error)}
    except Exception as error:
        result = {"status": "ERROR", "reason": compact_error(error)}

    if isinstance(result, str):
        print(result)
    else:
        print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
