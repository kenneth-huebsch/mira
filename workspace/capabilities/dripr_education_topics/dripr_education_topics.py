#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import uuid
from calendar import monthrange
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote
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
DEFAULT_REPO_PATH = WORKSPACE_ROOT / "runtime" / "repos" / "dripr"
DEFAULT_RUN_ROOT = WORKSPACE_ROOT / "runtime" / "capability-runs" / "dripr-education-topics"
DEFAULT_OVERRIDE_ENV_FILE = WORKSPACE_ROOT.parent / "secrets" / "dripr-education-topics.env"
DEFAULT_BEDROCK_REGION = "us-west-2"
STABLE_IMAGE_MODEL_ID = "stability.stable-image-core-v1:1"
PROD_ENV_NAME = "prod"
STAGING_ENV_NAME = "staging"
PROD_ENV_KEYS = (
    "DATABASE_URL",
    "DRIPR_API_KEY",
    "VITE_API_GATEWAY_URL",
    "AWS_ACCESS_KEY",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_REGION",
)
RECENT_TOPICS_SQL = """
SELECT month, year, title, content, image_url
FROM education_topics
WHERE (year * 100 + month) >= ((YEAR(CURDATE()) - 2) * 100 + MONTH(CURDATE()))
ORDER BY year DESC, month DESC
""".strip()
VERIFY_TOPIC_SQL = """
SELECT month, year, title, image_url
FROM education_topics
WHERE month = %s AND year = %s
""".strip()
FETCH_TOPIC_SQL = """
SELECT month, year, title, content, image_url
FROM education_topics
WHERE month = %s AND year = %s
""".strip()
INSERT_TOPIC_SQL = """
INSERT INTO education_topics (id, creation_datetime, month, year, title, content, image_url)
VALUES (%s, %s, %s, %s, %s, %s, %s)
""".strip()
MAX_FIELD_CHARS = 280
DANGEROUS_SQL_RE = re.compile(
    r"\b(ALTER|CREATE|DELETE|DROP|GRANT|INSERT|LOAD|REPLACE|REVOKE|TRUNCATE|UPDATE)\b",
    re.IGNORECASE,
)


class SetupError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interactive Dripr education topics helper.")
    parser.add_argument(
        "--env-file",
        default=os.environ.get("DRIPR_EDUCATION_TOPICS_ENV", str(DEFAULT_OVERRIDE_ENV_FILE)),
        help="Optional override env file. Dripr env/prod.env is the primary credential source.",
    )
    parser.add_argument("--now", help="Override current time for tests (ISO-8601, Eastern assumed if naive).")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("check-config", help="Validate repo and Dripr env/prod.env readiness.")
    subparsers.add_parser("sync-repo", help="Run git pull --ff-only in the Dripr checkout.")
    subparsers.add_parser(
        "check-next-month",
        help="On the monthly trigger day, check whether next month's prod education topic exists.",
    )
    subparsers.add_parser("recent-topics", help="List production education topics from the past two years.")

    generate_image = subparsers.add_parser(
        "generate-image",
        help="Generate a PNG illustration for an education topic through Bedrock Stable Image Core.",
    )
    generate_image.add_argument("--title", required=True, help="Education topic title used in the image prompt.")
    generate_image.add_argument(
        "--visual-concept",
        help="Optional visual concept for the prompt. Required unless --prompt is provided.",
    )
    generate_image.add_argument(
        "--prompt",
        help="Optional full Bedrock prompt override. When set, --visual-concept is ignored.",
    )
    generate_image.add_argument("--output", required=True, help="Output .png path.")

    publish = subparsers.add_parser(
        "publish",
        help="Publish an approved education topic to production through the Dripr API.",
    )
    publish.add_argument(
        "--kenny-approved",
        action="store_true",
        help="Required: Kenny explicitly approved this publish.",
    )
    publish.add_argument("--month", type=int, required=True)
    publish.add_argument("--year", type=int, required=True)
    publish.add_argument("--title", required=True)
    publish.add_argument("--content", required=True)
    publish.add_argument("--image", required=True)

    copy_to_staging = subparsers.add_parser(
        "copy-to-staging",
        help="Copy a production education topic row into dripr-staging when Kenny explicitly asks.",
    )
    copy_to_staging.add_argument("--month", type=int, required=True)
    copy_to_staging.add_argument("--year", type=int, required=True)

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


