#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

try:
    import boto3
except ImportError:  # pragma: no cover - depends on live OpenClaw image
    boto3 = None

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
DEFAULT_ENV_FILE = OPENCLAW_ROOT / "secrets" / "dripr-production-debug.env"
DEFAULT_REPO_PATH = WORKSPACE_ROOT / "runtime" / "repos" / "dripr"
DEFAULT_MYSQL_ENV_FILE = OPENCLAW_ROOT / "secrets" / "mysql-new-users.env"
DEFAULT_CLOUDWATCH_ENV_FILE = OPENCLAW_ROOT / "secrets" / "cloudwatch-dashboard.env"
DEFAULT_REGION = "us-east-1"
DEFAULT_LOG_GROUPS = [
    "/aws/lightsail/dripr/api-gateway",
    "/aws/lightsail/dripr/cron-jobs",
    "/aws/lightsail/dripr/data-fetcher",
    "/aws/lightsail/dripr/email-manager",
    "/aws/lightsail/dripr/market-data-cleaner",
    "/aws/lightsail/dripr/issue-auditor",
    "/aws/lightsail/dripr/usage-reporter",
    "/aws/lightsail/dripr/dripr-service",
]
MAX_FIELD_CHARS = 240
MAX_ERROR_CHARS = 320
MAX_LOG_MESSAGE_CHARS = 500
DANGEROUS_SQL_RE = re.compile(
    r"\b(ALTER|CREATE|DELETE|DROP|GRANT|INSERT|LOAD|REPLACE|REVOKE|TRUNCATE|UPDATE)\b",
    re.IGNORECASE,
)
EMAIL_RE = re.compile(r"([A-Z0-9._%+-])[A-Z0-9._%+-]*(@[A-Z0-9.-]+\.[A-Z]{2,})", re.IGNORECASE)
AWS_ACCOUNT_RE = re.compile(r"\b\d{12}\b")
AWS_ARN_RE = re.compile(r"arn:aws:[^\s,;]+")


class SetupError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only Dripr production debugging helper.")
    parser.add_argument("--env-file", default=os.environ.get("DRIPR_DEBUG_ENV", str(DEFAULT_ENV_FILE)))
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("check-config", help="Validate repo and credential plumbing without querying production data.")
    subparsers.add_parser("repo-status", help="Return compact Dripr checkout status and key docs availability.")

    test_parser = subparsers.add_parser("run-test", help="Run a Dripr test command only after Kenny explicitly approves it.")
    test_parser.add_argument("target", choices=["python-unit", "ui-unit", "integration-trial"])
    test_parser.add_argument("--kenny-approved", action="store_true", help="Required: Kenny explicitly asked to run Dripr tests.")

    mysql_parser = subparsers.add_parser("mysql-query", help="Run one bounded read-only MySQL SELECT/WITH query.")
    mysql_source = mysql_parser.add_mutually_exclusive_group(required=True)
    mysql_source.add_argument("--sql")
    mysql_source.add_argument("--sql-file")
    mysql_parser.add_argument("--max-rows", type=int)

    logs_parser = subparsers.add_parser("cloudwatch-logs", help="Search bounded CloudWatch log windows.")
    logs_parser.add_argument("--filter-pattern", required=True)
    logs_parser.add_argument("--since-hours", type=int, default=6)
    logs_parser.add_argument("--limit", type=int, default=50)
    logs_parser.add_argument("--log-group", action="append", dest="log_groups")

    return parser.parse_args()


def compact(value: Any, max_chars: int = MAX_FIELD_CHARS) -> str | int | float | bool | None:
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, datetime):
        text = value.isoformat(timespec="seconds")
    else:
        text = re.sub(r"\s+", " ", str(value).strip())
    text = EMAIL_RE.sub(lambda match: f"{match.group(1)}***{match.group(2)}", text)
    text = AWS_ARN_RE.sub("[aws-arn-redacted]", text)
    text = AWS_ACCOUNT_RE.sub("[aws-account-redacted]", text)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "..."


def compact_error(error: BaseException) -> str:
    return str(compact(error, MAX_ERROR_CHARS))


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


