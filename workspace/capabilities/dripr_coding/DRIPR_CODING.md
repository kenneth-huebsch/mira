---
capability_id: dripr_coding
---

# Dripr Coding

Use this capability inside a detached Dripr Coding subagent when Kenny asks Mira
to make a code change in Dripr.

The main Interactive Mira session should only scope the request, spawn this
detached child, and return visible confirmation text. Do not perform Dripr
coding work directly in the parent session.

## First Move

Restate the coding request in one sentence:

- Desired change or bug fix.
- Any known affected Dripr areas.
- Any explicit constraints Kenny gave.

This restatement is only orientation. It is not a valid final response and must
be followed immediately by the required flow below unless the request is
ambiguous or blocked.

If Kenny's request is too ambiguous to turn into a coding task, ask one concise
question in the final report and stop. Kenny can answer in Interactive Mira, and
Mira can spawn a fresh coding run.

## Required Flow

1. Read this file and `capabilities/dripr_coding/README.md`.
2. Run:
   ```bash
   python3 capabilities/dripr_coding/dripr_coding.py check-config
   ```
3. Run:
   ```bash
   python3 capabilities/dripr_coding/dripr_coding.py prepare-repos
   ```
4. In the refreshed Dripr checkout, run:
   ```bash
   python3 capabilities/dripr_coding/dripr_coding.py list-skills
   ```
5. Read:
   - `AGENTS.md`
   - every relevant `.agent/skills/*/SKILL.md` file from the catalog
   - `.agent/overnight/README.md`
6. Start the prompt-to-PR runner through the helper:
   ```bash
   python3 capabilities/dripr_coding/dripr_coding.py run-prompt-pr --title "<short title>" --kind chore --prompt "<Kenny's request>"
   ```

Do not stop after reading instructions or restating the request. The coding run
is not started until `run-prompt-pr` is invoked. If you cannot invoke it, the
final report must name the exact command or prerequisite that blocked you.
If `run-prompt-pr` returns `FAILED` with `review_must_fix` items, include those
exact bullets in the final report. Do not say the review details are unavailable
when the helper returned them.

Use `--kind bug`, `--kind feature`, `--kind refactor`, `--kind test`, or
`--kind chore` when Kenny's wording clearly implies one. Use `--touches` only
when the affected areas are small and credible; otherwise omit it and let Dripr's
runner infer scope.

## Repo Preparation Policy

The helper owns repo setup under:

```bash
/home/node/.openclaw/workspace/runtime/repos
```

It clones missing `dripr` and `agent` repos. If they already exist, it refreshes
both to clean `main` with:

```bash
git reset --hard
git clean -fd
git switch main
git pull --ff-only
```

This deletes tracked and untracked local edits while preserving ignored files
such as dependency directories, virtualenvs, and local env files.

## Safety Rules

- Do not run deploy scripts or mutate infrastructure outside the prompt-to-PR
  runner.
- Do not edit production or staging databases.
- Do not touch credentials or env secrets.
- Do not paste raw env files, tokens, auth state, logs, or customer data.
- If `prepare-repos` or the runner fails, report the blocker and stop.
- If the runner exits after reviewer MUST_FIX feedback, treat that as a failed
  prompt-to-PR run: report the MUST_FIX bullets from helper JSON and do not claim
  a PR was created.
- If the prompt implies a database migration, production repair, deploy, or
  infrastructure mutation, let Dripr's runner refuse or ask Kenny for explicit
  operator action.
- Do not return a success report unless `run-prompt-pr` was invoked and returned
  success.
- Do not loop on the same failure more than three times.

## Report Format

Return a concise status report:

```text
Dripr coding run: <short title>

Status:
- <started prompt-to-PR runner / dry-run generated / blocked>

What I did:
- `check-config`: <OK or blocker>
- `prepare-repos`: <OK or blocker>
- `run-prompt-pr`: <command shape, if invoked>

Result:
- <PR URL if the runner produced one, or blocker/failure summary. If
  `review_must_fix` is non-empty, list those bullets here.>

Next step:
- <what Kenny should review or provide>
```