def load_env(path: Path, required: bool = False) -> dict[str, str]:
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


def load_override_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return load_env(path)


def env_value(key: str, default: str = "", *mappings: dict[str, str]) -> str:
    if os.environ.get(key):
        return os.environ.get(key) or default
    for mapping in mappings:
        if mapping.get(key):
            return mapping[key]
    return default


def positive_int(value: int | str | None, default: int, max_value: int) -> int:
    try:
        parsed = int(value or default)
    except ValueError:
        return default
    return max(1, min(parsed, max_value))


def compact(value: Any, max_chars: int = MAX_FIELD_CHARS) -> str | int | float | bool | None:
    if value is None or isinstance(value, (int, float, bool)):
        return value
    text = re.sub(r"\s+", " ", str(value).strip())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "..."


def compact_error(error: BaseException) -> str:
    return str(compact(error, MAX_FIELD_CHARS))


def now_et(raw: str | None = None) -> datetime:
    if not raw:
        return datetime.now(ET)
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ET)
    return parsed.astimezone(ET)


def is_monthly_trigger_day(dt: datetime) -> bool:
    last_day = monthrange(dt.year, dt.month)[1]
    return dt.day == last_day - 14


def next_calendar_month(dt: datetime) -> tuple[int, int]:
    if dt.month == 12:
        return 1, dt.year + 1
    return dt.month + 1, dt.year


def month_year_label(month: int, year: int) -> str:
    return datetime(year, month, 1, tzinfo=ET).strftime("%B %Y")


def dripr_repo(overrides: dict[str, str]) -> Path:
    return Path(env_value("DRIPR_REPO_PATH", str(DEFAULT_REPO_PATH), overrides))


def run_root(overrides: dict[str, str]) -> Path:
    return Path(env_value("DRIPR_EDUCATION_TOPICS_RUN_ROOT", str(DEFAULT_RUN_ROOT), overrides))


def load_dripr_env_file(repo: Path, env_name: str) -> dict[str, str]:
    path = repo / "env" / f"{env_name}.env"
    if not path.exists():
        raise SetupError(f"missing Dripr env file: {path}")
    return load_env(path, required=True)


def parse_database_url(database_url: str) -> dict[str, Any]:
    if "@" not in database_url or "/" not in database_url:
        raise SetupError("DATABASE_URL must look like user:password@host:port/database")
    user_pass, host_part = database_url.rsplit("@", 1)
    if ":" not in user_pass:
        raise SetupError("DATABASE_URL is missing user:password")
    user, password = user_pass.split(":", 1)
    host_port, database = host_part.split("/", 1)
    database = database.split("?", 1)[0]
    if ":" in host_port:
        host, port_text = host_port.rsplit(":", 1)
        port = positive_int(port_text, 3306, 65535)
    else:
        host, port = host_port, 3306
    if not user or not password or not host or not database:
        raise SetupError("DATABASE_URL is missing user, password, host, or database")
    return {
        "user": unquote(user),
        "password": unquote(password),
        "host": host,
        "port": port,
        "database": database,
    }


def mysql_connection_config_from_dripr_env(dripr_env: dict[str, str]) -> dict[str, Any]:
    database_url = env_value("DATABASE_URL", "", dripr_env)
    if not database_url:
        raise SetupError("DATABASE_URL missing from Dripr env file")
    return parse_database_url(database_url)


def mysql_connect(config: dict[str, Any]):
    if mysql_connector is not None:
        return mysql_connector.connect(
            host=config["host"],
            port=config["port"],
            database=config["database"],
            user=config["user"],
            password=config["password"],
        )
    if pymysql is not None:
        return pymysql.connect(
            host=config["host"],
            port=config["port"],
            database=config["database"],
            user=config["user"],
            password=config["password"],
            cursorclass=pymysql.cursors.DictCursor,
        )
    raise SetupError("missing Python MySQL driver")


