---
name: agent-browser
description: Use the agent-browser CLI before web_fetch/web_search for any live web task: opening a site, inspecting a page, getting page text or title, clicking, typing, filling forms, scraping rendered content, checking sports/e-commerce/news pages, taking screenshots, or browser testing.
metadata: {"openclaw":{"requires":{"bins":["agent-browser"]},"homepage":"https://github.com/vercel-labs/agent-browser"}}
---

# agent-browser

Use `agent-browser` as the default interface for live web work.

## Rules

- Use `agent-browser` before `web_fetch` or `web_search` for any live website task.
- Use `agent-browser` instead of generating one-off Node or Playwright scripts.
- Only use `web_fetch` when the user explicitly asks for a raw/static URL fetch, or when `agent-browser` is unavailable or fails after one retry.
- Do not narrate that you are using `agent-browser` unless the user explicitly asks for implementation details.
- If the user asks for only the final result, do the browser work silently and return only that result.
- Do not say things like "I'll use agent-browser", "I'll open the page", or "I'll get the title" before doing the work.
- Keep one session alive across related commands unless isolation is needed.
- After navigation or major DOM changes, run a fresh snapshot before using refs again.
- Use `--json` when structured output will help the next step.
- When the task is complete, close the browser with `agent-browser close`.

## Preferred patterns

- For page titles, prefer:
  - `agent-browser open <url>`
  - `agent-browser get title`
- For simple text extraction, prefer `get` commands before snapshotting the whole page.
- Use `snapshot -i` when you need refs for interaction, not for every task.

## Core workflow

1. Open the page:
   - `agent-browser open <url>`
2. For simple metadata, prefer direct getters:
   - `agent-browser get title`
   - `agent-browser get url`
3. Discover interactable elements when needed:
   - `agent-browser snapshot -i`
4. Use refs like `@e1`, `@e2` to interact:
   - `agent-browser click @e1`
   - `agent-browser fill @e2 "text"`
5. Wait when needed:
   - `agent-browser wait --load networkidle`
   - `agent-browser wait --text "Success"`
6. Re-snapshot after navigation or major updates.
7. Close the browser when done:
   - `agent-browser close`

## Common commands

```bash
agent-browser open <url>
agent-browser get title
agent-browser snapshot -i
agent-browser click @e1
agent-browser fill @e2 "text"
agent-browser type @e2 "more text"
agent-browser press Enter
agent-browser hover @e1
agent-browser select @e1 "value"
agent-browser scrollintoview @e1
agent-browser wait --load networkidle
agent-browser wait --text "Success"
agent-browser get text @e1
agent-browser get url
agent-browser screenshot
agent-browser close
```

## Useful patterns

### Forms

```bash
agent-browser open https://example.com/form
agent-browser snapshot -i
agent-browser fill @e1 "user@example.com"
agent-browser fill @e2 "Hello"
agent-browser click @e3
agent-browser wait --load networkidle
agent-browser snapshot -i
```

### Scraping

```bash
agent-browser open https://example.com
agent-browser get title
agent-browser close
```

### Debugging

```bash
agent-browser --headed open https://example.com
agent-browser console
agent-browser errors
agent-browser highlight @e1
```

## Notes

- Refs are tied to the current page state and may change after navigation.
- `fill` clears before typing; use `type` to append.
- Prefer `agent-browser get title` over inferring the title from `open` output.
- Use sessions when working across multiple independent browser tasks:
  - `agent-browser --session test1 open <url>`
