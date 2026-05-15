import { appendFile, mkdir, readFile } from "node:fs/promises";
import path from "node:path";
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

type MediumMemoryRecord = {
  summary: string;
  created_at: string;
  expires_at: string;
};

type MemoryDecision = {
  should_store: boolean;
  summary: string;
  expires_in_days: number;
};

type LoaderMode = "interactive" | "heartbeat" | "cron";

type DynamicLoader = (workspaceDir: string) => Promise<string | undefined>;

type CronProfile = {
  systemFiles: string[];
  dynamicLoaders: DynamicLoader[];
};

type DynamicSpec =
  // Named loader from NAMED_LOADERS, e.g. "rolling_summary"
  | string
  // Inline loader spec
  | {
      kind: "file";
      path: string;
    }
  | {
      kind: "jsonl_tail";
      path: string;
      limit?: number;
      title?: string;
    };

const MEDIUM_MEMORY_FILE = "memory/medium_memory.jsonl";
const LONG_MEMORY_FILE = "memory/long_memory.jsonl";
const ENGAGEMENT_MEMORY_FILE = "memory/engagement_memory.jsonl";
const PROJECTS_FILE = "memory/projects.jsonl";
const PROJECT_RUNS_FILE = "memory/project_runs.jsonl";
const PROJECT_DETAILS_FILE = "memory/project_details.jsonl";
const SKILL_FILE = "skills/memory_manager.md";
const MAX_SUMMARY_LENGTH = 140;
const INTERACTIVE_MEDIUM_LIMIT = 8;
const INTERACTIVE_LONG_LIMIT = 4;
const INTERACTIVE_PROJECT_LIMIT = 5;
const INTERACTIVE_PENDING_RUN_LIMIT = 4;
const INTERACTIVE_PROJECT_DETAIL_LIMIT = 10;
const HEARTBEAT_ENGAGEMENT_HISTORY_LIMIT = 6;
const HEARTBEAT_MEDIUM_MEMORY_LIMIT = 2;
const HEARTBEAT_HISTORY_MAX_CHARS = 1200;
const HEARTBEAT_MEDIUM_MEMORY_MAX_CHARS = 360;
const PROACTIVE_ENGAGEMENT_HISTORY_LIMIT = 20;
const PROACTIVE_MEDIUM_LIMIT = 10;
const PROACTIVE_LONG_LIMIT = 10;
// OpenClaw's bootstrap auto-injects AGENTS.md, SOUL.md, IDENTITY.md, USER.md,
// TOOLS.md, and HEARTBEAT.md on every run. Capability-owned interactive policy
// can be injected here so AGENTS.md stays focused on global invariants.
const INTERACTIVE_SYSTEM_FILES: string[] = [];
const INTERACTIVE_CAPABILITY_FILES: string[] = [
  "capabilities/project_companion/INTERACTIVE.md",
];
const HEARTBEAT_SYSTEM_FILES: string[] = [];
const PENDING_PROJECT_RUN_STATUSES = new Set([
  "queued",
  "in_progress",
  "pending_confirmation",
  "needs_input",
  "failed",
]);

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function isoDateNow(): string {
  return new Date().toISOString().slice(0, 10);
}

