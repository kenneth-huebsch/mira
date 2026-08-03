# Run Mira

This folder is Mira's self-contained OpenClaw home.

Tracked files are the friend-safe blueprint: behavior docs, scripts, templates,
plugins, skills, and restore docs. Local runtime infrastructure is
kept beside it but ignored by git:

- `openclaw-src/` - Mira's OpenClaw source checkout.
- `.openclaw/` - Mira's live OpenClaw state, config, credentials, sessions,
  cron state, QMD runtime, Telegram state, and workspace.

## Commands

Start Mira:

```bash
cd /home/kenny/mira
./scripts/start-openclaw.sh
```

Stop Mira:

```bash
cd /home/kenny/mira
./scripts/stop-openclaw.sh
```

Run OpenClaw CLI commands in Mira's compose project:

```bash
cd /home/kenny/mira
./scripts/openclaw-cli.sh dashboard --no-open
```

Upgrade Mira's OpenClaw source:

```bash
cd /home/kenny/mira
./scripts/sync-from-live.sh
cd /home/kenny/mira/openclaw-src
git status --short
stable_tag="$(gh release view --repo openclaw/openclaw \
  --json tagName,isPrerelease,isDraft \
  --jq 'select(.isPrerelease == false and .isDraft == false) | .tagName')"
test -n "$stable_tag"
GIT_TERMINAL_PROMPT=0 git fetch origin tag "$stable_tag"
git merge --ff-only "$stable_tag"
git describe --tags --exact-match HEAD
git status --short
```

If source files under `src/` are dirty, report them before upgrading. Mira's
managed OpenClaw source-local files are `docker-compose.yml` and
`entrypoint.sh`; preserve only those files across the fast-forward after syncing
them to the blueprint. If Git refuses the fast-forward because they are dirty,
stash exactly those two paths, merge the stable tag, then pop that stash and
verify the source diff is still limited to those managed files. Do not follow
untagged `main` or a prerelease when the goal is the newest stable deployment.

Rebuild and recreate Mira's gateway after the source update:

```bash
cd /home/kenny/mira/openclaw-src
docker build --build-arg OPENCLAW_EXTENSIONS=memory-lancedb -t openclaw:local .
cd /home/kenny/mira
./scripts/start-openclaw.sh
```

The Docker build may be slow after a large upstream jump because the OpenClaw
image runs dependency install, server build, UI build, and production pruning.

## Defaults

- Compose project: `openclaw-mira`
- OpenClaw source: `/home/kenny/mira/openclaw-src`
- OpenClaw state: `/home/kenny/mira/.openclaw`
- Workspace: `/home/kenny/mira/.openclaw/workspace`
- Gateway port: `18791`
- Bridge port: `18792`
- UI/dev port: `3501`

Override these with environment variables only for recovery or migration work.

## Persistent AWS Tools

`openclaw-src/entrypoint.sh`, mirrored as tracked
`openclaw/entrypoint.sh`, idempotently provisions these exact tools under the
persistent OpenClaw home:

- Official AWS CLI v2 `2.36.14` at
  `/home/node/.openclaw/tools/aws-cli/2.36.14`.
- npm package `aws-cdk@2.1134.0` at
  `/home/node/.openclaw/tools/aws-cdk/2.1134.0`.

The entrypoint supports Debian `amd64` and `arm64`, verifies the pinned AWS
archive checksum before extraction, and links `aws` and `cdk` into both
`/home/node/.openclaw/bin` and `/usr/local/bin`. Version, install-root, bin-dir,
and AWS checksum environment overrides are available for deliberate recovery
work; the defaults remain the reviewed exact pins. Repository npm scripts still
prefer their local `node_modules/.bin`.

After a normal future image rebuild/recreation, verify the provisioned command
surface inside the gateway:

```bash
aws --version
cdk --version
```


## Provider Credentials

Mira's environment-style secrets are per-instance, not global shell state. The
live auth profile references `OPENROUTER_API_KEY` through a SecretRef-style env
reference. OpenClaw reads its native fallback file, and
`scripts/start-openclaw.sh` plus `scripts/openclaw-cli.sh` source that same file
for Docker Compose interpolation:

```bash
/home/kenny/mira/.openclaw/.env
```

The scripts pass those values into Docker through `openclaw/provider-auth.compose.yml`, so the setup does not depend on global shell exports or source checkout defaults.

That file is ignored runtime state and must not be committed. Keep it at mode
`600`. To rotate the OpenRouter token, replace `OPENROUTER_API_KEY` without
printing its value, then restart this OpenClaw home:

```bash
cd /home/kenny/mira
./scripts/stop-openclaw.sh
./scripts/start-openclaw.sh
```

Do not put provider API keys in `~/.bashrc`, tracked docs, templates, or
`auth-profiles.json`. The expected live auth profile shape is a `keyRef` to
`OPENROUTER_API_KEY`; the token value belongs only in the ignored `.env` file.

For the default Telegram account, put `TELEGRAM_BOT_TOKEN` in `.env` and omit
`botToken`, `tokenFile`, and `token` from `channels.telegram`. OpenClaw uses its
documented environment fallback. The `token` property is invalid for Telegram.

## Memory Runtime

Mira's live memory files are in `/home/kenny/mira/.openclaw/workspace`:

- `SESSION-STATE.md` for hot working state.
- `MEMORY.md` for curated durable summaries.
- `memory/YYYY-MM-DD.md` for daily working notes.
- `DREAMS.md` for optional consolidation review.

The blueprint tracks empty scaffold templates under `templates/memory-scaffold/`
and restores them only when the corresponding live memory files are missing.
Existing memory files are preserved by `scripts/restore-to-live.sh`.

Mira's memory search uses OpenRouter's OpenAI-compatible embeddings endpoint via
`OPENROUTER_API_KEY`; the live key is loaded from ignored `.openclaw/.env`, not
tracked config. Useful checks inside Mira's agent runtime:

```bash
openclaw config validate
openclaw plugins list
python3 skills/mira-memory/mira_memory_check.py
```

From host-side wrapper checks, command availability can differ from the in-agent
runtime. Prefer testing memory from a fresh Mira DM when validating end-to-end
agent behavior.

The `active-memory` plugin is enabled for direct `main` sessions. It should add
bounded pre-reply recall without persisting raw transcripts. Verify it through
`openclaw plugins list`, config inspection, and a fresh Mira DM that references a
known stored memory.

LanceDB is the active memory plugin. The container path is
`~/.openclaw/memory/lancedb`; on this host it maps to
`/home/kenny/mira/.openclaw/memory/lancedb`.

```bash
memory_recall query="recent preference" limit=5
memory_store text="durable memory text" category="fact" importance=0.8
memory_forget id="<memory-id>"
```

In a confirmed fresh DM, bounded recall should surface relevant approved memory
without persisting raw transcripts.

Host-side debugging checklist:

```bash
cd /home/kenny/mira
./scripts/openclaw-cli.sh config validate
./scripts/openclaw-cli.sh plugins list
docker exec --user node openclaw-mira-openclaw-gateway-1 \
  sh -lc 'cd /home/node/.openclaw/workspace && python3 skills/mira-memory/mira_memory_check.py'
MIRA_MEMORY_COLD_STORE_DIR=/home/kenny/mira/.openclaw/memory/git-notes \
  python3 /home/kenny/mira/.openclaw/workspace/skills/memory-cold-store/memory_cold_store.py doctor
```

If a host-side `openclaw memory ...` command is unavailable or shows different
tool exposure than a real conversation, verify from a fresh Mira DM before
changing config; CLI command surfaces have differed across OpenClaw builds.

Memory service secrets such as embedding provider keys belong in the ignored
`/home/kenny/mira/.openclaw/.env`.
`scripts/start-openclaw.sh` and `scripts/openclaw-cli.sh` source
`scripts/load-openclaw-env.sh`, which loads that unified file.
Do not commit live memory contents, vector indexes, git-notes stores, cloud
memory exports, session memory indexes, or service keys.

Git-notes cold memory uses a workspace-local helper and an ignored runtime repo:

```bash
python3 /home/kenny/mira/.openclaw/workspace/skills/memory-cold-store/memory_cold_store.py doctor
python3 /home/kenny/mira/.openclaw/workspace/skills/memory-cold-store/memory_cold_store.py search "query"
```