def validate_readonly_sql(sql: str) -> str:
    query = sql.strip().rstrip(";")
    first_word = query.split(None, 1)[0].upper() if query.split(None, 1) else ""
    if first_word not in {"SELECT", "WITH"}:
        raise SetupError("query must be read-only SELECT or WITH")
    if ";" in query or DANGEROUS_SQL_RE.search(query):
        raise SetupError("query must not contain multiple statements or mutations")
    return query


def run_mysql_query_for_config(
    mysql_config: dict[str, Any],
    sql: str,
    params: tuple[Any, ...] | None = None,
    max_rows: int = 50,
) -> list[dict[str, Any]]:
    query = validate_readonly_sql(sql)
    connection = mysql_connect(mysql_config)
    try:
        cursor = connection.cursor(dictionary=True) if mysql_connector is not None else connection.cursor()
        try:
            cursor.execute("START TRANSACTION READ ONLY")
            cursor.execute(query, params or ())
            rows = [dict(row) for row in cursor.fetchmany(max_rows + 1)]
            cursor.execute("ROLLBACK")
        finally:
            cursor.close()
    finally:
        connection.close()
    return rows[:max_rows]


def run_mysql_query_for_dripr_env(
    dripr_env: dict[str, str],
    sql: str,
    params: tuple[Any, ...] | None = None,
    max_rows: int = 50,
) -> list[dict[str, Any]]:
    return run_mysql_query_for_config(
        mysql_connection_config_from_dripr_env(dripr_env),
        sql,
        params,
        max_rows,
    )


def insert_education_topic_row(mysql_config: dict[str, Any], row: dict[str, Any]) -> None:
    connection = mysql_connect(mysql_config)
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(
                INSERT_TOPIC_SQL,
                (
                    row["id"],
                    row["creation_datetime"],
                    row["month"],
                    row["year"],
                    row["title"],
                    row["content"],
                    row["image_url"],
                ),
            )
            connection.commit()
        finally:
            cursor.close()
    finally:
        connection.close()


def validate_month_year(month: int, year: int) -> None:
    if month < 1 or month > 12:
        raise SetupError("month must be between 1 and 12")
    if year < 2000 or year > 2100:
        raise SetupError("year must be between 2000 and 2100")


def validate_topic_text(title: str, content: str) -> tuple[str, str]:
    clean_title = title.strip()
    clean_content = content.strip()
    if not clean_title:
        raise SetupError("title is required")
    if not clean_content:
        raise SetupError("content is required")
    if len(clean_title) > 128:
        raise SetupError("title must be 128 characters or fewer")
    if len(clean_content) > 2048:
        raise SetupError("content must be 2048 characters or fewer")
    return clean_title, clean_content


def required_env_keys(env_values: dict[str, str], keys: list[str]) -> list[str]:
    return [key for key in keys if not env_value(key, "", env_values)]


def aws_runtime_status(dripr_env: dict[str, str], overrides: dict[str, str]) -> dict[str, Any]:
    region = env_value("DRIPR_BEDROCK_REGION", DEFAULT_BEDROCK_REGION, overrides, dripr_env)
    access_key = env_value("AWS_ACCESS_KEY", "", overrides, dripr_env)
    secret_key = env_value("AWS_SECRET_ACCESS_KEY", "", overrides, dripr_env)
    status: dict[str, Any] = {
        "available": False,
        "region": region,
        "boto3_version": None,
        "sts_available": False,
        "bedrock_runtime_available": False,
    }
    if not access_key or not secret_key:
        status["output"] = "AWS_ACCESS_KEY/AWS_SECRET_ACCESS_KEY missing from Dripr prod.env"
        return status
    if boto3 is None:
        status["output"] = "boto3 is not available"
        return status

    status["boto3_version"] = boto3.__version__
    client_kwargs = {
        "aws_access_key_id": access_key,
        "aws_secret_access_key": secret_key,
        "region_name": region,
    }
    try:
        boto3.client("sts", **client_kwargs).get_caller_identity()
        status["sts_available"] = True
    except Exception as error:
        status["output"] = f"STS check failed: {compact_error(error)}"
        return status

    try:
        boto3.client("bedrock-runtime", **client_kwargs)
        status["bedrock_runtime_available"] = True
        status["available"] = True
    except Exception as error:
        status["output"] = (
            "bedrock-runtime client unavailable; container needs boto3>=1.34 "
            f"({compact_error(error)})"
        )
    return status