function addDays(dateIso: string, days: number): string {
  const date = new Date(`${dateIso}T00:00:00.000Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function normalizeSummary(text: string): string {
  const compact = text.replace(/\s+/g, " ").trim();
  return compact.slice(0, MAX_SUMMARY_LENGTH);
}

function parseJsonObject(raw: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
  } catch {
    return null;
  }
  return null;
}

function parsePossiblyWrappedJson(raw: string): Record<string, unknown> | null {
  const direct = parseJsonObject(raw.trim());
  if (direct) {
    return direct;
  }

  const fenced = raw.match(/```(?:json)?\s*([\s\S]*?)\s*```/i);
  if (fenced?.[1]) {
    return parseJsonObject(fenced[1]);
  }

  const firstBrace = raw.indexOf("{");
  const lastBrace = raw.lastIndexOf("}");
  if (firstBrace >= 0 && lastBrace > firstBrace) {
    return parseJsonObject(raw.slice(firstBrace, lastBrace + 1));
  }

  return null;
}

function normalizeRecord(input: Record<string, unknown>): MediumMemoryRecord | null {
  const summary = String(input.summary ?? "").trim();
  const createdAt = String(input.created_at ?? "").trim();
  const expiresAt = String(input.expires_at ?? "").trim();

  if (!summary || !createdAt || !expiresAt) {
    return null;
  }

  return {
    summary,
    created_at: createdAt,
    expires_at: expiresAt,
  };
}

function normalizeDecision(input: Record<string, unknown>): MemoryDecision {
  const summary = normalizeSummary(String(input.summary ?? ""));
  return {
    should_store: Boolean(input.should_store) && summary.length > 0,
    summary,
    expires_in_days: clamp(Number(input.expires_in_days ?? 7), 3, 30),
  };
}

function extractLatestUserMessage(payload: unknown): string {
  const data = payload as Record<string, unknown>;
  const directCandidates = [
    data.userMessage,
    data.user_message,
    data.latestUserMessage,
    data.input,
    data.prompt,
  ];
  for (const candidate of directCandidates) {
    if (typeof candidate === "string" && candidate.trim()) {
      return candidate.trim();
    }
  }

  const messages = Array.isArray(data.messages) ? data.messages : [];
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i] as Record<string, unknown>;
    const role = String(message.role ?? "");
    if (role === "user" && typeof message.content === "string" && message.content.trim()) {
      return message.content.trim();
    }
  }
  return "";
}

function extractLatestAssistantReply(payload: unknown): string {
  const data = payload as Record<string, unknown>;
  const directCandidates = [
    data.finalResponse,
    data.final_response,
    data.assistantResponse,
    data.assistant_reply,
  ];
  for (const candidate of directCandidates) {
    if (typeof candidate === "string" && candidate.trim()) {
      return candidate.trim();
    }
  }

  const messages = Array.isArray(data.messages) ? data.messages : [];
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i] as Record<string, unknown>;
    const role = String(message.role ?? "");
    if (role === "assistant" && typeof message.content === "string" && message.content.trim()) {
      return message.content.trim();
    }
  }
  return "";
}

function resolveWorkspaceDir(...sources: unknown[]): string {
  for (const source of sources) {
    const data = source as Record<string, unknown>;
    if (!data || typeof data !== "object") {
      continue;
    }

    const candidates = [
      data.workspaceDir,
      data.workspace_dir,
      data.cwd,
      data.workingDirectory,
      data.workdir,
    ];
    for (const candidate of candidates) {
      if (typeof candidate === "string" && candidate.trim()) {
        return candidate;
      }
    }
  }

  return ".";
}

function resolveMode(context: unknown): LoaderMode {
  const trigger = String((context as Record<string, unknown> | undefined)?.trigger ?? "").trim();
  if (trigger === "cron") {
    return "cron";
  }
  if (trigger === "heartbeat") {
    return "heartbeat";
  }
  return "interactive";
}

/**
 * Extract the YAML-style frontmatter block from a markdown document.
 * Frontmatter must be the very first non-empty content and is delimited by
 * lines containing only `---`. Returns the raw inner body (no delimiters).
 */
function extractFrontmatter(prompt: string): string | null {
  // Tolerate UTF-8 BOM and leading blank lines.
  const stripped = prompt.replace(/^\uFEFF/, "").replace(/^\s*\n/, "");
  if (!stripped.startsWith("---")) {
    return null;
  }
  const after = stripped.slice(3);
  // Allow either \n or \r\n right after the opening ---
  const end = after.search(/\n---\s*(\n|$)/);
  if (end < 0) {
    return null;
  }
  return after.slice(0, end);
}

function parseCronId(prompt: string): string | null {
  const match = prompt.match(/(?:^|\n)cron_id:\s*([a-z0-9_:-]+)/i);
  return match?.[1]?.trim().toLowerCase() ?? null;
}

function referencedCronPromptPath(prompt: string): string | null {
  const match = prompt.match(/Run this prompt file:\s*([^\s]+)/i);
  const rawPath = match?.[1]?.trim().replace(/[."'`]+$/g, "") ?? "";
  if (!rawPath || path.isAbsolute(rawPath)) {
    return null;
  }
  const normalized = path.posix.normalize(rawPath.replace(/\\/g, "/"));
  if (!normalized.startsWith("cron/") || normalized.includes("..")) {
    return null;
  }
  if (!normalized.endsWith(".md")) {
    return null;
  }
  return normalized;
}

async function resolveCronPrompt(workspaceDir: string, prompt: string): Promise<string> {
  if (parseCronId(prompt)) {
    return prompt;
  }
  const relativePath = referencedCronPromptPath(prompt);
  if (!relativePath) {
    return prompt;
  }
  const resolved = await readTextIfExists(path.join(workspaceDir, relativePath));
  return resolved ?? prompt;
}

/**
 * Minimal YAML subset parser tailored to our cron frontmatter shape.
 * Supports:
 *   - top-level `key: value` scalars
 *   - top-level `key:` followed by a list of `- value` lines, where each
 *     value is either a scalar or a flow-style mapping like
 *     `- { kind: jsonl_tail, path: "memory/x.jsonl", limit: 10 }`
 * It is intentionally not a full YAML parser — keep frontmatter simple.
 */
