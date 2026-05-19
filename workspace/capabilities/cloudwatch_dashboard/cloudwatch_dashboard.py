#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import time
from typing import Any
from zoneinfo import ZoneInfo

try:
    import boto3
except ImportError:  # pragma: no cover - depends on live OpenClaw image
    boto3 = None

try:
    from botocore.exceptions import BotoCoreError, ClientError
except ImportError:  # pragma: no cover - depends on live OpenClaw image
    BotoCoreError = ClientError = Exception


ET = ZoneInfo("America/New_York")
WORKSPACE_ROOT = Path(os.environ.get("OPENCLAW_WORKSPACE_DIR", "/home/node/.openclaw/workspace"))
OPENCLAW_ROOT = WORKSPACE_ROOT.parent
DEFAULT_ENV_FILE = OPENCLAW_ROOT / "secrets" / "cloudwatch-dashboard.env"
DEFAULT_CHECKS_FILE = OPENCLAW_ROOT / "secrets" / "cloudwatch-dashboard-checks.json"
DEFAULT_DASHBOARD_NAME = "dripr-daily"
DEFAULT_REGION = "us-east-1"
DEFAULT_LOOKBACK_HOURS = 24
DEFAULT_PERIOD_SECONDS = 300
MAX_ISSUES = 20
MAX_ERROR_CHARS = 260
MAX_TEXT_CHARS = 220
LOG_QUERY_TIMEOUT_SECONDS = 45
COMPARATORS = {">", ">=", "<", "<=", "==", "!="}


class SetupError(RuntimeError):
    pass


@dataclass
class MetricRef:
    namespace: str
    metric_name: str
    dimensions: dict[str, str]
    stat: str
    period: int
    label: str | None
    widget_title: str | None