def build_education_topic_image_prompt(title: str, visual_concept: str) -> str:
    return (
        "Create a landscape editorial illustration for a real estate newsletter Expert Tips section.\n"
        f"Topic: {title}.\n"
        f"Visual concept: {visual_concept}\n"
        "Style: clean modern vector/editorial illustration, warm approachable colors, "
        "professional but playful, simple composition, soft depth, high quality.\n"
        "Constraints: absolutely no text, no letters, no numbers, no captions, no document writing, "
        "no labels, no logos, no watermarks, no photorealistic people, no distorted hands or faces."
    )


def resolve_image_prompt(title: str, visual_concept: str | None, prompt_override: str | None) -> str:
    clean_title = title.strip()
    if not clean_title:
        raise SetupError("title is required")
    if prompt_override and prompt_override.strip():
        return prompt_override.strip()
    if not visual_concept or not visual_concept.strip():
        raise SetupError("provide --visual-concept or --prompt for image generation")
    return build_education_topic_image_prompt(clean_title, visual_concept.strip())


def bedrock_runtime_client(dripr_env: dict[str, str], overrides: dict[str, str]):
    if boto3 is None:
        raise SetupError("boto3 is not available")
    region = env_value("DRIPR_BEDROCK_REGION", DEFAULT_BEDROCK_REGION, overrides, dripr_env)
    access_key = env_value("AWS_ACCESS_KEY", "", overrides, dripr_env)
    secret_key = env_value("AWS_SECRET_ACCESS_KEY", "", overrides, dripr_env)
    if not access_key or not secret_key:
        raise SetupError("AWS_ACCESS_KEY/AWS_SECRET_ACCESS_KEY missing from Dripr prod.env")
    try:
        return boto3.client(
            "bedrock-runtime",
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        ), region
    except Exception as error:
        raise SetupError(
            "bedrock-runtime client unavailable; container needs boto3>=1.34 "
            f"({compact_error(error)})"
        ) from error


def generate_topic_image(overrides: dict[str, str], args: argparse.Namespace) -> dict[str, Any]:
    output_path = Path(args.output)
    if output_path.suffix.lower() != ".png":
        raise SetupError("output must be a .png path")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    prompt = resolve_image_prompt(args.title, args.visual_concept, args.prompt)
    repo = dripr_repo(overrides)
    prod_env = load_dripr_env_file(repo, PROD_ENV_NAME)
    client, region = bedrock_runtime_client(prod_env, overrides)

    response = client.invoke_model(
        modelId=STABLE_IMAGE_MODEL_ID,
        body=json.dumps(
            {
                "prompt": prompt,
                "mode": "text-to-image",
                "aspect_ratio": "16:9",
                "output_format": "png",
            }
        ),
        contentType="application/json",
        accept="application/json",
    )
    payload = json.loads(response["body"].read())
    images = payload.get("images") or []
    if not images:
        raise SetupError("Bedrock returned no images")

    image_bytes = base64.b64decode(images[0])
    output_path.write_bytes(image_bytes)
    return {
        "status": "OK",
        "model": STABLE_IMAGE_MODEL_ID,
        "region": region,
        "output": str(output_path),
        "bytes": len(image_bytes),
        "prompt": prompt,
    }


def aws_identity(dripr_env: dict[str, str], overrides: dict[str, str]) -> dict[str, Any]:
    return aws_runtime_status(dripr_env, overrides)