function parseCronFrontmatter(prompt: string): {
  systemFiles: string[];
  dynamic: DynamicSpec[];
} {
  const block = extractFrontmatter(prompt);
  if (!block) {
    return { systemFiles: [], dynamic: [] };
  }

  const lines = block.split(/\r?\n/);
  const systemFiles: string[] = [];
  const dynamic: DynamicSpec[] = [];
  let currentList: "system_files" | "dynamic" | null = null;

  for (const rawLine of lines) {
    const line = rawLine.replace(/\s+$/, "");
    if (!line.trim()) {
      continue;
    }
    // List item under the current key.
    const listMatch = line.match(/^\s+-\s+(.+)$/);
    if (listMatch && currentList) {
      const value = listMatch[1].trim();
      if (currentList === "system_files") {
        systemFiles.push(stripQuotes(value));
      } else {
        const spec = parseDynamicSpec(value);
        if (spec) {
          dynamic.push(spec);
        }
      }
      continue;
    }
    // Top-level key.
    const keyMatch = line.match(/^([a-z_][a-z0-9_]*)\s*:\s*(.*)$/i);
    if (keyMatch) {
      const [, key, rawValue] = keyMatch;
      const value = rawValue.trim();
      if (key === "system_files") {
        currentList = "system_files";
        if (value.startsWith("[")) {
          // Inline flow-list: [a, b, c]
          for (const entry of splitFlowList(value)) {
            systemFiles.push(stripQuotes(entry));
          }
          currentList = null;
        }
      } else if (key === "dynamic") {
        currentList = "dynamic";
        if (value.startsWith("[")) {
          for (const entry of splitFlowList(value)) {
            const spec = parseDynamicSpec(entry);
            if (spec) {
              dynamic.push(spec);
            }
          }
          currentList = null;
        }
      } else {
        // Unknown top-level key; reset list context.
        currentList = null;
      }
    }
  }

  return { systemFiles, dynamic };
}

function stripQuotes(value: string): string {
  const trimmed = value.trim();
  if (
    (trimmed.startsWith('"') && trimmed.endsWith('"')) ||
    (trimmed.startsWith("'") && trimmed.endsWith("'"))
  ) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}

function splitFlowList(value: string): string[] {
  const trimmed = value.trim().replace(/^\[/, "").replace(/\]$/, "");
  if (!trimmed) {
    return [];
  }
  // Comma-split, ignoring commas inside braces/brackets/quotes.
  const out: string[] = [];
  let depth = 0;
  let inQuote: '"' | "'" | null = null;
  let start = 0;
  for (let i = 0; i < trimmed.length; i += 1) {
    const ch = trimmed[i];
    if (inQuote) {
      if (ch === inQuote) inQuote = null;
      continue;
    }
    if (ch === '"' || ch === "'") {
      inQuote = ch;
      continue;
    }
    if (ch === "{" || ch === "[") {
      depth += 1;
      continue;
    }
    if (ch === "}" || ch === "]") {
      depth -= 1;
      continue;
    }
    if (ch === "," && depth === 0) {
      out.push(trimmed.slice(start, i).trim());
      start = i + 1;
    }
  }
  const last = trimmed.slice(start).trim();
  if (last) {
    out.push(last);
  }
  return out;
}

function parseDynamicSpec(value: string): DynamicSpec | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  // Inline mapping: { kind: jsonl_tail, path: ..., limit: 20, title: "..." }
  if (trimmed.startsWith("{") && trimmed.endsWith("}")) {
    const inner = trimmed.slice(1, -1);
    const fields: Record<string, string> = {};
    for (const part of splitFlowList(inner)) {
      const eq = part.indexOf(":");
      if (eq < 0) continue;
      const key = part.slice(0, eq).trim();
      const raw = stripQuotes(part.slice(eq + 1).trim());
      fields[key] = raw;
    }
    const kind = fields.kind;
    if (kind === "file" && fields.path) {
      return { kind: "file", path: fields.path };
    }
    if (kind === "jsonl_tail" && fields.path) {
      const limit = fields.limit ? Number(fields.limit) : undefined;
      return {
        kind: "jsonl_tail",
        path: fields.path,
        limit: Number.isFinite(limit) ? (limit as number) : undefined,
        title: fields.title,
      };
    }
    return null;
  }
  // Otherwise, treat as a named loader id.
  return stripQuotes(trimmed);
}

function isExpired(entry: MediumMemoryRecord): boolean {
  return entry.expires_at < isoDateNow();
}

function sortByCreatedAtDescending(entries: MediumMemoryRecord[]): MediumMemoryRecord[] {
  return [...entries].sort((left, right) => right.created_at.localeCompare(left.created_at));
}

