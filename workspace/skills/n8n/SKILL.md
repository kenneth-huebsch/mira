---
name: n8n
description: Manage Kenny's n8n workflows with the workspace-local Python helpers. Use when Kenny asks to list, inspect, debug, validate, optimize, create, update, activate, deactivate, or troubleshoot n8n workflows.
metadata: {"openclaw":{"emoji":"⚙️","requires":{"env":["N8N_API_KEY","N8N_BASE_URL"]},"primaryEnv":"N8N_API_KEY"}}
---

# n8n Workflow Management

Use this skill when Kenny asks about n8n workflows, executions, automation
debugging, validation, optimization, workflow changes, or the production n8n
infrastructure.

Mira uses the skill-plus-helper pattern for n8n. Do not assume a plugin tool
exists. Read this skill, then run the Python helpers from this directory with
the OpenClaw `exec` tool.

## Runtime

Inside Mira's gateway container, the skill lives at:

```bash
/home/node/.openclaw/workspace/skills/n8n
```

The helper scripts are:

```bash
python3 /home/node/.openclaw/workspace/skills/n8n/scripts/n8n_api.py
python3 /home/node/.openclaw/workspace/skills/n8n/scripts/n8n_context.py
python3 /home/node/.openclaw/workspace/skills/n8n/scripts/n8n_tester.py
python3 /home/node/.openclaw/workspace/skills/n8n/scripts/n8n_optimizer.py
```

`N8N_API_KEY` and `N8N_BASE_URL` are loaded into Mira's gateway environment from
ignored runtime secrets. Never print or reveal the values. If a command reports
they are missing, say that the n8n environment is unavailable in the current
runtime; do not tell Kenny to use a generic home-directory path.

## Response Rule

Do not send placeholder replies like "I'll pull that up" unless you are also
issuing the needed tool call in the same turn. For workflow lookups, run the
helper first, then answer with the result.

## First Steps

Kenny's n8n infrastructure context lives in the private repo
`https://github.com/kenneth-huebsch/n8n`. For any n8n request beyond a simple
workflow API lookup, refresh or check the runtime checkout first:

```bash
cd /home/node/.openclaw/workspace/skills/n8n
python3 scripts/n8n_context.py refresh-repo --pretty
python3 scripts/n8n_context.py reading-list
```

Then read the listed files from the runtime checkout, especially:

```bash
/home/node/.openclaw/workspace/runtime/repos/n8n/AGENTS.md
/home/node/.openclaw/workspace/runtime/repos/n8n/README.md
/home/node/.openclaw/workspace/runtime/repos/n8n/compose.yaml
/home/node/.openclaw/workspace/runtime/repos/n8n/.agents/skills/n8n-infrastructure/SKILL.md
```

Use the repo-local `n8n-infrastructure` skill for Lightsail, Caddy, Docker,
server deploys, backups, TLS, SSH, and production debugging. Use this local
skill's API helpers for n8n workflow and execution API operations.

## Read-Only Operations

These are safe to run when Kenny asks about current n8n state:

```bash
cd /home/node/.openclaw/workspace/skills/n8n
python3 scripts/n8n_context.py check-context --pretty
python3 scripts/n8n_api.py list-workflows --pretty
python3 scripts/n8n_api.py list-workflows --active true --pretty
python3 scripts/n8n_api.py get-workflow --id <workflow-id> --pretty
python3 scripts/n8n_api.py list-executions --limit 10 --pretty
python3 scripts/n8n_api.py list-executions --id <workflow-id> --limit 20 --pretty
python3 scripts/n8n_api.py get-execution --id <execution-id> --pretty
python3 scripts/n8n_api.py stats --id <workflow-id> --days 7 --pretty
python3 scripts/n8n_tester.py validate --id <workflow-id> --pretty
python3 scripts/n8n_optimizer.py analyze --id <workflow-id> --pretty
python3 scripts/n8n_optimizer.py suggest --id <workflow-id> --pretty
```

For Telegram replies, summarize compactly. Prefer workflow names, ids, active
state, recent failure/error signals, and the next useful debugging step.

## Mutating Operations Need Approval

These can change live n8n state or trigger connected systems. Get Kenny's
explicit approval immediately before running them:

```bash
python3 scripts/n8n_api.py create --from-file <workflow.json>
python3 scripts/n8n_api.py update --id <workflow-id> --from-file <workflow.json>
python3 scripts/n8n_api.py activate --id <workflow-id>
python3 scripts/n8n_api.py deactivate --id <workflow-id>
python3 scripts/n8n_api.py delete-workflow --id <workflow-id>
python3 scripts/n8n_api.py delete-execution --id <execution-id>
python3 scripts/n8n_api.py execute --id <workflow-id>
python3 scripts/n8n_api.py execute --id <workflow-id> --data '<json>'
python3 scripts/n8n_tester.py dry-run --id <workflow-id> --data '<json>'
```

Treat `dry-run` as potentially live: it may execute workflow nodes and call
external systems.

## Workflow Creation And Updates

When creating or updating workflows:

1. Inspect the existing workflow or requirements first.
2. Build complete, functional workflows with real n8n node types such as
   `n8n-nodes-base.httpRequest`, `n8n-nodes-base.code`, and
   `n8n-nodes-base.set`.
3. Do not create placeholder nodes, TODO-only workflows, or setup-instruction
   workflows.
4. Validate workflow JSON before asking Kenny to approve a live create/update.
5. Keep new workflows inactive unless Kenny explicitly asks to activate them.

## Debugging Flow

For a failed or suspicious workflow:

```bash
cd /home/node/.openclaw/workspace/skills/n8n
python3 scripts/n8n_api.py get-workflow --id <workflow-id> --pretty
python3 scripts/n8n_api.py list-executions --id <workflow-id> --limit 10 --pretty
python3 scripts/n8n_tester.py validate --id <workflow-id> --pretty
python3 scripts/n8n_optimizer.py report --id <workflow-id>
```

If execution details contain private payloads, summarize errors and node names
instead of pasting raw data.