@dataclass
class LogWidgetRef:
    title: str | None
    query: str
    region: str | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check CloudWatch dashboard metrics for attention-worthy issues.")
    parser.add_argument("--env-file", default=os.environ.get("CLOUDWATCH_DASHBOARD_ENV", str(DEFAULT_ENV_FILE)))
    parser.add_argument("--now", help="Override current time for tests (ISO-8601).")
    parser.add_argument("--json", action="store_true", help="Print explicit JSON NO_REPLY payloads.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("review", help="Fetch CloudWatch metrics and return compact issue context.")
    subparsers.add_parser("check-config", help="Validate configuration without querying metric data.")
    return parser.parse_args()


def compact(value: Any, max_chars: int = MAX_TEXT_CHARS) -> str | int | float | bool | None:
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
    values: dict[str, str] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            parsed = parse_env_line(line)
            if parsed:
                key, value = parsed
                values[key] = value
    return values


def env_value(values: dict[str, str], key: str, default: str | None = None) -> str | None:
    return os.environ.get(key) or values.get(key) or default


def positive_int(value: str | None, default: int, max_value: int) -> int:
    try:
        parsed = int(value or default)
    except ValueError:
        return default
    return max(1, min(parsed, max_value))


def load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SetupError(f"missing checks file: {path}")
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise SetupError(f"invalid checks JSON: {compact_error(error)}") from error
    if not isinstance(data, dict):
        raise SetupError("checks file must contain a JSON object")
    return data


def load_checks(values: dict[str, str]) -> list[dict[str, Any]]:
    raw_json = env_value(values, "CLOUDWATCH_DASHBOARD_CHECKS_JSON")
    if raw_json:
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as error:
            raise SetupError(f"invalid CLOUDWATCH_DASHBOARD_CHECKS_JSON: {compact_error(error)}") from error
    else:
        checks_file = Path(env_value(values, "CLOUDWATCH_DASHBOARD_CHECKS_FILE", str(DEFAULT_CHECKS_FILE)) or "")
        data = load_json_file(checks_file)
    checks = data.get("checks")
    if not isinstance(checks, list) or not checks:
        raise SetupError("checks file must define a non-empty checks array")
    return [validate_check(check, index) for index, check in enumerate(checks)]


def validate_check(check: Any, index: int) -> dict[str, Any]:
    if not isinstance(check, dict):
        raise SetupError(f"check {index + 1} must be an object")
    name = str(check.get("name") or f"check {index + 1}").strip()
    check_type = str(check.get("type") or "metric").strip()
    if check_type not in {"metric", "logs"}:
        raise SetupError(f"{name}: type must be metric or logs")
    operator = str(check.get("operator") or check.get("comparison") or "").strip()
    if operator not in COMPARATORS:
        raise SetupError(f"{name}: operator must be one of {', '.join(sorted(COMPARATORS))}")
    if "threshold" not in check:
        raise SetupError(f"{name}: missing threshold")
    try:
        threshold = float(check["threshold"])
    except (TypeError, ValueError) as error:
        raise SetupError(f"{name}: threshold must be numeric") from error
    treat_missing = str(check.get("treatMissingData") or "notBreaching").strip()
    if treat_missing not in {"breaching", "notBreaching", "ignore"}:
        raise SetupError(f"{name}: treatMissingData must be breaching, notBreaching, or ignore")
    if (
        check_type == "logs"
        and not check.get("logGroupName")
        and not check.get("logGroupNames")
        and not check.get("widgetTitle")
        and not check.get("query")
    ):
        raise SetupError(f"{name}: logs checks need widgetTitle, query, logGroupName, or logGroupNames")
    validated = dict(check)
    validated["name"] = name
    validated["type"] = check_type
    validated["operator"] = operator
    validated["threshold"] = threshold
    validated["treatMissingData"] = treat_missing
    return validated


def configure_aws_env(values: dict[str, str]) -> None:
    for key, value in values.items():
        if key.startswith("AWS_") and key not in os.environ:
            os.environ[key] = value


def cloudwatch_client(values: dict[str, str]):
    if boto3 is None:
        raise SetupError("missing Python AWS driver: install python3-boto3 or boto3")
    configure_aws_env(values)
    region = env_value(values, "CLOUDWATCH_REGION", DEFAULT_REGION)
    profile = env_value(values, "AWS_PROFILE")
    if profile:
        session = boto3.Session(profile_name=profile, region_name=region)
    else:
        session = boto3.Session(region_name=region)
    return session.client("cloudwatch")


def logs_client(values: dict[str, str]):
    if boto3 is None:
        raise SetupError("missing Python AWS driver: install python3-boto3 or boto3")
    configure_aws_env(values)
    region = env_value(values, "CLOUDWATCH_REGION", DEFAULT_REGION)
    profile = env_value(values, "AWS_PROFILE")
    if profile:
        session = boto3.Session(profile_name=profile, region_name=region)
    else:
        session = boto3.Session(region_name=region)
    return session.client("logs")


def dashboard_name(values: dict[str, str]) -> str:
    return env_value(values, "CLOUDWATCH_DASHBOARD_NAME", DEFAULT_DASHBOARD_NAME) or DEFAULT_DASHBOARD_NAME


def get_dashboard_body(client: Any, name: str) -> dict[str, Any]:
    response = client.get_dashboard(DashboardName=name)
    try:
        body = json.loads(response["DashboardBody"])
    except (KeyError, json.JSONDecodeError) as error:
        raise SetupError("CloudWatch dashboard body was not valid JSON") from error
    if not isinstance(body, dict):
        raise SetupError("CloudWatch dashboard body must be a JSON object")
    return body


def normalized(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def expand_metric_entry(entry: list[Any], previous: list[Any] | None) -> list[Any]:
    expanded: list[Any] = []
    for index, value in enumerate(entry):
        if value == "..." and previous:
            remaining = len(entry) - index - 1
            prefix_len = max(0, len(previous) - remaining)
            expanded.extend(previous[:prefix_len])
            continue
        if value == "." and previous and index < len(previous):
            expanded.append(previous[index])
        else:
            expanded.append(value)
    return expanded


def metric_from_entry(entry: list[Any], widget_title: str | None, default_region: str | None) -> MetricRef | None:
    if not entry or isinstance(entry[0], dict):
        return None
    values = list(entry)
    options: dict[str, Any] = {}
    if values and isinstance(values[-1], dict):
        options = values.pop()
    if len(values) < 2:
        return None
    namespace = str(values[0])
    metric_name = str(values[1])
    dimensions: dict[str, str] = {}
    for index in range(2, len(values) - 1, 2):
        dimensions[str(values[index])] = str(values[index + 1])
    stat = str(options.get("stat") or options.get("statistic") or "Average")
    period = positive_int(str(options.get("period")) if options.get("period") else None, DEFAULT_PERIOD_SECONDS, 86400)
    label = str(options.get("label")).strip() if options.get("label") else None
    if default_region and options.get("region") and str(options["region"]) != default_region:
        return None
    return MetricRef(
        namespace=namespace,
        metric_name=metric_name,
        dimensions=dimensions,
        stat=stat,
        period=period,
        label=label,
        widget_title=widget_title,
    )


def dashboard_metrics(body: dict[str, Any], region: str | None) -> list[MetricRef]:
    widgets = body.get("widgets")
    if not isinstance(widgets, list):
        return []
    metrics: list[MetricRef] = []
    for widget in widgets:
        if not isinstance(widget, dict) or widget.get("type") != "metric":
            continue
        properties = widget.get("properties")
        if not isinstance(properties, dict):
            continue
        title = str(properties.get("title")).strip() if properties.get("title") else None
        default_stat = str(properties.get("stat") or "Average")
        default_period = positive_int(str(properties.get("period")) if properties.get("period") else None, DEFAULT_PERIOD_SECONDS, 86400)
        previous: list[Any] | None = None
        for entry in properties.get("metrics") or []:
            if not isinstance(entry, list):
                continue
            expanded = expand_metric_entry(entry, previous)
            previous = expanded
            metric = metric_from_entry(expanded, title, region)
            if metric:
                if metric.stat == "Average":
                    metric.stat = default_stat
                if metric.period == DEFAULT_PERIOD_SECONDS:
                    metric.period = default_period
                metrics.append(metric)
    return metrics


def dashboard_log_widgets(body: dict[str, Any], region: str | None) -> list[LogWidgetRef]:
    widgets = body.get("widgets")
    if not isinstance(widgets, list):
        return []
    log_widgets: list[LogWidgetRef] = []
    for widget in widgets:
        if not isinstance(widget, dict) or widget.get("type") != "log":
            continue
        properties = widget.get("properties")
        if not isinstance(properties, dict):
            continue
        widget_region = str(properties.get("region")).strip() if properties.get("region") else None
        if region and widget_region and widget_region != region:
            continue
        query = str(properties.get("query") or "").strip()
        if not query:
            continue
        title = str(properties.get("title")).strip() if properties.get("title") else None
        log_widgets.append(LogWidgetRef(title=title, query=query, region=widget_region))
    return log_widgets


def explicit_metric(check: dict[str, Any], default_period: int) -> MetricRef | None:
    raw = check.get("metric")
    if not isinstance(raw, dict):
        return None
    namespace = raw.get("namespace")
    metric_name = raw.get("metricName") or raw.get("name")
    if not namespace or not metric_name:
        raise SetupError(f"{check['name']}: explicit metric needs namespace and metricName")
    dimensions_raw = raw.get("dimensions") or {}
    if not isinstance(dimensions_raw, dict):
        raise SetupError(f"{check['name']}: metric dimensions must be an object")
    return MetricRef(
        namespace=str(namespace),
        metric_name=str(metric_name),
        dimensions={str(key): str(value) for key, value in dimensions_raw.items()},
        stat=str(raw.get("stat") or check.get("stat") or "Average"),
        period=positive_int(str(raw.get("period")) if raw.get("period") else None, default_period, 86400),
        label=str(raw.get("label")).strip() if raw.get("label") else None,
        widget_title=None,
    )


def metric_matches(check: dict[str, Any], metric: MetricRef) -> bool:
    widget_title = check.get("widgetTitle") or check.get("widget_title")
    if widget_title and normalized(widget_title) not in normalized(metric.widget_title):
        return False
    label = check.get("label") or check.get("metricLabel") or check.get("metric_label")
    if label and normalized(label) not in normalized(metric.label or metric.metric_name):
        return False
    namespace = check.get("namespace")
    if namespace and str(namespace) != metric.namespace:
        return False
    metric_name = check.get("metricName") or check.get("metric_name")
    if metric_name and str(metric_name) != metric.metric_name:
        return False
    dimensions = check.get("dimensions")
    if isinstance(dimensions, dict):
        for key, value in dimensions.items():
            if metric.dimensions.get(str(key)) != str(value):
                return False
    return True


def find_metric(check: dict[str, Any], metrics: list[MetricRef], default_period: int) -> MetricRef:
    metric = explicit_metric(check, default_period)
    if metric:
        return metric
    matches = [metric for metric in metrics if metric_matches(check, metric)]
    metric_index = check.get("metricIndex") if "metricIndex" in check else check.get("metric_index")
    if metric_index is not None:
        try:
            index = int(metric_index)
        except (TypeError, ValueError) as error:
            raise SetupError(f"{check['name']}: metricIndex must be an integer") from error
        if index < 0 or index >= len(matches):
            raise SetupError(f"{check['name']}: metricIndex {index} did not match a dashboard metric")
        return matches[index]
    if len(matches) != 1:
        raise SetupError(f"{check['name']}: matched {len(matches)} dashboard metrics; refine widgetTitle/label/metricName/dimensions")
    return matches[0]


def query_metric(client: Any, metric: MetricRef, start_utc: datetime, end_utc: datetime) -> dict[str, Any]:
    response = client.get_metric_statistics(
        Namespace=metric.namespace,
        MetricName=metric.metric_name,
        Dimensions=[{"Name": key, "Value": value} for key, value in sorted(metric.dimensions.items())],
        StartTime=start_utc,
        EndTime=end_utc,
        Period=metric.period,
        Statistics=[metric.stat],
    )
    datapoints = sorted(response.get("Datapoints", []), key=lambda item: item.get("Timestamp", datetime.min.replace(tzinfo=timezone.utc)))
    values = [point.get(metric.stat) for point in datapoints if isinstance(point.get(metric.stat), (int, float))]
    latest_point = datapoints[-1] if datapoints else None
    latest_value = latest_point.get(metric.stat) if latest_point else None
    max_value = max(values) if values else None
    min_value = min(values) if values else None
    avg_value = sum(values) / len(values) if values else None
    return {
        "latest": latest_value,
        "max": max_value,
        "min": min_value,
        "avg": avg_value,
        "datapoints": len(values),
        "latestTimestamp": latest_point.get("Timestamp") if latest_point else None,
    }


def selected_value(check: dict[str, Any], stats: dict[str, Any]) -> float | None:
    value_key = str(check.get("value") or check.get("valueKey") or "latest")
    value = stats.get(value_key)
    if value is None:
        return None
    if not isinstance(value, (int, float)):
        raise SetupError(f"{check['name']}: selected value {value_key} was not numeric")
    return float(value)


def is_breaching(value: float, operator: str, threshold: float) -> bool:
    if operator == ">":
        return value > threshold
    if operator == ">=":
        return value >= threshold
    if operator == "<":
        return value < threshold
    if operator == "<=":
        return value <= threshold
    if operator == "==":
        return value == threshold
    if operator == "!=":
        return value != threshold
    raise SetupError(f"unsupported operator: {operator}")


def issue_for_missing(check: dict[str, Any], metric: MetricRef) -> dict[str, Any] | None:
    if check["treatMissingData"] == "ignore" or check["treatMissingData"] == "notBreaching":
        return None
    return {
        "name": check["name"],
        "severity": check.get("severity", "warning"),
        "reason": "missing data",
        "metric": metric.label or metric.metric_name,
        "widget": metric.widget_title,
        "namespace": metric.namespace,
        "description": check.get("description"),
    }


def issue_for_breach(check: dict[str, Any], metric: MetricRef, stats: dict[str, Any], value: float) -> dict[str, Any]:
    return {
        "name": check["name"],
        "severity": check.get("severity", "warning"),
        "reason": "threshold breached",
        "metric": metric.label or metric.metric_name,
        "widget": metric.widget_title,
        "namespace": metric.namespace,
        "value": round(value, 4),
        "value_key": check.get("value") or check.get("valueKey") or "latest",
        "operator": check["operator"],
        "threshold": check["threshold"],
        "datapoints": stats.get("datapoints"),
        "latest_timestamp": stats.get("latestTimestamp"),
        "description": check.get("description"),
        "suggested_action": check.get("suggestedAction") or check.get("suggested_action"),
    }


def log_group_names(check: dict[str, Any]) -> list[str]:
    raw_names = check.get("logGroupNames")
    if isinstance(raw_names, list):
        names = [str(name).strip() for name in raw_names if str(name).strip()]
    else:
        names = []
    single = str(check.get("logGroupName") or "").strip()
    if single:
        names.append(single)
    if not names:
        raise SetupError(f"{check['name']}: logs checks need logGroupName or logGroupNames")
    return names


def find_log_widget(check: dict[str, Any], log_widgets: list[LogWidgetRef]) -> LogWidgetRef:
    query = str(check.get("query") or "").strip()
    if query:
        return LogWidgetRef(title=str(check.get("widgetTitle") or check["name"]), query=query, region=None)
    widget_title = check.get("widgetTitle") or check.get("widget_title")
    if not widget_title:
        raise SetupError(f"{check['name']}: logs checks need widgetTitle or query")
    matches = [widget for widget in log_widgets if normalized(widget_title) in normalized(widget.title)]
    if len(matches) != 1:
        raise SetupError(f"{check['name']}: matched {len(matches)} log widgets; refine widgetTitle")
    return matches[0]


def split_logs_insights_query(query: str) -> tuple[list[str] | None, str]:
    source_re = re.compile(r'^\s*SOURCE\s+((?:"[^"]+"\s*,?\s*)+)\|?', re.IGNORECASE)
    match = source_re.match(query)
    if not match:
        return None, query
    log_groups = re.findall(r'"([^"]+)"', match.group(1))
    remaining = query[match.end() :].lstrip()
    if remaining.startswith("|"):
        remaining = remaining[1:].lstrip()
    if not remaining:
        raise SetupError("Logs Insights dashboard query had SOURCE but no query body")
    return log_groups, remaining


def query_logs_insights(client: Any, check: dict[str, Any], widget: LogWidgetRef, start_utc: datetime, end_utc: datetime) -> dict[str, Any]:
    log_groups, query_string = split_logs_insights_query(widget.query)
    kwargs = {
        "startTime": int(start_utc.timestamp()),
        "endTime": int(end_utc.timestamp()),
        "queryString": query_string,
    }
    if log_groups:
        kwargs["logGroupNames"] = log_groups
    response = client.start_query(**kwargs)
    query_id = response["queryId"]
    deadline = time.monotonic() + LOG_QUERY_TIMEOUT_SECONDS
    result: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        result = client.get_query_results(queryId=query_id)
        status = result.get("status")
        if status in {"Complete", "Failed", "Cancelled", "Timeout", "Unknown"}:
            break
        time.sleep(1)
    if result is None:
        raise RuntimeError("Logs Insights query did not return a result")
    if result.get("status") != "Complete":
        raise RuntimeError(f"Logs Insights query ended with status {result.get('status')}")
    rows = result.get("results") or []
    first_seen: str | None = None
    last_seen: str | None = None
    for row in rows:
        if not isinstance(row, list):
            continue
        values = {field.get("field"): field.get("value") for field in row if isinstance(field, dict)}
        timestamp = values.get("@timestamp")
        if timestamp:
            first_seen = timestamp if first_seen is None else min(first_seen, timestamp)
            last_seen = timestamp if last_seen is None else max(last_seen, timestamp)
    return {
        "count": len(rows),
        "first_seen": first_seen,
        "last_seen": last_seen,
        "query_status": result.get("status"),
        "widget": widget.title,
        "log_groups": ", ".join(log_groups) if log_groups else None,
        "truncated": len(rows) >= positive_int(str(check.get("maxEvents")) if check.get("maxEvents") else None, 100, 10000),
    }


def query_logs_filter(client: Any, check: dict[str, Any], start_utc: datetime, end_utc: datetime) -> dict[str, Any]:
    filter_pattern = str(check.get("filterPattern") or '"ERROR"')
    max_events = positive_int(str(check.get("maxEvents")) if check.get("maxEvents") else None, 1000, 10000)
    start_ms = int(start_utc.timestamp() * 1000)
    end_ms = int(end_utc.timestamp() * 1000)
    count = 0
    first_seen_ms: int | None = None
    last_seen_ms: int | None = None
    streams: set[str] = set()
    truncated = False
    paginator = client.get_paginator("filter_log_events")
    for group_name in log_group_names(check):
        for page in paginator.paginate(
            logGroupName=group_name,
            startTime=start_ms,
            endTime=end_ms,
            filterPattern=filter_pattern,
        ):
            events = page.get("events", [])
            for event in events:
                timestamp = event.get("timestamp")
                if isinstance(timestamp, int):
                    first_seen_ms = timestamp if first_seen_ms is None else min(first_seen_ms, timestamp)
                    last_seen_ms = timestamp if last_seen_ms is None else max(last_seen_ms, timestamp)
                if event.get("logStreamName"):
                    streams.add(str(event["logStreamName"]))
                count += 1
                if count >= max_events:
                    truncated = True
                    break
            if truncated:
                break
        if truncated:
            break
    return {
        "count": count,
        "first_seen": datetime.fromtimestamp(first_seen_ms / 1000, timezone.utc) if first_seen_ms is not None else None,
        "last_seen": datetime.fromtimestamp(last_seen_ms / 1000, timezone.utc) if last_seen_ms is not None else None,
        "streams": len(streams),
        "truncated": truncated,
    }


def query_logs(client: Any, check: dict[str, Any], log_widgets: list[LogWidgetRef], start_utc: datetime, end_utc: datetime) -> dict[str, Any]:
    if check.get("widgetTitle") or check.get("query"):
        return query_logs_insights(client, check, find_log_widget(check, log_widgets), start_utc, end_utc)
    return query_logs_filter(client, check, start_utc, end_utc)


def issue_for_log_breach(check: dict[str, Any], stats: dict[str, Any], value: float) -> dict[str, Any]:
    return {
        "name": check["name"],
        "severity": check.get("severity", "warning"),
        "reason": "log filter matched",
        "widget": stats.get("widget") or check.get("widgetTitle"),
        "log_groups": stats.get("log_groups") or (", ".join(log_group_names(check)) if check.get("logGroupName") or check.get("logGroupNames") else None),
        "filter_pattern": check.get("filterPattern") or ("dashboard query" if check.get("widgetTitle") or check.get("query") else '"ERROR"'),
        "value": int(value),
        "value_key": "count",
        "operator": check["operator"],
        "threshold": check["threshold"],
        "first_seen": stats.get("first_seen"),
        "last_seen": stats.get("last_seen"),
        "streams": stats.get("streams"),
        "truncated": stats.get("truncated"),
        "description": check.get("description"),
        "suggested_action": check.get("suggestedAction") or check.get("suggested_action"),
    }


def setup_required(reason: str) -> dict[str, Any]:
    return {"status": "SETUP_REQUIRED", "reason": reason}


def review(args: argparse.Namespace) -> dict[str, Any] | str:
    values = load_env(Path(args.env_file))
    checks = load_checks(values)
    current_et = now_et(args.now)
    lookback_hours = positive_int(env_value(values, "CLOUDWATCH_LOOKBACK_HOURS"), DEFAULT_LOOKBACK_HOURS, 168)
    default_period = positive_int(env_value(values, "CLOUDWATCH_PERIOD_SECONDS"), DEFAULT_PERIOD_SECONDS, 86400)
    region = env_value(values, "CLOUDWATCH_REGION", DEFAULT_REGION)
    start_utc = (current_et - timedelta(hours=lookback_hours)).astimezone(timezone.utc)
    end_utc = current_et.astimezone(timezone.utc)
    issues: list[dict[str, Any]] = []
    log_checks = [check for check in checks if check["type"] == "logs"]
    cloudwatch = cloudwatch_client(values)
    logs = logs_client(values) if log_checks else None
    body = get_dashboard_body(cloudwatch, dashboard_name(values))
    metrics = dashboard_metrics(body, region)
    log_widgets = dashboard_log_widgets(body, region)
    for check in checks:
        if check["type"] == "logs":
            stats = query_logs(logs, check, log_widgets, start_utc, end_utc)
            value = float(stats["count"])
            if is_breaching(value, check["operator"], check["threshold"]):
                issues.append(issue_for_log_breach(check, stats, value))
            continue
        metric = find_metric(check, metrics, default_period)
        stats = query_metric(cloudwatch, metric, start_utc, end_utc)
        value = selected_value(check, stats)
        if value is None:
            missing_issue = issue_for_missing(check, metric)
            if missing_issue:
                issues.append(missing_issue)
            continue
        if is_breaching(value, check["operator"], check["threshold"]):
            issues.append(issue_for_breach(check, metric, stats, value))
    if not issues:
        return {"status": "NO_REPLY"} if args.json else "NO_REPLY"
    return {
        "status": "OK",
        "dashboard": dashboard_name(values),
        "region": region,
        "checked_at_et": current_et.isoformat(timespec="seconds"),
        "window_hours": lookback_hours,
        "issue_count": len(issues),
        "truncated": len(issues) > MAX_ISSUES,
        "issues": [{key: compact(value) for key, value in issue.items() if value is not None} for issue in issues[:MAX_ISSUES]],
    }


def main() -> int:
    args = parse_args()
    try:
        if args.command == "check-config":
            values = load_env(Path(args.env_file))
            load_checks(values)
            if boto3 is None:
                raise SetupError("missing Python AWS driver: install python3-boto3 or boto3")
            print(json.dumps({"status": "OK"}, sort_keys=True))
            return 0
        result = review(args)
    except SetupError as error:
        result = setup_required(compact_error(error))
    except (BotoCoreError, ClientError) as error:
        result = {"status": "ERROR", "reason": compact_error(error)}
    except Exception as error:
        result = {"status": "ERROR", "reason": compact_error(error)}

    if isinstance(result, str):
        print(result)
    else:
        print(json.dumps(result, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