function takeRecentEntries(entries: MediumMemoryRecord[], limit: number): MediumMemoryRecord[] {
  return sortByCreatedAtDescending(entries).slice(0, limit);
}

function renderSection(title: string, body: string): string {
  return `${title}:\n${body.trim()}`;
}

function renderBullets(title: string, lines: string[]): string | undefined {
  if (lines.length === 0) {
    return undefined;
  }
  return renderSection(title, lines.map((line) => `- ${line}`).join("\n"));
}

function keepRecentLinesWithinBudget(lines: string[], maxChars?: number): string[] {
  if (!maxChars || maxChars <= 0) {
    return lines;
  }

  const kept: string[] = [];
  let usedChars = 0;
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    const line = lines[index];
    const separatorChars = kept.length > 0 ? 1 : 0;
    const nextUsedChars = usedChars + separatorChars + line.length;
    if (nextUsedChars > maxChars) {
      continue;
    }
    kept.unshift(line);
    usedChars = nextUsedChars;
  }
  return kept;
}

async function readTextIfExists(filePath: string): Promise<string | null> {
  try {
    const raw = await readFile(filePath, "utf8");
    const trimmed = raw.trim();
    return trimmed ? trimmed : null;
  } catch {
    return null;
  }
}

async function readWorkspaceFileSection(workspaceDir: string, relativePath: string): Promise<string | undefined> {
  const absolutePath = path.join(workspaceDir, relativePath);
  const content = await readTextIfExists(absolutePath);
  if (!content) {
    return undefined;
  }
  return renderSection(`Loaded from ${relativePath}`, content);
}

async function loadMemory(memoryPath: string): Promise<MediumMemoryRecord[]> {
  try {
    const raw = await readFile(memoryPath, "utf8");
    const entries: MediumMemoryRecord[] = [];
    for (const line of raw.split("\n")) {
      const trimmed = line.trim();
      if (!trimmed) {
        continue;
      }
      const parsed = parseJsonObject(trimmed);
      if (!parsed) {
        continue;
      }
      const normalized = normalizeRecord(parsed);
      if (normalized) {
        entries.push(normalized);
      }
    }
    return entries;
  } catch {
    return [];
  }
}

async function loadRecentJsonlLines(
  workspaceDir: string,
  relativePath: string,
  limit: number,
  title: string,
  maxChars?: number,
): Promise<string | undefined> {
  const absolutePath = path.join(workspaceDir, relativePath);
  const content = await readTextIfExists(absolutePath);
  if (!content) {
    return undefined;
  }

  const lines = content
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(-limit);
  const budgetedLines = keepRecentLinesWithinBudget(lines, maxChars);
  if (budgetedLines.length === 0) {
    return undefined;
  }

  return renderSection(title, budgetedLines.join("\n"));
}

async function loadRollingSummary(workspaceDir: string): Promise<string | undefined> {
  const absolutePath = path.join(workspaceDir, "memory/rolling_summary.json");
  const content = await readTextIfExists(absolutePath);
  if (!content) {
    return undefined;
  }

  const parsed = parseJsonObject(content);
  const summary = typeof parsed?.summary === "string" ? parsed.summary.trim() : "";
  if (!summary) {
    return undefined;
  }

  return renderSection("Rolling Summary", summary);
}

function renderProjectLine(project: Record<string, unknown>): string | null {
  const status = String(project.status ?? "").trim();
  if (status !== "active") {
    return null;
  }
  const title = String(project.title ?? "").trim();
  if (!title) {
    return null;
  }
  const phase = String(project.current_phase ?? "").trim();
  const startsAt = String(project.starts_at ?? "").trim();
  const nextActions = Array.isArray(project.next_actions)
    ? project.next_actions.map((item) => String(item).trim()).filter(Boolean).slice(0, 3)
    : [];
  const blockers = Array.isArray(project.blockers)
    ? project.blockers.map((item) => String(item).trim()).filter(Boolean).slice(0, 2)
    : [];
  const parts = [
    title,
    phase ? `phase: ${phase}` : "",
    startsAt ? `starts: ${startsAt}` : "",
    nextActions.length > 0 ? `next: ${nextActions.join("; ")}` : "",
    blockers.length > 0 ? `blocked by: ${blockers.join("; ")}` : "",
  ].filter(Boolean);
  return parts.join(" | ");
}