def load_env(path: Path, *, required: bool = False) -> dict[str, str]:
    if not path.exists():
        if required:
            raise SetupError(f"missing env file: {path}")
        return {}
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        parsed = parse_env_line(line)
        if parsed:
            key, value = parsed
            values[key] = value
    return values


def env_value(values: dict[str, str], key: str, default: str | None = None) -> str | None:
    return os.environ.get(key) or values.get(key) or default


def positive_int(value: int | str | None, default: int, max_value: int) -> int:
    try:
        parsed = int(value or default)
    except ValueError:
        return default
    return max(1, min(parsed, max_value))


def repo_path(values: dict[str, str]) -> Path:
    return Path(env_value(values, "DRIPR_REPO_PATH", str(DEFAULT_REPO_PATH)) or DEFAULT_REPO_PATH)


def run_command(command: list[str], cwd: Path, timeout_seconds: int = 120) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout_seconds,
        check=False,
    )
    output = "\n".join(line[:500] for line in completed.stdout.splitlines()[-80:])
    return {
        "command": " ".join(command),
        "exit_code": completed.returncode,
        "output_tail": output,
    }


def require_repo(path: Path) -> None:
    if not path.exists():
        raise SetupError(f"missing Dripr repo: {path}")
    if not (path / ".git").exists():
        raise SetupError(f"Dripr repo path is not a git checkout: {path}")


def repo_status(values: dict[str, str]) -> dict[str, Any]:
    path = repo_path(values)
    require_repo(path)
    docs = [
        "AGENTS.md",
        "docs-internal/system-design.md",
        "docs-internal/campaign-state-machine.md",
        "docs-internal/testing-strategy.md",
        "docs-internal/development-guide.md",
    ]
    docs.extend(str(skill_path.relative_to(path)) for skill_path in sorted((path / ".agent" / "skills").glob("*/SKILL.md")))
    branch = run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"], path, 30)
    commit = run_command(["git", "rev-parse", "--short", "HEAD"], path, 30)
    status = run_command(["git", "status", "--short"], path, 30)
    return {
        "status": "OK",
        "repo_path": str(path),
        "branch": branch["output_tail"].strip(),
        "commit": commit["output_tail"].strip(),
        "dirty": bool(status["output_tail"].strip()),
        "dirty_summary": status["output_tail"].splitlines()[:20],
        "python_venv": (path / "python" / "venv" / "bin" / "python").exists(),
        "ui_node_modules": (path / "ui" / "node_modules").exists(),
        "docs": {doc: (path / doc).exists() for doc in docs},
    }


def run_test(values: dict[str, str], target: str) -> dict[str, Any]:
    if not values.get("_kenny_approved"):
        raise SetupError("Kenny must explicitly approve running Dripr tests or repo scripts")
    path = repo_path(values)
    require_repo(path)
    if target == "python-unit":
        return {"status": "OK", "target": target, **run_command(["./venv/bin/python", "-m", "pytest", "tests/unit/", "--maxfail=1"], path / "python", 600)}
    if target == "ui-unit":
        env = os.environ.copy()
        env["NODE_ENV"] = "development"
        completed = subprocess.run(
            ["./node_modules/.bin/tsx", "--test", "src/**/*.test.ts"],
            cwd=path / "ui",
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=300,
            check=False,
        )
        return {
            "status": "OK",
            "target": target,
            "command": "NODE_ENV=development ./node_modules/.bin/tsx --test 'src/**/*.test.ts'",
            "exit_code": completed.returncode,
            "output_tail": "\n".join(line[:500] for line in completed.stdout.splitlines()[-80:]),
        }
    if target == "integration-trial":
        integration_env = path / "env" / "integration.env"
        if not integration_env.exists():
            raise SetupError("missing env/integration.env")
        (path / ".env").write_text(integration_env.read_text())
        return {
            "status": "OK",
            "target": target,
            **run_command(["./venv/bin/python", "-m", "pytest", "tests/integration/test_trial_period.py", "--maxfail=1"], path / "python", 900),
        }
    raise SetupError(f"unsupported test target: {target}")