def prod_publish_status(prod_env: dict[str, str]) -> dict[str, Any]:
    missing = required_env_keys(prod_env, list(PROD_ENV_KEYS))
    entry: dict[str, Any] = {
        "credential_source": "env/prod.env",
        "ready": not missing,
        "issues": [f"missing keys: {', '.join(missing)}"] if missing else [],
    }
    if not missing:
        entry["database"] = mysql_connection_config_from_dripr_env(prod_env)["database"]
        entry["api_base_url"] = env_value("VITE_API_GATEWAY_URL", "", prod_env).rstrip("/")
    return entry


def check_config(overrides: dict[str, str]) -> dict[str, Any]:
    repo = dripr_repo(overrides)
    skill_file = repo / ".agent" / "skills" / "uploading-education-topics" / "SKILL.md"
    issues: list[str] = []

    if not repo.exists():
        issues.append(f"Dripr repo missing: {repo}")
    elif not (repo / ".git").exists():
        issues.append(f"Dripr path is not a git checkout: {repo}")
    if repo.exists() and not skill_file.exists():
        issues.append(f"education topics skill missing: {skill_file}")

    prod_env: dict[str, str] = {}
    publish_config: dict[str, Any] = {}
    if repo.exists():
        try:
            prod_env = load_dripr_env_file(repo, PROD_ENV_NAME)
            publish_config = prod_publish_status(prod_env)
            if not publish_config.get("ready"):
                issues.append(
                    f"prod publish config not ready: {'; '.join(publish_config.get('issues', []))}"
                )
        except SetupError as error:
            issues.append(str(error))

    mysql_ok = bool(prod_env)
    mysql_database = None
    if prod_env:
        try:
            mysql_database = mysql_connection_config_from_dripr_env(prod_env)["database"]
        except Exception:
            mysql_ok = False
            issues.append("prod.env DATABASE_URL is unavailable or invalid for recent-topics queries")

    aws = aws_runtime_status(prod_env, overrides) if prod_env else {
        "available": False,
        "region": DEFAULT_BEDROCK_REGION,
        "bedrock_runtime_available": False,
    }
    if prod_env and not aws.get("bedrock_runtime_available"):
        issues.append(aws.get("output") or "bedrock-runtime client is unavailable for image generation")

    return {
        "status": "OK" if not issues else "NEEDS_ATTENTION",
        "issues": issues,
        "repo_path": str(repo),
        "skill_path": str(skill_file),
        "draft_root": str(run_root(overrides)),
        "credential_source": "Dripr env/prod.env only",
        "publish": publish_config,
        "mysql_config_present": mysql_ok,
        "mysql_database": mysql_database,
        "aws": aws,
    }


def sync_repo(overrides: dict[str, str]) -> dict[str, Any]:
    repo = dripr_repo(overrides)
    if not repo.exists() or not (repo / ".git").exists():
        raise SetupError(f"Dripr repo checkout missing: {repo}")
    completed = subprocess.run(
        ["git", "pull", "--ff-only"],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=300,
        check=False,
    )
    if completed.returncode != 0:
        raise SetupError(f"git pull --ff-only failed in {repo}\n{completed.stdout}")
    head = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
        check=False,
    )
    return {
        "status": "OK",
        "repo_path": str(repo),
        "commit": head.stdout.strip() if head.returncode == 0 else None,
        "output": compact(completed.stdout, 240),
    }


def check_next_month(overrides: dict[str, str], args: argparse.Namespace) -> dict[str, Any] | None:
    current = now_et(args.now)
    if not is_monthly_trigger_day(current):
        return None

    target_month, target_year = next_calendar_month(current)
    repo = dripr_repo(overrides)
    prod_env = load_dripr_env_file(repo, PROD_ENV_NAME)
    rows = run_mysql_query_for_dripr_env(
        prod_env,
        VERIFY_TOPIC_SQL,
        (target_month, target_year),
        max_rows=1,
    )
    topic_exists = bool(rows)
    result: dict[str, Any] = {
        "status": "OK",
        "trigger_day": True,
        "target_month": target_month,
        "target_year": target_year,
        "target_label": month_year_label(target_month, target_year),
        "topic_exists": topic_exists,
    }
    if topic_exists:
        row = rows[0]
        result["topic"] = {
            "month": row.get("month"),
            "year": row.get("year"),
            "title": compact(row.get("title")),
            "image_url": compact(row.get("image_url")),
        }
    return result


