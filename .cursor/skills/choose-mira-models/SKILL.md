---
name: choose-mira-models
description: Choose OpenRouter models for Mira interactive chat, harness children, OpenClaw crons if added later, and tool workflows. Use when changing model pins, default models, thinking levels, balancing cost vs judgment, or interpreting agent benchmarks such as τ²-Bench.
---

# Choose Mira Models

Use this policy when selecting models for Kenny's Mira/OpenClaw setup.

Mira is two layers. Do not pick one model for both jobs:

- **Interactive Mira (outer loop):** Telegram/chat router. Needs reliable tools,
  scope judgment, quiet autonomy, and cheap long-context turns. Does not need
  frontier coding power; harness children do the heavy coding.
- **Harness children (inner loop):** implement/review/fix via coding-harness
  `policy.json` tiers. Optimize for SWE/Terminal-style coding agents, not chat
  persona.

## Defaults

- **Interactive Mira:** prefer the shortlist below unless Kenny asks otherwise.
  The friend-safe template may lag live; verify live
  `agents.defaults.model.primary` before assuming the pin.
- **Cron/tool workflows:** no crons by default; choose a fully qualified model
  id if one is added later.
- **Judgment-heavy durable state work:** evaluate separately; do not blindly use
  cheap cron defaults.
- **Invalid cron value:** never use `default` as a cron payload model; it fails
  as `openrouter/default`.

## Interactive Mira shortlist

Prefer models in the τ² Airline Pareto band (~≥75% accuracy, low $/task, low
output tokens). Smoke-test on real Mira turns before pinning.

| Priority | Model | Notes |
|---|---|---|
| 1 | `openrouter/z-ai/glm-5.2` | Strong default: tools + efficiency; template-friendly |
| 2 | `openrouter/stepfun/step-3.7-flash` | High accuracy per dollar on τ² Pareto |
| 3 | `openrouter/deepseek/deepseek-v4-flash` | Cheapest near the bar; smoke-test first |
| 4 | `openrouter/qwen/qwen3.5-397b-a17b` | Stronger agent score; slower/talkier; not first for cost |
| 5 | `openrouter/google/gemini-3-flash-preview` | High accuracy; watch output bloat |

Skip for the outer loop unless Kenny explicitly wants them:

- Frontier chat models at Grok/Opus-class spend when cost is the goal.
- `openrouter/openai/gpt-5-mini` as the standing interactive default (see below).

## GPT-5 Mini shortcomings (interactive Mira)

Do **not** treat `openrouter/openai/gpt-5-mini` as the preferred interactive
default. Observed and measured issues:

- **Weak scope judgment.** Over-broad answers that drag in unrelated Mira
  skills, harness internals, or docs (e.g. WordPress/`TOOLS.md` when asked
  about locks phase-3 documentation).
- **Approval/ceremony inflation.** Invents magic phrases, menus, and extra
  confirmations even when autonomy policy says to proceed quietly.
- **Poor τ² cost/task profile.** Mid accuracy (~67%), high wall time, and very
  high output tokens per task — looks cheap per token, burns money and latency
  on real agent turns.
- **Skill-overfitting trap.** Papering over these failures with more skills is
  an arms race; bump the outer-loop model instead.

Mini remains acceptable only for narrow, recipe-like tool jobs where judgment
is not the bottleneck — not as standing interactive Mira.

## How to use benchmarks

Use public agent boards as a **filter**, then validate on Mira-shaped work.

**Useful for interactive Mira**

- **τ²-Bench Airline (OpenRouter):** tool calling under policy, $/task, time,
  output tokens. Good Exacto/tool-reliability signal. Not a Mira job match.
- **τ² other domains / tool-error charts:** check airline overfitting and
  schema/JSON tool failures.
- **Personal smoke set (required before pin):** status of a run; “should we
  upsert skills/docs?”; continue/resume; finalize/push gate. Prefer models that
  stay scoped and quiet.

**Useful for harness children only**

- **SWE-bench Verified / Pro**
- **Terminal-Bench**

**Mostly wrong for interactive Mira**

- GPQA, BrowseComp, DeepSearchQA, and similar trivia/search boards.

Do not autopick “Best Value” or cheapest $/task from airline alone. Airline
task cost ≠ Mira’s bill (huge bootstrap prompts + cache + verbosity). Prefer
Pareto candidates with low output tokens, then smoke-test.

## Selection Policy (non-interactive / cron)

Use `openrouter/xiaomi/mimo-v2-flash` (or current MiMo flash equivalent) for:

- Extraction, routing, and strict `NO_REPLY` jobs.
- Scheduled workflows that must call tools, follow a recipe, and produce
  visible final text.
- Cost-sensitive jobs where reliable tool execution matters more than judgment.

Use reasoning-capable or stronger models cautiously for:

- Memory consolidation, if Kenny later asks to add memory.
- Promotion/deletion of durable state, if Mira later gets a memory workflow.
- Complex planning, deduping, or ambiguous edits where a bad change has lasting
  impact.

## Reasoning Guidance

- For crons: prefer `thinking: off` unless the cron truly needs reasoning.
- For interactive chat: use `thinkingDefault: low`. Models that require
  reasoning support should not be run with thinking off.
- Avoid high reasoning for delivery-sensitive Telegram crons unless tested. It
  can add latency, hidden-output behavior, and cost.

## Anti-Patterns

- Do not skill-overfit a weak interactive model to fix judgment failures; change
  the model.
- Do not use a cheap model just because the job is cheap if scope discipline or
  emotional continuity matters.
- Do not use a reasoning model for simple scheduled tool work unless it has
  proven reliable with visible final output.
- Do not assume a model change took effect after editing JSON directly; use
  `openclaw models set` / config validate and verify live primary.
- Do not write `default` into an OpenClaw cron payload. Use a fully qualified
  model id.
- Do not pick interactive Mira from SWE-bench alone, or harness children from
  τ² Airline alone.
