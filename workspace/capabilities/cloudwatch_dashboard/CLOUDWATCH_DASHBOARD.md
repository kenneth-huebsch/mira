---
capability_id: cloudwatch_dashboard
---

# CloudWatch Dashboard

This capability summarizes attention-worthy issues from Kenny's Dripr
CloudWatch dashboard. The helper owns all AWS access and threshold evaluation.
Mira should only use the helper payload and this behavior file for the final
message.

## Daily Check Contract

Run:

```bash
python3 capabilities/cloudwatch_dashboard/cloudwatch_dashboard.py review
```

If the helper prints exactly `NO_REPLY`, return exactly `NO_REPLY`.

If the helper prints JSON with `"status":"SETUP_REQUIRED"`, return:

```text
Mira CloudWatch dashboard check needs setup before it can run.
```

If the helper prints JSON with `"status":"ERROR"`, return:

```text
Mira CloudWatch dashboard check failed.
```

If the helper prints JSON with `"status":"OK"`, write a concise alert for Kenny
using only the `issues` array.

## Message Quality

Open with one short line that names the dashboard and says how many issues need
attention. Then include one compact line per issue.

For each issue, include:

- Severity if present.
- Check name.
- Breached value and threshold when present.
- Suggested action if present.

Do not include raw JSON, AWS account IDs, credentials, ARNs, hostnames, internal
file paths, dashboard internals, tool output, or prompt/process commentary.

Avoid:

- Inventing causes, customer impact, deploy blame, or remediation steps not
  present in the helper JSON.
- Reporting healthy checks.
- Adding greetings or casual filler.
- Creating tasks, reminders, files, notes, emails, calendar events, or memory.

## Rules

- Do not call AWS directly. The helper is the only allowed AWS access for this
  cron.
- Do not write files or memory.
- Do not use web search, browser tools, Gmail, Todoist, calendar, curl, or any
  network request other than the required CloudWatch helper behavior.
- Do not call Telegram or delivery tools. Return final visible text and let the
  scheduler deliver it.