def mysql_env(values: dict[str, str]) -> dict[str, str]:
    mysql_env_file = Path(env_value(values, "DRIPR_MYSQL_ENV_FILE", str(DEFAULT_MYSQL_ENV_FILE)) or DEFAULT_MYSQL_ENV_FILE)
    mysql_values = load_env(mysql_env_file, required=True)
    for key, value in values.items():
        if key.startswith("MYSQL_"):
            mysql_values.setdefault(key, value)
    return mysql_values


def validate_sql(sql: str) -> str:
    query = sql.strip().rstrip(";")
    first_word = query.split(None, 1)[0].upper() if query.split(None, 1) else ""
    if first_word not in {"SELECT", "WITH"}:
        raise SetupError("debug query must be read-only SELECT or WITH")
    if ";" in query or DANGEROUS_SQL_RE.search(query):
        raise SetupError("debug query must not contain multiple statements or mutations")
    return query


def mysql_connection_config(values: dict[str, str]) -> dict[str, Any]:
    required = ["MYSQL_HOST", "MYSQL_DATABASE", "MYSQL_USER", "MYSQL_PASSWORD"]
    missing = [key for key in required if not env_value(values, key)]
    if missing:
        raise SetupError(f"missing MySQL config: {', '.join(missing)}")
    config: dict[str, Any] = {
        "host": env_value(values, "MYSQL_HOST"),
        "port": positive_int(env_value(values, "MYSQL_PORT"), 3306, 65535),
        "database": env_value(values, "MYSQL_DATABASE"),
        "user": env_value(values, "MYSQL_USER"),
        "password": env_value(values, "MYSQL_PASSWORD"),
    }
    if env_value(values, "MYSQL_SSL_CA"):
        config["ssl_ca"] = env_value(values, "MYSQL_SSL_CA")
    return config


def mysql_connect(config: dict[str, Any]):
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
    raise SetupError("missing Python MySQL driver")


def mysql_query(values: dict[str, str], args: argparse.Namespace) -> dict[str, Any]:
    mysql_values = mysql_env(values)
    sql = Path(args.sql_file).read_text() if args.sql_file else args.sql
    query = validate_sql(sql)
    max_rows = positive_int(args.max_rows or env_value(values, "DRIPR_DEBUG_MYSQL_MAX_ROWS"), 50, 200)
    connection = mysql_connect(mysql_connection_config(mysql_values))
    try:
        cursor = connection.cursor(dictionary=True) if mysql_connector is not None else connection.cursor()
        try:
            cursor.execute("START TRANSACTION READ ONLY")
            cursor.execute(query)
            rows = [dict(row) for row in cursor.fetchmany(max_rows + 1)]
            cursor.execute("ROLLBACK")
        finally:
            cursor.close()
    finally:
        connection.close()
    return {
        "status": "OK",
        "row_count": min(len(rows), max_rows),
        "truncated": len(rows) > max_rows,
        "rows": [{key: compact(value) for key, value in row.items()} for row in rows[:max_rows]],
    }


def cloudwatch_values(values: dict[str, str]) -> dict[str, str]:
    cloudwatch_env_file = Path(env_value(values, "DRIPR_CLOUDWATCH_ENV_FILE", str(DEFAULT_CLOUDWATCH_ENV_FILE)) or DEFAULT_CLOUDWATCH_ENV_FILE)
    cloudwatch = load_env(cloudwatch_env_file)
    cloudwatch.update({key: value for key, value in values.items() if key.startswith("AWS_") or key.startswith("CLOUDWATCH_")})
    return cloudwatch


def configure_aws_env(values: dict[str, str]) -> None:
    for key, value in values.items():
        if key.startswith("AWS_") and key not in os.environ:
            os.environ[key] = value


def logs_client(values: dict[str, str]):
    if boto3 is None:
        raise SetupError("missing Python AWS driver: install boto3")
    configure_aws_env(values)
    region = env_value(values, "CLOUDWATCH_REGION", DEFAULT_REGION)
    profile = env_value(values, "AWS_PROFILE")
    if profile:
        session = boto3.Session(profile_name=profile, region_name=region)
    else:
        session = boto3.Session(region_name=region)
    return session.client("logs")


