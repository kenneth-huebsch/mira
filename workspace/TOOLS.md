# TOOLS.md

Canonical reference for Mira's tool conventions. This file is loaded into agent
runs, so put tool mechanics here instead of scattering command details across
prompts.

## OpenClaw Exec Runtime

Mira's OpenClaw `exec` tool runs inside the gateway container with workspace
paths rooted at `/home/node/.openclaw/workspace`.

Runtime dependencies belong in `openclaw/entrypoint.sh` so restored containers
prepare the same command surface. Live credentials and tokens remain under
`.openclaw` secrets/state and must not be copied into tracked files.

## Coding Harness

Mira routes non-Mira coding requests through Kenny's private agent harness. The
adapter is a thin router: it resolves/clones the target and rejects Mira
self-work, then delegates all execution to the harness runner
`scripts/agent_run.py`. The harness owns prompts, the green/red gate, handoffs,
the per-phase review-and-remediate loop, phased scheduling, and run records.

- Harness repo: `https://github.com/kenneth-huebsch/agent.git`
- Immutable revision and contract: `skills/coding-harness/harness.lock.json`
- Adapter/runner policy: `skills/coding-harness/policy.json`
- Host runtime checkout: `/home/kenny/mira/.openclaw/workspace/runtime/repos/agent`
- Container runtime checkout: `/home/node/.openclaw/workspace/runtime/repos/agent`
- Runner delegated to: `runtime/repos/agent/scripts/agent_run.py`
- Adapter: `python3 skills/coding-harness/coding_harness.py`
- Skill: `skills/coding-harness/SKILL.md`

Command surface:

```bash
python3 skills/coding-harness/coding_harness.py refresh-harness
python3 skills/coding-harness/coding_harness.py check-config
python3 skills/coding-harness/coding_harness.py run --target <path-or-repo> --prompt "<task>" [--mode plan] [--verification-json '<object>'|--verify "<legacy-shell-cmd>"] [--timeout <secs>] [--dry-run] [--no-review|--review-threshold {blocking,high,medium,low}|--review-max-rounds N] [--implement-model M|--plan-model M|--review-model M|--fix-model M]
python3 skills/coding-harness/coding_harness.py run-plan --target <path-or-repo> --plan runtime/coding-harness-plans/<name>.json [--dry-run] [...]
python3 skills/coding-harness/coding_harness.py resume <run-or-plan-id> [--restart-current-stage]
python3 skills/coding-harness/coding_harness.py cancel <run-or-plan-id> --reason "<reason>"
python3 skills/coding-harness/coding_harness.py list
python3 skills/coding-harness/coding_harness.py status <run-id>
python3 skills/coding-harness/coding_harness.py show <run-id>
```

- Larger work follows plan-then-approved-execution: plan interactively, author a
  phase-spec JSON under ignored runtime (`runtime/coding-harness-plans/<name>.json`),
  get explicit approval, then `run-plan`. Phase-specs and run records stay in
  runtime, never in the blueprint.
- The adapter sets `AGENT_RUN_HOME=runtime/coding-harness-runs` so run records
  land under Mira's ignored runtime, and forwards verification, policy,
  model, resume, cancellation, review, and timeout options. Phase specs remain
  under `runtime/coding-harness-plans`.
- `refresh-harness` materializes the tracked full SHA detached; it never switches
  to or pulls a branch. It verifies detached state even when the checkout was
  already at the pinned SHA. Target clones use `owner--repo`, validate origin,
  and are never auto-pulled. Fresh private clones use `gh auth git-credential`
  without placing a GitHub token in command arguments or the delegated
  environment.
- The runner timeout is 3000 seconds, cancellation cleanup gets 15 seconds, and
  OpenClaw's outer timeout is 3600 seconds. The adapter always forwards 3000
  when `run` or `run-plan` omits `--timeout`, preventing the pinned runner's
  older 3600 CLI default from overriding policy. Foreground signals are forwarded to
  the runner process group. A second session can request cancellation only when
  it can see the same run store and the runner can validate the recorded live
  process; otherwise the request is recorded for reconciliation.
- Resume preserves partial work. Interrupted mutating stages require
  `--restart-current-stage`; drift fails closed and completed green phases do
  not rerun.
- The adapter and runner enforce pin, path, environment, record, and Git
  invariants. Prompts, hooks, and command wrappers are defense in depth, not
  hard network isolation; direct executables or network-capable code may bypass
  advisory controls. External mutations still require explicit approval.
- `run-plan` resolves relative phase-spec paths from the adapter invocation
  directory before delegation and accepts only regular, canonical,
  non-symlink files below `runtime/coding-harness-plans`. The harness checkout
  and every repository nested beneath it are denied targets.
- Delegation scrubs provider and integration secrets while fixing
  `XDG_CONFIG_HOME=/home/node/.openclaw` and
  `GH_CONFIG_DIR=/home/node/.openclaw/gh`, so authenticated CLI state remains
  available from the persisted OpenClaw mount.
- The harness owns implementation policy and the phased/review contract. Mira
  should not restate generic coding rules in core context. For requests to
  modify Mira herself, do not use this harness route; self-work belongs to a
  separate future skill.

Runtime prerequisites: `gh auth status` must work, `gh repo view
kenneth-huebsch/agent` must confirm private harness access, and `agent status`
must confirm Cursor CLI authentication. Use
`skills/cursor-agent-login/SKILL.md` when Cursor auth is missing.

## Memory

Mira's memory system is local-first. Live memory files live in the workspace:

