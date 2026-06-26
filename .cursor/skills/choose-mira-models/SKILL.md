---
name: choose-mira-models
description: Choose OpenRouter models for Mira interactive coding chat, OpenClaw crons if added later, and tool workflows. Use when changing model pins, default models, thinking levels, or balancing cost, reliability, reasoning, and tool execution quality.
---

# Choose Mira Models

Use this policy when selecting models for Kenny's Mira/OpenClaw setup.

## Defaults

- **Interactive Mira:** use the template default unless Kenny asks to change it.
- **Cron/tool workflows:** no crons by default; choose a fully qualified model id if one is added later.
- **Judgment-heavy durable state work:** evaluate separately; do not blindly use cheap cron defaults.
- **Invalid cron value:** never use `default` as a cron payload model; it fails as `openrouter/default`.

## Selection Policy

Use `openrouter/xiaomi/mimo-v2-flash` for:

- Extraction, routing, and strict `NO_REPLY` jobs.
- Scheduled workflows that must call tools, follow a recipe, and produce visible final text.
- Cost-sensitive jobs where reliable tool execution matters more than deep emotional nuance.

Use `openrouter/openai/gpt-5-mini` for:

- Interactive Mira chat with Kenny when the default model is changed to GPT-5 mini.
- Reliable Telegram-visible final output, tool use, and nuanced enough judgment
  for normal personal-assistant work.
- Tool-heavy turns where reliable visible output matters.

Use reasoning-capable or stronger models cautiously for:

- Memory consolidation, if Kenny later asks to add memory.
- Promotion/deletion of durable state, if Mira later gets a memory workflow.
- Complex planning, deduping, or ambiguous edits where a bad change has lasting impact.

## Reasoning Guidance

- For crons: prefer `thinking: off` unless the cron truly needs reasoning.
- For interactive chat: use `thinkingDefault: low`; `gpt-5-mini` requires
  reasoning support and should not be run with thinking off.
- Avoid high reasoning for delivery-sensitive Telegram crons unless tested. It can add latency, hidden-output behavior, and cost.

## Anti-Patterns

- Do not use a cheap model just because the job is cheap if it must feel emotionally real.
- Do not use a reasoning model for simple scheduled tool work unless it has proven reliable with visible final output.
- Do not assume a model change took effect after editing JSON directly; use the relevant OpenClaw CLI and verify.
- Do not write `default` into an OpenClaw cron payload. Use a fully qualified model id.