def copy_topic_to_staging(overrides: dict[str, str], args: argparse.Namespace) -> dict[str, Any]:
    validate_month_year(args.month, args.year)
    repo = dripr_repo(overrides)
    prod_env = load_dripr_env_file(repo, PROD_ENV_NAME)
    staging_env = load_dripr_env_file(repo, STAGING_ENV_NAME)

    prod_rows = run_mysql_query_for_dripr_env(
        prod_env,
        FETCH_TOPIC_SQL,
        (args.month, args.year),
        max_rows=1,
    )
    if not prod_rows:
        raise SetupError(
            f"no production education topic found for {month_year_label(args.month, args.year)}"
        )

    staging_rows = run_mysql_query_for_dripr_env(
        staging_env,
        VERIFY_TOPIC_SQL,
        (args.month, args.year),
        max_rows=1,
    )
    if staging_rows:
        row = staging_rows[0]
        return {
            "status": "OK",
            "action": "already_exists",
            "target_label": month_year_label(args.month, args.year),
            "month": args.month,
            "year": args.year,
            "staging_database": mysql_connection_config_from_dripr_env(staging_env)["database"],
            "topic": {
                "title": compact(row.get("title")),
                "image_url": compact(row.get("image_url")),
            },
        }

    prod_row = prod_rows[0]
    title, content = validate_topic_text(
        str(prod_row.get("title") or ""),
        str(prod_row.get("content") or ""),
    )
    image_url = str(prod_row.get("image_url") or "").strip()
    if not image_url:
        raise SetupError("production topic is missing image_url")

    staging_config = mysql_connection_config_from_dripr_env(staging_env)
    new_row = {
        "id": str(uuid.uuid4()),
        "creation_datetime": datetime.now(timezone.utc).replace(tzinfo=None),
        "month": args.month,
        "year": args.year,
        "title": title,
        "content": content,
        "image_url": image_url,
    }
    insert_education_topic_row(staging_config, new_row)

    verify_rows = run_mysql_query_for_config(
        staging_config,
        FETCH_TOPIC_SQL,
        (args.month, args.year),
        max_rows=1,
    )
    return {
        "status": "OK",
        "action": "copied",
        "target_label": month_year_label(args.month, args.year),
        "month": args.month,
        "year": args.year,
        "staging_database": staging_config["database"],
        "source_database": mysql_connection_config_from_dripr_env(prod_env)["database"],
        "topic": {
            "title": title,
            "image_url": compact(image_url),
            "content_preview": compact(content, 160),
        },
        "verification": verify_rows,
        "note": "image_url still points at the production S3 object by design",
    }


def recent_topics(overrides: dict[str, str]) -> dict[str, Any]:
    repo = dripr_repo(overrides)
    prod_env = load_dripr_env_file(repo, PROD_ENV_NAME)
    rows = run_mysql_query_for_dripr_env(prod_env, RECENT_TOPICS_SQL, max_rows=100)
    return {
        "status": "OK",
        "database": mysql_connection_config_from_dripr_env(prod_env)["database"],
        "row_count": len(rows),
        "topics": [
            {
                "month": row.get("month"),
                "year": row.get("year"),
                "title": compact(row.get("title")),
                "content_preview": compact(row.get("content"), 160),
                "image_url": compact(row.get("image_url")),
            }
            for row in rows
        ],
    }


def validate_topic_payload(args: argparse.Namespace) -> tuple[str, str, Path]:
    image_path = Path(args.image)
    if not image_path.is_file():
        raise SetupError(f"image file not found: {image_path}")
    if image_path.suffix.lower() != ".png":
        raise SetupError("image must be a .png file")

    title = args.title.strip()
    content = args.content.strip()
    title, content = validate_topic_text(title, content)
    return title, content, image_path