- `SESSION-STATE.md` - hot working state for the active task.
- `MEMORY.md` - curated durable summaries.
- `memory/YYYY-MM-DD.md` - daily working notes and detailed observations.
- `DREAMS.md` - optional OpenClaw dreaming summaries for human review.

These files are runtime memory, not blueprint behavior. Do not copy accumulated
memory contents, vector databases, git-notes stores, session exports, or cloud
sync state into tracked files unless Kenny explicitly asks.

Useful memory checks inside Mira's agent runtime:

```bash
openclaw config validate
openclaw plugins list
python3 skills/mira-memory/mira_memory_check.py
```

From host-side wrapper checks, command availability can differ from the in-agent
runtime. Prefer testing memory from a fresh Mira DM when validating end-to-end
agent behavior.

Mira's memory search and LanceDB embeddings use OpenRouter's OpenAI-compatible
embeddings endpoint with `OPENROUTER_API_KEY` loaded from ignored secret env
files. `active-memory` is enabled for direct `main` sessions to add bounded
pre-reply recall; it should not persist raw transcripts.

LanceDB is the active memory plugin. Its runtime database lives under ignored
storage at `~/.openclaw/memory/lancedb` in the container, mapped from
`/home/kenny/mira/.openclaw/memory/lancedb` on the host. Agents may use the
OpenClaw memory tools when they are available in a session:

```bash
memory_recall query="query" limit=5
memory_store text="durable memory text" category="fact" importance=0.8
memory_forget id="<memory-id>"
```

In a confirmed fresh DM, bounded recall should surface relevant approved memory
without persisting raw transcripts.

Host-side debugging patterns:

```bash
cd /home/kenny/mira
./scripts/openclaw-cli.sh config validate
./scripts/openclaw-cli.sh plugins list
```

Memory service secrets belong in ignored per-instance files under
`.openclaw/secrets/`, not in tracked config, docs, templates, shell startup
files, or memory notes. Mira does not use third-party cloud memory services by
default.

### Git-Notes Cold Store

Use `skills/memory-cold-store/memory_cold_store.py` for high-value durable
memory such as decisions, lessons, durable corrections, handoffs, and project
landmarks. The git-notes repository lives under ignored runtime storage at
`~/.openclaw/memory/git-notes`.

```bash
python3 skills/memory-cold-store/memory_cold_store.py remember "content" --type decision --topic memory --importance high
python3 skills/memory-cold-store/memory_cold_store.py search "query"
python3 skills/memory-cold-store/memory_cold_store.py list
python3 skills/memory-cold-store/memory_cold_store.py doctor
```

Do not store raw transcripts, logs, email bodies, credentials, tokens,
browser/session state, or unreviewed private dumps in the cold store.

## n8n

The `n8n` skill combines two sources:

- Infrastructure context comes from the private repo
  `https://github.com/kenneth-huebsch/n8n`, refreshed into ignored runtime at
  `/home/node/.openclaw/workspace/runtime/repos/n8n`.
- Workflow and execution operations use the n8n REST API through these
  environment variables:

```bash
N8N_API_KEY=...
N8N_BASE_URL=https://your-n8n.example
```

On this host, keep the live values in ignored runtime state at
`.openclaw/secrets/n8n.env`. `scripts/start-openclaw.sh` and
`scripts/openclaw-cli.sh` load that file and pass `N8N_API_KEY` and
`N8N_BASE_URL` into the OpenClaw gateway and CLI containers. The API key must
not be stored in tracked docs, memory, shell startup files, or workflow exports.

n8n intentionally uses the workspace skill-plus-helper pattern, not a plugin
tool. For Kenny-approved Telegram DM work, Mira may read the skill and run the
helper scripts with `exec`; mutating n8n operations still require explicit
approval.

Useful verification from inside the skill directory:

```bash
python3 scripts/n8n_context.py check-context --pretty
python3 scripts/n8n_context.py refresh-repo --pretty
python3 scripts/n8n_api.py list-workflows --pretty
```

For infrastructure, server, Caddy, TLS, deployment, backup, or SSH work, Mira
should first read the checked-out repo's `AGENTS.md`, `README.md`,
`compose.yaml`, and `.agents/skills/n8n-infrastructure/SKILL.md`.

Listing and inspecting workflows and executions is read-only. Creating,
updating, activating, deactivating, deleting, manually executing workflows, or
changing server infrastructure can affect external systems; get explicit
approval before taking those actions.

## Gmail With `gog`

Mira may check her Gmail on demand when Kenny asks. There are no Gmail crons by
default.

Mira's Gmail account is `mira.agentops@gmail.com`. Use one of the following on
every Gmail call:

- Set `GOG_ACCOUNT=mira.agentops@gmail.com` in the environment, or
- Pass `--account mira.agentops@gmail.com` explicitly.

Useful read-only patterns:

```bash
gog gmail messages search "in:inbox newer_than:30d" --max 20 --account mira.agentops@gmail.com --json
gog gmail get <messageId> --account mira.agentops@gmail.com --json
```

Do not send email, mark messages read, archive, delete, label, create filters,
or otherwise mutate the mailbox unless Kenny explicitly asks for that action.

Use `skills/gog-reauth/SKILL.md` when `gog` reports an expired or revoked Gmail
OAuth token, or when Kenny asks to re-run the Gmail OAuth flow.

## Telegram

Telegram DM is enabled as a Kenny control surface. Keep replies concise and do
not include raw tool output, credentials, internal IDs, transcript paths, or
hidden reasoning.

## Cron

If Kenny asks for scheduled behavior, create it intentionally through the OpenClaw cron CLI, document the
new prompt and dependencies, and update the sync/restore manifest.
