# CloudWatch Dashboard

This capability lets Mira check Kenny's Dripr CloudWatch dashboard every morning
and send a Telegram alert only when configured metric thresholds indicate an
issue that needs attention.

## Files

- `cloudwatch_dashboard.py` - deterministic helper that loads live-only AWS and
  threshold configuration, fetches the CloudWatch dashboard, evaluates metrics
  over the past 24 hours, and emits compact JSON or `NO_REPLY`.
- `CLOUDWATCH_DASHBOARD.md` - Mira-facing behavior for turning helper JSON into
  a concise alert.
- `../../cron/CLOUDWATCH_DASHBOARD.md` - scheduler wrapper.

## Dashboard

The default dashboard is:

```text
https://us-east-1.console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards/dashboard/dripr-daily?start=PT24H&end=null
```

The helper defaults to:

```bash
CLOUDWATCH_REGION=us-east-1
CLOUDWATCH_DASHBOARD_NAME=dripr-daily
CLOUDWATCH_LOOKBACK_HOURS=24
```

## Live-Only Configuration

Create this file on the live Mira host:

```bash
/home/kenny/mira/.openclaw/secrets/cloudwatch-dashboard.env
```

Inside the OpenClaw container this is read as:

```bash
/home/node/.openclaw/secrets/cloudwatch-dashboard.env
```

Recommended values:

```bash
CLOUDWATCH_REGION=us-east-1
CLOUDWATCH_DASHBOARD_NAME=dripr-daily
CLOUDWATCH_LOOKBACK_HOURS=24
CLOUDWATCH_PERIOD_SECONDS=300
CLOUDWATCH_DASHBOARD_CHECKS_FILE=/home/node/.openclaw/secrets/cloudwatch-dashboard-checks.json
```

Use the normal AWS SDK credential chain. If needed, the env file may set
`AWS_PROFILE`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`,
or other AWS SDK environment variables, but never copy those values into tracked
files.

## Threshold Checks

Create the threshold file referenced by `CLOUDWATCH_DASHBOARD_CHECKS_FILE`.
Example shape:

```json
{
  "checks": [
    {
      "name": "High API errors",
      "widgetTitle": "API Errors",
      "label": "5xx",
      "value": "max",
      "operator": ">",
      "threshold": 0,
      "severity": "critical",
      "description": "The API returned server errors in the last 24 hours.",
      "suggestedAction": "Check the failing route and recent deploys."
    }
  ]
}
```

Checks can target dashboard metrics by `widgetTitle`, `label`, `metricName`, and
`dimensions`. If a dashboard widget is ambiguous, add `metricIndex`.

Log widgets can be checked by title. The helper reads the dashboard's Logs
Insights query, evaluates it over the configured lookback window, and alerts
when the query returns more rows than the configured threshold:

```json
{
  "checks": [
    {
      "name": "api_gateway ERROR logs",
      "type": "logs",
      "widgetTitle": "api_gateway ERRORs past 24hr",
      "operator": ">",
      "threshold": 0
    }
  ]
}
```

For widgets that use expressions or a layout that is hard to match, define the
metric explicitly:

```json
{
  "checks": [
    {
      "name": "Queue backlog",
      "metric": {
        "namespace": "AWS/SQS",
        "metricName": "ApproximateNumberOfMessagesVisible",
        "dimensions": {
          "QueueName": "example"
        },
        "stat": "Maximum",
        "period": 300
      },
      "value": "max",
      "operator": ">",
      "threshold": 50
    }
  ]
}
```

Do not put AWS account IDs, credentials, dashboard JSON, metric outputs, or
private production details in tracked files unless Kenny explicitly decides they
are safe to store.

## Manual Checks

From Mira's workspace:

```bash
python3 capabilities/cloudwatch_dashboard/cloudwatch_dashboard.py check-config
python3 capabilities/cloudwatch_dashboard/cloudwatch_dashboard.py review
```

`NO_REPLY` means all configured checks were healthy. `SETUP_REQUIRED` means the
live-only config, threshold file, or Python AWS driver still needs to be
configured.