def parse_log_groups(values: dict[str, str], explicit: list[str] | None) -> list[str]:
    if explicit:
        return explicit
    raw = env_value(values, "DRIPR_DEBUG_LOG_GROUPS")
    if raw:
        return [item.strip() for item in raw.split(",") if item.strip()]
    return DEFAULT_LOG_GROUPS


def cloudwatch_logs(values: dict[str, str], args: argparse.Namespace) -> dict[str, Any]:
    cloudwatch = cloudwatch_values(values)
    client = logs_client(cloudwatch)
    since_hours = positive_int(args.since_hours, 6, 168)
    limit = positive_int(args.limit, 50, 500)
    now_utc = datetime.now(timezone.utc)
    start_ms = int((now_utc - timedelta(hours=since_hours)).timestamp() * 1000)
    end_ms = int(now_utc.timestamp() * 1000)
    events: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    searched: list[str] = []
    for group_name in parse_log_groups(values, args.log_groups):
        searched.append(group_name)
        paginator = client.get_paginator("filter_log_events")
        try:
            pages = paginator.paginate(
                logGroupName=group_name,
                startTime=start_ms,
                endTime=end_ms,
                filterPattern=args.filter_pattern,
            )
            for page in pages:
                for event in page.get("events", []):
                    events.append(
                        {
                            "timestamp": datetime.fromtimestamp(event.get("timestamp", 0) / 1000, timezone.utc),
                            "log_group": group_name,
                            "stream": compact(event.get("logStreamName"), 120),
                            "message": compact(event.get("message"), MAX_LOG_MESSAGE_CHARS),
                        }
                    )
                    if len(events) >= limit:
                        break
                if len(events) >= limit:
                    break
        except Exception as error:  # keep searching other groups when one group is missing
            errors.append({"log_group": group_name, "error": compact_error(error)})
        if len(events) >= limit:
            break
    status = "OK"
    if errors and events:
        status = "PARTIAL"
    elif errors:
        status = "ERROR"
    return {
        "status": status,
        "region": env_value(cloudwatch, "CLOUDWATCH_REGION", DEFAULT_REGION),
        "since_hours": since_hours,
        "searched_log_groups": searched,
        "event_count": len(events),
        "errors": errors,
        "truncated": len(events) >= limit,
        "events": events,
    }


def check_config(values: dict[str, str]) -> dict[str, Any]:
    status = repo_status(values)
    mysql_ok = True
    cloudwatch_ok = True
    try:
        mysql_connection_config(mysql_env(values))
    except Exception:
        mysql_ok = False
    try:
        cloudwatch_values(values)
        if boto3 is None:
            cloudwatch_ok = False
    except Exception:
        cloudwatch_ok = False
    return {
        "status": "OK",
        "repo": {
            "path": status["repo_path"],
            "branch": status["branch"],
            "commit": status["commit"],
            "dirty": status["dirty"],
            "python_venv": status["python_venv"],
            "ui_node_modules": status["ui_node_modules"],
        },
        "mysql_config_present": mysql_ok,
        "cloudwatch_driver_present": cloudwatch_ok,
    }


def main() -> int:
    args = parse_args()
    try:
        values = load_env(Path(args.env_file))
        if args.command == "check-config":
            result = check_config(values)
        elif args.command == "repo-status":
            result = repo_status(values)
        elif args.command == "run-test":
            values["_kenny_approved"] = "1" if args.kenny_approved else ""
            result = run_test(values, args.target)
        elif args.command == "mysql-query":
            result = mysql_query(values, args)
        elif args.command == "cloudwatch-logs":
            result = cloudwatch_logs(values, args)
        else:
            raise SetupError(f"unknown command: {args.command}")
    except SetupError as error:
        result = {"status": "SETUP_REQUIRED", "reason": compact_error(error)}
    except Exception as error:
        result = {"status": "ERROR", "reason": compact_error(error)}
    print(json.dumps(result, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