From the host, use Mira's live runtime path explicitly:

```bash
MIRA_MEMORY_COLD_STORE_DIR=/home/kenny/mira/.openclaw/memory/git-notes \
  python3 /home/kenny/mira/.openclaw/workspace/skills/memory-cold-store/memory_cold_store.py doctor
```

## n8n Runtime

The `n8n` skill requires these names in the ignored runtime environment file:

```bash
/home/kenny/mira/.openclaw/.env
```

Use `templates/n8n.env.example` for the redacted variable-name snippet:

```bash
N8N_API_KEY=...
N8N_BASE_URL=https://your-n8n.example
```

After creating or rotating those values, keep `.env` at mode `600`, restart Mira,
and verify from the skill directory with:

```bash
python3 scripts/n8n_api.py list-workflows --pretty
```

Listing workflows is read-only. Creating, updating, activating, deactivating,
deleting, or manually executing workflows may mutate external systems and needs
explicit approval.

## WordPress Page Updater

Mira uses the standard WordPress REST API to list, read, and update the content
of existing pages. MCP and a WordPress-side custom plugin are not required.

WordPress setup:

1. Confirm the site uses HTTPS.
2. Create a dedicated standard Editor user for Mira. An Author cannot edit
   pages; do not use an Administrator account.
3. In the dedicated user's profile, create an Application Password named
   `Mira page updater`. Save it when shown; it cannot be retrieved later and
   can be revoked independently.
4. Merge the variable names from `templates/wordpress.env.example` into the
   ignored runtime file below, replace all placeholders, remove spaces from the
   Application Password, and keep the file mode at `600`:

```bash
/home/kenny/mira/.openclaw/.env
```

Expected shape:

```bash
WORDPRESS_BASE_URL=https://your-wordpress-site.example
WORDPRESS_USERNAME=dedicated-mira-editor
WORDPRESS_APP_PASSWORD=replace-with-application-password-without-spaces
```

`scripts/start-openclaw.sh` and `scripts/openclaw-cli.sh` load this file and
pass only these WordPress values to the gateway container. Never place the live
password in tracked files, memory, chat, or shell startup files.

Restart Mira after creating or rotating the file:

```bash
cd /home/kenny/mira
./scripts/stop-openclaw.sh
./scripts/start-openclaw.sh
```

Verify read-only access:

```bash
docker exec --user node openclaw-mira-openclaw-gateway-1 \
  sh -lc 'cd /home/node/.openclaw/workspace/skills/wordpress-page-updater && python3 scripts/wordpress_page.py --pretty check'
```

The helper can list/search pages and accepts a page ID for read/update
operations, but updates only page content. Updating an already-published page
is immediately live, so Mira must fetch it, show the proposed diff, and obtain
fresh explicit approval before the update call. The helper checks
`modified_gmt` immediately before writing and refuses a stale preview.

This site currently prepends repeated WPBakery `vc_shortcodes-default-css` and
`vc_shortcodes-custom-css` `<style>` tags to REST responses. The helper strips
only those exact known prefixes before JSON decoding. If the prefixes change or
other markup appears, it fails closed; fix the WordPress plugin output rather
than accepting arbitrary HTML around API responses.

WordPress stores revisions for page updates. To roll back, open the page in
WordPress admin, open **Revisions**, select the prior revision, and restore it.
The helper intentionally does not expose rollback, delete, status, title, slug,
author, page creation, or arbitrary REST operations.

To revoke access, remove the named Application Password from the dedicated
user's profile, remove the three `WORDPRESS_*` entries from `.env` without
printing other values, and restart Mira.

### Addicks/Barker PDF Case Updates

The specialized skill at
`workspace/skills/addicks-barker-case-updates/SKILL.md` converts a supplied
case-update PDF into a staged WPBakery insertion for page `3041`. OpenClaw's
built-in `pdf` tool handles local paths, URLs, and inbound media references
through the enabled bundled `document-extract` plugin and the configured
OpenRouter `pdfModel`; no host PDF package is required.

