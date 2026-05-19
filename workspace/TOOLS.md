# TOOLS.md

Canonical reference for tool-specific conventions. This file is auto-injected
into every agent run, so cron prompts and `AGENTS.md` should reference it
rather than restating account names, calendar IDs, or command flags.

If a convention here drifts from reality (an account changes, a calendar id
fails to resolve, a command flag is renamed), fix it HERE — once — and every
caller picks it up automatically.

---

## `gog` (Google Workspace CLI)

`gog` is OpenClaw's Google Workspace skill. Always load and follow the bundled
`gog` skill before issuing commands; the notes below cover only the
Kenny-specific conventions.


## `agent-browser` CLI (web browsing)

`agent-browser` is Mira's default tool for live web work. Use it before
`web_fetch` whenever Kenny asks Mira to open, inspect, search within, click
around, scrape, or verify a webpage, especially sites that block simple fetches
(eBay, ESPN, most major news/sports sites).

Use `web_fetch` only when Kenny explicitly asks for a raw URL fetch/static page
read, or when `agent-browser` is unavailable or fails after one retry.

**Always use `agent-browser` first for:**
- Web browsing
- Sports scores, schedules, live data (ESPN, NBA, NFL sites)
- E-commerce searches (eBay, Amazon, etc.)

**Basic pattern:**
```bash
agent-browser open <url>
agent-browser snapshot          # get page content
agent-browser snapshot -i       # get content with interactive refs
agent-browser get title
agent-browser close             # always close when done
```

Load and follow `skills/agent-browser/SKILL.md` for full usage. Do not narrate
that you are using `agent-browser` — just use it and return the result.