function renderProjectDetailLine(detail: Record<string, unknown>, projectTitle: string): string | null {
  if (String(detail.status ?? "").trim() !== "active") {
    return null;
  }
  const kind = compactField(detail.kind, 40);
  const title = compactField(detail.title, 100);
  const value = compactField(detail.value, 180);
  if (!projectTitle || (!title && !value)) {
    return null;
  }
  const startsAt = compactField(detail.starts_at, 80);
  const endsAt = compactField(detail.ends_at, 80);
  const parts = [
    projectTitle,
    kind ? `kind: ${kind}` : "",
    title ? `title: ${title}` : "",
    value ? `detail: ${value}` : "",
    startsAt ? `starts: ${startsAt}` : "",
    endsAt ? `ends: ${endsAt}` : "",
  ].filter(Boolean);
  return parts.join(" | ");
}

function jsonListLength(value: unknown): number {
  return Array.isArray(value) ? value.length : 0;
}

function compactField(value: unknown, maxChars = 140): string {
  const compact = String(value ?? "").replace(/\s+/g, " ").trim();
  if (compact.length <= maxChars) {
    return compact;
  }
  return `${compact.slice(0, maxChars - 1).trimEnd()}...`;
}

async function loadActiveProjects(workspaceDir: string): Promise<string | undefined> {
  const absolutePath = path.join(workspaceDir, PROJECTS_FILE);
  const content = await readTextIfExists(absolutePath);
  if (!content) {
    return undefined;
  }

  const lines = content
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  const projectLines: string[] = [];
  for (const line of lines) {
    const parsed = parseJsonObject(line);
    if (!parsed) {
      continue;
    }
    const rendered = renderProjectLine(parsed);
    if (rendered) {
      projectLines.push(rendered);
    }
    if (projectLines.length >= INTERACTIVE_PROJECT_LIMIT) {
      break;
    }
  }

  return renderBullets("Active Project Companion Context", projectLines);
}

async function loadActiveProjectDetails(workspaceDir: string): Promise<string | undefined> {
  const projectsContent = await readTextIfExists(path.join(workspaceDir, PROJECTS_FILE));
  const detailsContent = await readTextIfExists(path.join(workspaceDir, PROJECT_DETAILS_FILE));
  if (!projectsContent || !detailsContent) {
    return undefined;
  }

  const activeProjectsById = new Map<string, string>();
  for (const line of projectsContent.split("\n").map((item) => item.trim()).filter(Boolean)) {
    const project = parseJsonObject(line);
    const id = compactField(project?.id, 80);
    const title = compactField(project?.title, 120);
    const status = compactField(project?.status, 40);
    if (id && title && status === "active") {
      activeProjectsById.set(id, title);
    }
  }

  const detailLines: string[] = [];
  for (const line of detailsContent.split("\n").map((item) => item.trim()).filter(Boolean)) {
    const detail = parseJsonObject(line);
    if (!detail) {
      continue;
    }
    const projectId = compactField(detail.project_id, 80);
    const projectTitle = activeProjectsById.get(projectId);
    if (!projectTitle) {
      continue;
    }
    const rendered = renderProjectDetailLine(detail, projectTitle);
    if (rendered) {
      detailLines.push(rendered);
    }
    if (detailLines.length >= INTERACTIVE_PROJECT_DETAIL_LIMIT) {
      break;
    }
  }

  return renderBullets("Active Project Details", detailLines);
}

async function loadPendingProjectRuns(workspaceDir: string): Promise<string | undefined> {
  const runsPath = path.join(workspaceDir, PROJECT_RUNS_FILE);
  const runsContent = await readTextIfExists(runsPath);
  if (!runsContent) {
    return undefined;
  }

  const projectsById = new Map<string, string>();
  const projectsContent = await readTextIfExists(path.join(workspaceDir, PROJECTS_FILE));
  if (projectsContent) {
    for (const line of projectsContent.split("\n").map((item) => item.trim()).filter(Boolean)) {
      const parsed = parseJsonObject(line);
      const id = compactField(parsed?.id, 80);
      const title = compactField(parsed?.title, 120);
      if (id && title) {
        projectsById.set(id, title);
      }
    }
  }

  const pendingLines: string[] = [];
  for (const line of runsContent.split("\n").map((item) => item.trim()).filter(Boolean)) {
    const run = parseJsonObject(line);
    if (!run) {
      continue;
    }
    const status = compactField(run.status, 40);
    if (!PENDING_PROJECT_RUN_STATUSES.has(status)) {
      continue;
    }
    const projectId = compactField(run.project_id, 80);
    const projectTitle = projectsById.get(projectId) ?? projectId;
    const questions = Array.isArray(run.questions)
      ? run.questions.map((item) => compactField(item, 120)).filter(Boolean).slice(0, 2)
      : [];
    const proposedTaskCount = jsonListLength(run.proposed_tasks);
    const proposedEventCount = jsonListLength(run.proposed_calendar_events);
    const replyNeeded =
      status === "needs_input"
        ? "answer questions"
        : status === "pending_confirmation"
          ? "review/confirm proposal"
          : status === "failed"
            ? "review failure"
            : status === "queued" || status === "in_progress"
              ? "wait for worker"
              : "";
    const parts = [
      projectTitle,
      `status: ${status}`,
      compactField(run.request, 120) ? `request: ${compactField(run.request, 120)}` : "",
      compactField(run.summary, 160) ? `summary: ${compactField(run.summary, 160)}` : "",
      proposedTaskCount || proposedEventCount ? `proposal: ${proposedTaskCount} task(s), ${proposedEventCount} event(s)` : "",
      questions.length > 0 ? `questions: ${questions.join("; ")}` : "",
      replyNeeded ? `reply needed: ${replyNeeded}` : "",
    ].filter(Boolean);
    pendingLines.push(parts.join(" | "));
  }

  return renderBullets(
    "Pending Project Planning Runs",
    pendingLines.slice(-INTERACTIVE_PENDING_RUN_LIMIT),
  );
}