The target page must retain exactly one
`[vc_column ... el_id="updates-column"]` and its black, left-aligned,
50%-width top separator. The staging helper inserts a new separator and text
box before that existing separator while preserving all prior page content.

Useful checks:

```bash
cd /home/kenny/mira/.openclaw/workspace/skills/addicks-barker-case-updates
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s tests -p 'test_*.py'
python3 scripts/case_update.py --help
```

Runtime artifacts live under ignored
`workspace/runtime/addicks-barker-case-updates/`. `stage` never writes to
WordPress. `publish` verifies the fixed page/URL, source `modified_gmt`, source
content hash, manifest, and staged file hashes before updating. It still
requires fresh explicit approval of the displayed snippet immediately before
execution.

## Runtime Boundary

Mira's harness routing and on-demand Gmail commands run through OpenClaw `exec`
in the gateway container, with workspace paths rooted at
`/home/node/.openclaw/workspace`. Container runtime dependencies are prepared by
`openclaw/entrypoint.sh`; live credentials stay under
`/home/kenny/mira/.openclaw` on the host and map into `/home/node/.openclaw`
inside the container.

Mira has no cron jobs by default. If scheduled behavior is added later, document
the prompt and dependencies in the blueprint before relying on it.

## Coding Harness

Mira routes non-Mira coding requests through Kenny's private agent harness:

- Harness repo: `https://github.com/kenneth-huebsch/agent`
- Host runtime checkout: `/home/kenny/mira/.openclaw/workspace/runtime/repos/agent`
- Container runtime checkout: `/home/node/.openclaw/workspace/runtime/repos/agent`
- Helper: `/home/node/.openclaw/workspace/skills/coding-harness/coding_harness.py`

Useful checks:

```bash
cd /home/kenny/mira
docker exec --user node openclaw-mira-openclaw-gateway-1 \
  python3 /home/node/.openclaw/workspace/skills/coding-harness/coding_harness.py check-config
```

The preflight runs `gh auth status`, a private `gh repo view` for the harness,
and `agent status`. Fresh private clones use GitHub CLI's Git credential helper
without exporting or printing a token. Delegation preserves the mounted CLI
config locations at `/home/node/.openclaw` and `/home/node/.openclaw/gh` while
scrubbing secret environment variables. If Cursor auth is missing, use
`workspace/skills/cursor-agent-login/SKILL.md` or provide `CURSOR_API_KEY`
through ignored runtime secrets before expecting coding runs to execute.

`refresh-harness` materializes the exact full SHA in `harness.lock.json`
detached; it never switches or pulls a branch. Update that lock only after
reviewing and testing a specific immutable revision. Run records are under
`runtime/coding-harness-runs`; phase specs are under
`runtime/coding-harness-plans`.

```bash
python3 skills/coding-harness/coding_harness.py resume <run-or-plan-id> [--restart-current-stage]
python3 skills/coding-harness/coding_harness.py cancel <run-or-plan-id> --reason "<reason>"
```

Interrupted mutating stages preserve partial work and need explicit restart.
Second-session cancellation works only with the same run store and a verifiable
recorded process; otherwise the request remains for reconciliation. The runner
timeout is 3000 seconds, cancellation grace is 15 seconds, and the OpenClaw
outer timeout is 3600 seconds. Pin, path, environment, Git, and record checks
are enforced; prompts, hooks, and wrappers remain advisory defense in depth and
do not provide hard network isolation.

Mira self-work is intentionally out of scope for this harness skill.

## Infrastructure Paths

Use these paths when maintaining Mira's setup outside the harness route:

- Blueprint repo: `/home/kenny/mira`
- Live workspace: `/home/kenny/mira/.openclaw/workspace`
- Live config/state: `/home/kenny/mira/.openclaw`
- OpenClaw source checkout: `/home/kenny/mira/openclaw-src`
- Gateway container: `openclaw-mira-openclaw-gateway-1`

Behavior changes should usually start in the live workspace and then be synced
back:

```bash
cd /home/kenny/mira
./scripts/sync-from-live.sh
git diff
```

Restore and runtime verification:

```bash
cd /home/kenny/mira
./scripts/restore-to-live.sh
./scripts/openclaw-cli.sh cron list --json
```
