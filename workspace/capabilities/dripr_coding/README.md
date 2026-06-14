---
capability_id: dripr_coding
---

# Dripr Coding

Use this capability when Kenny asks Mira to make a Dripr code change and wants
the work handed to the local prompt-to-PR agent loop.

The coding run is intentionally separate from Dripr Production Debug. Debugging
is read-only. This workflow is allowed to prepare local repos and run Dripr's
prompt-to-PR wrapper because Kenny's coding request is the approval for that
local coding job.

## Live-Only Repos

Both repos live under Mira's OpenClaw runtime workspace:

```bash
/home/node/.openclaw/workspace/runtime/repos/dripr
/home/node/.openclaw/workspace/runtime/repos/agent
```

On Kenny's host these map to:

```bash
/home/kenny/mira/.openclaw/workspace/runtime/repos/dripr
/home/kenny/mira/.openclaw/workspace/runtime/repos/agent
```

The helper clones missing repos from:

```bash
https://github.com/kenneth-huebsch/dripr.git
https://github.com/kenneth-huebsch/agent.git
```

During repo preparation and runner launch, the helper configures a repo-local git
identity for commits created by Dripr's prompt-to-PR runner:

```bash
user.name=mira-dripr-coding-agent
user.email=mira-dripr-coding-agent@users.noreply.github.com
```

Override with `DRIPR_CODING_GIT_USER_NAME` and
`DRIPR_CODING_GIT_USER_EMAIL` in the live-only env file if needed.

If a repo already exists, the helper deletes tracked and untracked local changes
while preserving ignored dependency and env files:

```bash
git reset --hard
git clean -fd
git switch main
git pull --ff-only
```

## Helper Commands

Preflight without changing repos:

```bash
python3 capabilities/dripr_coding/dripr_coding.py check-config
```

Prepare both repos:

```bash
python3 capabilities/dripr_coding/dripr_coding.py prepare-repos
```

List Dripr repo skills from frontmatter:

```bash
python3 capabilities/dripr_coding/dripr_coding.py list-skills
```

Generate the prompt-to-PR task without invoking Cursor or GitHub:

```bash
python3 capabilities/dripr_coding/dripr_coding.py run-prompt-pr --dry-run --title "Fix login redirect" --kind bug --prompt "Fix the login redirect bug and add focused tests."
```

Run the coding job:

```bash
python3 capabilities/dripr_coding/dripr_coding.py run-prompt-pr --title "Fix login redirect" --kind bug --prompt "Fix the login redirect bug and add focused tests."
```

The detached OpenClaw subagent only orchestrates these commands. It does not
need a frontier model by default because Cursor CLI is the implementation engine
inside Dripr's prompt-to-PR runner.

On runner failure, helper JSON includes `review_must_fix` when Dripr's reviewer
left actionable blocking items in `.agent/overnight/review-<slug>.md`.

## Required Live Auth

The Dripr runner requires:

- Cursor CLI command on `PATH` as `agent`, or `CURSOR_BIN` set.
- Cursor auth through `CURSOR_API_KEY` or `agent login`.
- GitHub CLI `gh` on `PATH` and authenticated.
- Git auth able to clone and pull both private repos. If
  `/home/node/.openclaw/secrets/dripr-git-credentials` exists, the helper uses
  it as the Git credential store for both repos.
- Repo-local git identity configured by the helper so Dripr's runner can commit
  implementation, revision, and check-fix passes inside the container.
- Dripr `env/integration.env`, with `DATABASE_URL` pointing to a non-prod,
  non-staging test environment.

Secrets, tokens, auth state, runtime logs, repo checkouts, and generated task
files stay under `.openclaw` runtime paths and must not be copied into the
Mira blueprint.

## Safety Boundaries

- Do not deploy, mutate infrastructure, edit production or staging data, or touch
  credentials.
- Do not run production/staging tests.
- Let Dripr's prompt-to-PR runner own implementation, review, checks, branch
  creation, push, and PR creation.
- If the runner refuses due to ambiguity, missing auth, missing tools, dirty
  state, or a hard stop, report the blocker to Kenny rather than improvising.