async function loadInteractiveMemory(workspaceDir: string): Promise<string | undefined> {
  const mediumMemoryPath = path.join(workspaceDir, MEDIUM_MEMORY_FILE);
  const longMemoryPath = path.join(workspaceDir, LONG_MEMORY_FILE);
  const mediumMemory = takeRecentEntries(
    (await loadMemory(mediumMemoryPath)).filter((entry) => !isExpired(entry)),
    INTERACTIVE_MEDIUM_LIMIT,
  );
  const longMemory = takeRecentEntries(await loadMemory(longMemoryPath), INTERACTIVE_LONG_LIMIT);
  const sections = [
    renderBullets(
      "Relevant Medium Memory",
      mediumMemory.map((entry) => entry.summary),
    ),
    renderBullets(
      "Relevant Long Memory",
      longMemory.map((entry) => entry.summary),
    ),
    await loadActiveProjects(workspaceDir),
    await loadActiveProjectDetails(workspaceDir),
    await loadPendingProjectRuns(workspaceDir),
  ].filter((section): section is string => Boolean(section));

  if (sections.length === 0) {
    return undefined;
  }
  return sections.join("\n\n");
}

async function loadHeartbeatContext(workspaceDir: string): Promise<string | undefined> {
  const sections = (
    await Promise.all([
      loadRecentJsonlLines(
        workspaceDir,
        ENGAGEMENT_MEMORY_FILE,
        HEARTBEAT_ENGAGEMENT_HISTORY_LIMIT,
        "Recent Engagement Sends",
        HEARTBEAT_HISTORY_MAX_CHARS,
      ),
      loadHeartbeatMediumMemory(workspaceDir),
    ])
  ).filter((section): section is string => Boolean(section));

  if (sections.length === 0) {
    return undefined;
  }

  return [
    "Heartbeat Context:\nUse this tiny snapshot only for warmth, relevance, and dedupe. Recent engagement sends mean Rumi should usually stay quiet. Fresh medium memory is only a small hint; do not turn it into a reminder unless it clearly makes the note feel more human.",
    ...sections,
  ].join("\n\n");
}

async function loadHeartbeatMediumMemory(workspaceDir: string): Promise<string | undefined> {
  const mediumMemoryPath = path.join(workspaceDir, MEDIUM_MEMORY_FILE);
  const mediumMemory = takeRecentEntries(
    (await loadMemory(mediumMemoryPath)).filter((entry) => !isExpired(entry)),
    HEARTBEAT_MEDIUM_MEMORY_LIMIT,
  );
  return renderBullets(
    "Fresh Medium Memory Hints",
    mediumMemory.map((entry) => entry.summary),
  )?.slice(0, HEARTBEAT_MEDIUM_MEMORY_MAX_CHARS);
}

async function loadProactiveMediumMemory(workspaceDir: string): Promise<string | undefined> {
  const mediumMemoryPath = path.join(workspaceDir, MEDIUM_MEMORY_FILE);
  const mediumMemory = takeRecentEntries(
    (await loadMemory(mediumMemoryPath)).filter((entry) => !isExpired(entry)),
    PROACTIVE_MEDIUM_LIMIT,
  );
  return renderBullets(
    "Recent Medium Memory Candidates",
    mediumMemory.map((entry) => entry.summary),
  );
}

async function loadProactiveLongMemory(workspaceDir: string): Promise<string | undefined> {
  const longMemoryPath = path.join(workspaceDir, LONG_MEMORY_FILE);
  const longMemory = takeRecentEntries(await loadMemory(longMemoryPath), PROACTIVE_LONG_LIMIT);
  return renderBullets(
    "Recent Long Memory Candidates",
    longMemory.map((entry) => entry.summary),
  );
}

