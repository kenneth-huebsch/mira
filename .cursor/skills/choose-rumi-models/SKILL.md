---
name: choose-rumi-models
description: Choose OpenRouter models for Rumi interactive chat, OpenClaw crons, memory consolidation, and tool workflows. Use when changing model pins, default models, thinking levels, or when balancing cost, reliability, emotion, reasoning, and tool execution quality.
---

# Choose Rumi Models

Use this policy when selecting models for Kenny's Rumi/OpenClaw setup.

## Defaults

- **Interactive Rumi:** `openrouter/anthropic/claude-sonnet-4.6`
- **Cron/tool workflows:** `openrouter/xiaomi/mimo-v2-flash`
- **Judgment-heavy durable state work:** evaluate separately; do not blindly use cheap cron defaults.

## Selection Policy

Use `openrouter/xiaomi/mimo-v2-flash` for:

- Email triage, reminders, morning brief, proactive engagement, extraction, routing, and strict `NO_REPLY` jobs.
- Scheduled workflows that must call tools, follow a recipe, and produce visible final text.
- Cost-sensitive jobs where reliable tool execution matters more than deep emotional nuance.

Use `openrouter/anthropic/claude-sonnet-4.6` for:

- Interactive Rumi chat with Kenny.
- Emotionally responsive conversation, warmth, humor, relational presence, and nuanced judgment.
- Persona-heavy turns where the user wants Rumi to feel human, specific, and alive.

Use reasoning-capable or stronger models cautiously for:

- Memory consolidation.
- Promotion/deletion of durable state.
- Complex planning, deduping, or ambiguous edits where a bad change has lasting impact.

## Reasoning Guidance

- For crons: prefer `thinking: off` unless the cron truly needs reasoning.
- For interactive chat: low or model-default reasoning is usually enough; emotional quality comes mostly from model choice and persona instructions.
- Avoid high reasoning for delivery-sensitive Telegram crons unless tested. It can add latency, hidden-output behavior, and cost.

## Anti-Patterns

- Do not use a cheap model just because the job is cheap if it must feel emotionally real.
- Do not use a reasoning model for simple scheduled tool work unless it has proven reliable with visible final output.
- Do not assume a model change took effect after editing JSON directly; use the relevant OpenClaw CLI and verify.
