#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

try:
    import mysql.connector as mysql_connector
except ImportError:  # pragma: no cover - depends on live OpenClaw image
    mysql_connector = None

try:
    import pymysql
except ImportError:  # pragma: no cover - depends on live OpenClaw image
    pymysql = None


ET = ZoneInfo("America/New_York")
WORKSPACE_ROOT = Path(os.environ.get("OPENCLAW_WORKSPACE_DIR", "/home/node/.openclaw/workspace"))
OPENCLAW_ROOT = WORKSPACE_ROOT.parent
DEFAULT_ENV_FILE = OPENCLAW_ROOT / "secrets" / "mysql-new-users.env"
DEFAULT_MAX_ROWS = 25
DEFAULT_SINCE_HOURS = 25
MAX_FIELD_CHARS = 180
MAX_ERROR_CHARS = 220
REQUIRED_ENV_KEYS = ("MYSQL_HOST", "MYSQL_DATABASE", "MYSQL_USER", "MYSQL_PASSWORD")
DANGEROUS_SQL_RE = re.compile(
    r"\b(ALTER|CREATE|DELETE|DROP|GRANT|INSERT|LOAD|REPLACE|REVOKE|TRUNCATE|UPDATE)\b",
    re.IGNORECASE,
)


class SetupError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check MySQL for newly-created users.")
    parser.add_argument("--env-file", default=os.environ.get("MYSQL_NEW_USERS_ENV", str(DEFAULT_ENV_FILE)))
    parser.add_argument("--now", help="Override current time for tests (ISO-8601).")
    parser.add_argument("--json", action="store_true", help="Print explicit JSON NO_REPLY payloads.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("review", help="Query MySQL and return compact new-user context.")
    subparsers.add_parser("check-config", help="Validate required configuration without querying.")
    return parser.parse_args()


def compact(value: Any, max_chars: int = MAX_FIELD_CHARS) -> str | int | float | bool | None:
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, datetime):
        text = value.isoformat(timespec="seconds")
    else:
        text = re.sub(r"\s+", " ", str(value).strip())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "..."


def compact_error(error: BaseException) -> str:
    return str(error).replace("\n", " ")[:MAX_ERROR_CHARS]


def now_et(raw: str | None = None) -> datetime:
    if not raw:
        return datetime.now(ET)
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ET)
    return parsed.astimezone(ET)


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


def positive_int(value: str | None, default: int, max_value: int) -> int:
    try:
        parsed = int(value or default)
    except ValueError:
        return default
    return max(1, min(parsed, max_value))


def read_query(values: dict[str, str]) -> str:
    query_file = env_value(values, "MYSQL_NEW_USERS_QUERY_FILE")
    query = env_value(values, "MYSQL_NEW_USERS_QUERY")
    if query_file:
        query_path = Path(query_file)
        if not query_path.exists():
            raise SetupError(f"missing query file: {query_file}")
        query = query_path.read_text()
    if not query or not query.strip():
        raise SetupError("missing MYSQL_NEW_USERS_QUERY or MYSQL_NEW_USERS_QUERY_FILE")
    query = query.strip().rstrip(";")
    first_word = query.split(None, 1)[0].upper() if query.split(None, 1) else ""
    if first_word not in {"SELECT", "WITH"}:
        raise SetupError("new-user query must be read-only SELECT or WITH")
    if ";" in query or DANGEROUS_SQL_RE.search(query):
        raise SetupError("new-user query must not contain multiple statements or mutations")
    return query


def connection_config(values: dict[str, str]) -> dict[str, Any]:
    for key in REQUIRED_ENV_KEYS:
        required_env(values, key)
    config: dict[str, Any] = {
        "host": required_env(values, "MYSQL_HOST"),
        "port": positive_int(env_value(values, "MYSQL_PORT"), 3306, 65535),
        "database": required_env(values, "MYSQL_DATABASE"),
        "user": required_env(values, "MYSQL_USER"),
        "password": required_env(values, "MYSQL_PASSWORD"),
    }
    if env_value(values, "MYSQL_SSL_CA"):
        config["ssl_ca"] = env_value(values, "MYSQL_SSL_CA")
    return config


def connect(config: dict[str, Any]):
    if mysql_connector is not None:
        return mysql_connector.connect(**config)
    if pymysql is not None:
        pymysql_config = {
            "host": config["host"],
            "port": config["port"],
            "database": config["database"],
            "user": config["user"],
            "password": config["password"],
            "cursorclass": pymysql.cursors.DictCursor,
        }
        if config.get("ssl_ca"):
            pymysql_config["ssl"] = {"ca": config["ssl_ca"]}
        return pymysql.connect(**pymysql_config)
    raise SetupError("missing Python MySQL driver: install mysql-connector-python or PyMySQL")


def fetch_rows(config: dict[str, Any], query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    connection = connect(config)
    try:
        cursor = connection.cursor(dictionary=True) if mysql_connector is not None else connection.cursor()
        try:
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            cursor.close()
    finally:
        connection.close()


def allowed_fields(values: dict[str, str]) -> list[str] | None:
    raw = env_value(values, "MYSQL_NEW_USERS_FIELDS")
    if not raw:
        return None
    fields = [field.strip() for field in raw.split(",") if field.strip()]
    return fields or None


def compact_rows(rows: list[dict[str, Any]], fields: list[str] | None, max_rows: int) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    for row in rows[:max_rows]:
        source = {field: row.get(field) for field in fields} if fields else row
        compacted.append({key: compact(value) for key, value in source.items()})
    return compacted


def setup_required(reason: str) -> dict[str, Any]:
    return {"status": "SETUP_REQUIRED", "reason": reason}


def review(args: argparse.Namespace) -> dict[str, Any] | str:
    values = load_env(Path(args.env_file))
    query = read_query(values)
    max_rows = positive_int(env_value(values, "MYSQL_NEW_USERS_MAX_ROWS"), DEFAULT_MAX_ROWS, 100)
    since_hours = positive_int(env_value(values, "MYSQL_NEW_USERS_SINCE_HOURS"), DEFAULT_SINCE_HOURS, 168)
    current_et = now_et(args.now)
    since_et = current_et - timedelta(hours=since_hours)
    params = {
        "since_utc": since_et.astimezone(timezone.utc).replace(tzinfo=None),
        "since_et": since_et.replace(tzinfo=None),
        "now_utc": current_et.astimezone(timezone.utc).replace(tzinfo=None),
        "now_et": current_et.replace(tzinfo=None),
        "limit": max_rows,
    }
    rows = fetch_rows(connection_config(values), query, params)
    if not rows:
        return {"status": "NO_REPLY"} if args.json else "NO_REPLY"
    return {
        "status": "OK",
        "checked_at_et": current_et.isoformat(timespec="seconds"),
        "window_hours": since_hours,
        "row_count": len(rows),
        "max_rows": max_rows,
        "truncated": len(rows) > max_rows,
        "users": compact_rows(rows, allowed_fields(values), max_rows),
    }


def main() -> int:
    args = parse_args()
    try:
        if args.command == "check-config":
            values = load_env(Path(args.env_file))
            read_query(values)
            connection_config(values)
            if mysql_connector is None and pymysql is None:
                raise SetupError("missing Python MySQL driver: install mysql-connector-python or PyMySQL")
            print(json.dumps({"status": "OK"}, sort_keys=True))
            return 0
        result = review(args)
    except SetupError as error:
        result = setup_required(compact_error(error))
    except Exception as error:
        result = {"status": "ERROR", "reason": compact_error(error)}

    if isinstance(result, str):
        print(result)
    else:
        print(json.dumps(result, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