/**
 * Named dynamic loaders that cron frontmatter can reference by id.
 * Add new ids here and they become declaratively available.
 *
 * The previous hard-coded `createCronProfiles()` is gone — cron prompts now
 * declare their own `dynamic:` list via frontmatter (see `parseCronFrontmatter`).
 */
const NAMED_LOADERS: Record<string, DynamicLoader> = {
  rolling_summary: loadRollingSummary,
  active_projects: loadActiveProjects,
  proactive_medium_memory: loadProactiveMediumMemory,
  proactive_long_memory: loadProactiveLongMemory,
  active_priorities: async (workspaceDir: string) =>
    readWorkspaceFileSection(workspaceDir, "memory/ACTIVE_PRIORITIES.md"),
  proactive_engagement_history: async (workspaceDir: string) =>
    loadRecentJsonlLines(
      workspaceDir,
      ENGAGEMENT_MEMORY_FILE,
      PROACTIVE_ENGAGEMENT_HISTORY_LIMIT,
      "Recent Engagement History",
    ),
  consolidation_medium_memory: async (workspaceDir: string) =>
    loadRecentJsonlLines(workspaceDir, MEDIUM_MEMORY_FILE, Number.MAX_SAFE_INTEGER, "Medium Memory"),
  consolidation_long_memory: async (workspaceDir: string) =>
    loadRecentJsonlLines(workspaceDir, LONG_MEMORY_FILE, Number.MAX_SAFE_INTEGER, "Long Memory"),
};

function resolveDynamicLoader(spec: DynamicSpec): DynamicLoader | null {
  if (typeof spec === "string") {
    return NAMED_LOADERS[spec] ?? null;
  }
  if (spec.kind === "file") {
    const relative = spec.path;
    return async (workspaceDir: string) => readWorkspaceFileSection(workspaceDir, relative);
  }
  if (spec.kind === "jsonl_tail") {
    const { path: relative, limit, title } = spec;
    const effectiveLimit = limit && limit > 0 ? limit : Number.MAX_SAFE_INTEGER;
    const effectiveTitle = title ?? `Recent ${relative}`;
    return async (workspaceDir: string) =>
      loadRecentJsonlLines(workspaceDir, relative, effectiveLimit, effectiveTitle);
  }
  return null;
}

function buildCronProfileFromPrompt(prompt: string): CronProfile {
  const parsed = parseCronFrontmatter(prompt);
  const dynamicLoaders: DynamicLoader[] = [];
  for (const spec of parsed.dynamic) {
    const loader = resolveDynamicLoader(spec);
    if (loader) {
      dynamicLoaders.push(loader);
    }
  }
  return {
    systemFiles: parsed.systemFiles,
    dynamicLoaders,
  };
}

async function buildSystemSections(workspaceDir: string, relativePaths: string[]): Promise<string[]> {
  const sections = await Promise.all(
    relativePaths.map((relativePath) => readWorkspaceFileSection(workspaceDir, relativePath)),
  );
  return sections.filter((section): section is string => Boolean(section));
}

async function buildCronContext(
  workspaceDir: string,
  prompt: string,
): Promise<{ systemSections: string[]; contextSections: string[] }> {
  // Cron profile is derived from prompt frontmatter. Cron launcher messages may
  // reference a workspace cron file, so resolve that file before parsing.
  const cronPrompt = await resolveCronPrompt(workspaceDir, prompt);
  if (!parseCronId(cronPrompt)) {
    return { systemSections: [], contextSections: [] };
  }

  const profile = buildCronProfileFromPrompt(cronPrompt);
  const systemSections = await buildSystemSections(workspaceDir, profile.systemFiles);
  const dynamicSections = await Promise.all(
    profile.dynamicLoaders.map((loader) => loader(workspaceDir)),
  );
  return {
    systemSections,
    contextSections: dynamicSections.filter((section): section is string => Boolean(section)),
  };
}