def parse_curl_response(stdout: str) -> tuple[int, dict[str, Any] | None, str]:
    marker = "\nHTTP_STATUS:"
    if marker not in stdout:
        raise SetupError(f"publish command did not return HTTP status\n{stdout}")
    body, status_text = stdout.rsplit(marker, 1)
    body = body.strip()
    try:
        status_code = int(status_text.strip())
    except ValueError as error:
        raise SetupError(f"invalid HTTP status from publish command: {status_text}") from error
    if not body:
        return status_code, None, ""
    try:
        return status_code, json.loads(body), body
    except json.JSONDecodeError:
        return status_code, None, body


def publish_topic(overrides: dict[str, str], args: argparse.Namespace) -> dict[str, Any]:
    if not args.kenny_approved:
        raise SetupError("publish requires --kenny-approved after Kenny explicitly approves")

    repo = dripr_repo(overrides)
    title, content, image_path = validate_topic_payload(args)
    prod_env = load_dripr_env_file(repo, PROD_ENV_NAME)
    missing = required_env_keys(prod_env, list(PROD_ENV_KEYS))
    if missing:
        raise SetupError(f"prod.env missing keys: {', '.join(missing)}")

    api_key = env_value("DRIPR_API_KEY", "", prod_env)
    api_base = env_value("VITE_API_GATEWAY_URL", "", prod_env).rstrip("/")
    if not api_base:
        raise SetupError("VITE_API_GATEWAY_URL missing from prod.env")

    completed = subprocess.run(
        [
            "curl",
            "-sS",
            "-w",
            "\nHTTP_STATUS:%{http_code}",
            "-X",
            "POST",
            f"{api_base}/api/education-topics",
            "-H",
            f"X-Api-Key: {api_key}",
            "-F",
            f"month={args.month}",
            "-F",
            f"year={args.year}",
            "-F",
            f"title={title}",
            "-F",
            f"content={content}",
            "-F",
            f"image=@{image_path}",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=120,
        check=False,
    )
    if completed.returncode != 0:
        raise SetupError(f"curl publish failed\n{completed.stdout}")

    status_code, response_json, raw_body = parse_curl_response(completed.stdout)
    if status_code != 201:
        error_detail = response_json.get("error") if isinstance(response_json, dict) else raw_body
        raise SetupError(f"publish failed with HTTP {status_code}: {compact(error_detail, 240)}")

    mysql_config = mysql_connection_config_from_dripr_env(prod_env)
    verify_rows = run_mysql_query_for_config(mysql_config, VERIFY_TOPIC_SQL, (args.month, args.year), max_rows=5)
    return {
        "status": "OK",
        "target": "prod",
        "http_status": status_code,
        "api_response": response_json,
        "database": mysql_config["database"],
        "month": args.month,
        "year": args.year,
        "title": title,
        "verification": verify_rows,
    }


def main() -> int:
    args = parse_args()
    overrides = load_override_values(Path(args.env_file))
    try:
        if args.command == "check-config":
            result = check_config(overrides)
        elif args.command == "sync-repo":
            result = sync_repo(overrides)
        elif args.command == "check-next-month":
            outcome = check_next_month(overrides, args)
            if outcome is None:
                print("NO_REPLY")
                return 0
            result = outcome
        elif args.command == "recent-topics":
            result = recent_topics(overrides)
        elif args.command == "generate-image":
            result = generate_topic_image(overrides, args)
        elif args.command == "publish":
            result = publish_topic(overrides, args)
        elif args.command == "copy-to-staging":
            result = copy_topic_to_staging(overrides, args)
        else:
            raise SetupError(f"unknown command: {args.command}")
    except SetupError as error:
        result = {"status": "SETUP_REQUIRED", "reason": compact_error(error)}
    except Exception as error:
        result = {"status": "ERROR", "reason": compact_error(error)}
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result.get("status") == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