async function buildPromptInjection(event: unknown, context: unknown) {
  const workspaceDir = resolveWorkspaceDir(context, event);
  const mode = resolveMode(context);
  const systemSections: string[] = [];
  const contextSections: string[] = [];

  if (mode === "interactive") {
    systemSections.push(
      ...(await buildSystemSections(workspaceDir, [
        ...INTERACTIVE_SYSTEM_FILES,
        ...INTERACTIVE_CAPABILITY_FILES,
      ])),
    );
    const memorySection = await loadInteractiveMemory(workspaceDir);
    if (memorySection) {
      contextSections.push(memorySection);
    }
  }

  if (mode === "heartbeat") {
    systemSections.push(...(await buildSystemSections(workspaceDir, HEARTBEAT_SYSTEM_FILES)));
    const heartbeatContext = await loadHeartbeatContext(workspaceDir);
    if (heartbeatContext) {
      contextSections.push(heartbeatContext);
    }
  }

  if (mode === "cron") {
    const prompt = typeof (event as Record<string, unknown>).prompt === "string"
      ? String((event as Record<string, unknown>).prompt)
      : "";
    const cronContext = await buildCronContext(workspaceDir, prompt);
    systemSections.push(...cronContext.systemSections);
    contextSections.push(...cronContext.contextSections);
  }

  if (systemSections.length === 0 && contextSections.length === 0) {
    return undefined;
  }

  return {
    prependSystemContext: systemSections.length > 0 ? systemSections.join("\n\n") : undefined,
    prependContext: contextSections.length > 0 ? contextSections.join("\n\n") : undefined,
  };
}

async function runSkillDecision(payload: unknown, workspaceDir: string): Promise<MemoryDecision> {
  const data = payload as Record<string, unknown>;
  const userMessage = extractLatestUserMessage(data);
  const assistantResponse = extractLatestAssistantReply(data);
  if (!userMessage || !assistantResponse) {
    return {
      should_store: false,
      summary: "",
      expires_in_days: 7,
    };
  }

  const skillPath = path.join(workspaceDir, SKILL_FILE);
  const skillInput = { userMessage, assistantResponse };
  const candidates = [
    data.runSkill,
    (data.runtime as Record<string, unknown> | undefined)?.runSkill,
    (data.api as Record<string, unknown> | undefined)?.runSkill,
    ((data.runtime as Record<string, unknown> | undefined)?.skills as Record<string, unknown> | undefined)
      ?.run,
  ];

  for (const candidate of candidates) {
    if (typeof candidate !== "function") {
      continue;
    }
    try {
      const result = await candidate(skillPath, skillInput);
      const normalized = normalizeDecisionFromUnknown(result);
      if (normalized) {
        return normalized;
      }
    } catch {
      // Keep trying compatible runtime signatures.
    }

    try {
      const result = await candidate({ skill: skillPath, input: skillInput });
      const normalized = normalizeDecisionFromUnknown(result);
      if (normalized) {
        return normalized;
      }
    } catch {
      // Keep trying compatible runtime signatures.
    }
  }

  return {
    should_store: false,
    summary: "",
    expires_in_days: 7,
  };
}

function normalizeDecisionFromUnknown(value: unknown): MemoryDecision | null {
  if (!value) {
    return null;
  }

  if (typeof value === "string") {
    const parsed = parsePossiblyWrappedJson(value);
    return parsed ? normalizeDecision(parsed) : null;
  }

  if (typeof value === "object") {
    const objectValue = value as Record<string, unknown>;
    const direct = normalizeDecision(objectValue);
    if (direct.summary || direct.should_store) {
      return direct;
    }

    const content = objectValue.content;
    if (typeof content === "string") {
      const parsed = parsePossiblyWrappedJson(content);
      return parsed ? normalizeDecision(parsed) : null;
    }
  }

  return null;
}

export default definePluginEntry({
  id: "workspace-medium-memory",
  name: "Workspace Context Loader",
  description: "Loads frugal mode-aware workspace context and stores medium-term memory",
  register(api) {
    api.on("before_prompt_build", async (event: unknown, context: unknown) =>
      buildPromptInjection(event, context),
    );

    api.on("agent_end", async (payload: unknown, context: unknown) => {
      const workspaceDir = resolveWorkspaceDir(context, payload);
      const decision = await runSkillDecision(payload, workspaceDir);
      const mediumMemoryPath = path.join(workspaceDir, MEDIUM_MEMORY_FILE);
      const longMemoryPath = path.join(workspaceDir, LONG_MEMORY_FILE);
      const createdAt = isoDateNow();
      if (decision.should_store && decision.summary) {
        const existingMedium = await loadMemory(mediumMemoryPath);
        const existingLong = await loadMemory(longMemoryPath);
        const duplicate = [...existingMedium, ...existingLong].some(
          (entry) => entry.summary.toLowerCase().trim() === decision.summary.toLowerCase().trim(),
        );

        if (!duplicate) {
          const record: MediumMemoryRecord = {
            summary: normalizeSummary(decision.summary),
            created_at: createdAt,
            expires_at: addDays(createdAt, decision.expires_in_days),
          };

          await mkdir(path.dirname(mediumMemoryPath), { recursive: true });
          await appendFile(mediumMemoryPath, `${JSON.stringify(record)}\n`, "utf8");
        }
      }

      return undefined;
    });
  },
});
