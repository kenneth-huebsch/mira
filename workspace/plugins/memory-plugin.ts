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

type EngagementPriorityRecord = {
  topic: string;
  kind: "accountability" | "relationship" | "general";
  prompt: string;
  created_at: string;
  expires_at: string;
};

type EngagementPriorityDecision = {
  should_store: boolean;
  topic: string;
  kind: "accountability" | "relationship" | "general";
  prompt: string;
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
const ENGAGEMENT_PRIORITIES_FILE = "memory/engagement_priorities.jsonl";
const SKILL_FILE = "skills/memory_manager.md";
const ENGAGEMENT_PRIORITIES_SKILL_FILE = "skills/engagement_priorities_manager.md";
const MAX_SUMMARY_LENGTH = 140;
const MAX_TOPIC_LENGTH = 80;
const MAX_PRIORITY_PROMPT_LENGTH = 160;
const INTERACTIVE_MEDIUM_LIMIT = 8;
const INTERACTIVE_LONG_LIMIT = 4;
const PROACTIVE_ENGAGEMENT_HISTORY_LIMIT = 20;
const PROACTIVE_MEDIUM_LIMIT = 10;
// OpenClaw's bootstrap auto-injects AGENTS.md, SOUL.md, IDENTITY.md, USER.md,
// TOOLS.md, and HEARTBEAT.md on every run, so the plugin no longer re-injects
// any system files for interactive or heartbeat mode. The plugin's interactive
// job is now purely "inject dynamic memory snapshots."
const INTERACTIVE_SYSTEM_FILES: string[] = [];
const HEARTBEAT_SYSTEM_FILES: string[] = [];

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

function normalizeTopic(text: string): string {
  const compact = text
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return compact.slice(0, MAX_TOPIC_LENGTH);
}

function normalizePriorityPrompt(text: string): string {
  const compact = text.replace(/\s+/g, " ").trim();
  return compact.slice(0, MAX_PRIORITY_PROMPT_LENGTH);
}

function normalizePriorityKind(value: unknown): "accountability" | "relationship" | "general" {
  const kind = String(value ?? "").trim().toLowerCase();
  switch (kind) {
    case "accountability":
    case "relationship":
    case "general":
      return kind;
    default:
      return "general";
  }
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

function normalizeEngagementPriorityRecord(
  input: Record<string, unknown>,
): EngagementPriorityRecord | null {
  const topic = normalizeTopic(String(input.topic ?? ""));
  const prompt = normalizePriorityPrompt(String(input.prompt ?? ""));
  const createdAt = String(input.created_at ?? "").trim();
  const expiresAt = String(input.expires_at ?? "").trim();

  if (!topic || !prompt || !createdAt || !expiresAt) {
    return null;
  }

  return {
    topic,
    kind: normalizePriorityKind(input.kind),
    prompt,
    created_at: createdAt,
    expires_at: expiresAt,
  };
}

function normalizeEngagementPriorityDecision(
  input: Record<string, unknown>,
): EngagementPriorityDecision {
  const topic = normalizeTopic(String(input.topic ?? ""));
  const prompt = normalizePriorityPrompt(String(input.prompt ?? ""));
  return {
    should_store: Boolean(input.should_store) && topic.length > 0 && prompt.length > 0,
    topic,
    kind: normalizePriorityKind(input.kind),
    prompt,
    expires_in_days: clamp(Number(input.expires_in_days ?? 30), 3, 90),
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

async function loadEngagementPriorities(memoryPath: string): Promise<EngagementPriorityRecord[]> {
  try {
    const raw = await readFile(memoryPath, "utf8");
    const entries: EngagementPriorityRecord[] = [];
    for (const line of raw.split("\n")) {
      const trimmed = line.trim();
      if (!trimmed) {
        continue;
      }
      const parsed = parseJsonObject(trimmed);
      if (!parsed) {
        continue;
      }
      const normalized = normalizeEngagementPriorityRecord(parsed);
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
  if (lines.length === 0) {
    return undefined;
  }

  return renderSection(title, lines.join("\n"));
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
  ].filter((section): section is string => Boolean(section));

  if (sections.length === 0) {
    return undefined;
  }
  return sections.join("\n\n");
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

/**
 * Named dynamic loaders that cron frontmatter can reference by id.
 * Add new ids here and they become declaratively available.
 *
 * The previous hard-coded `createCronProfiles()` is gone — cron prompts now
 * declare their own `dynamic:` list via frontmatter (see `parseCronFrontmatter`).
 */
const NAMED_LOADERS: Record<string, DynamicLoader> = {
  rolling_summary: loadRollingSummary,
  proactive_medium_memory: loadProactiveMediumMemory,
  active_priorities: async (workspaceDir: string) =>
    readWorkspaceFileSection(workspaceDir, "memory/ACTIVE_PRIORITIES.md"),
  proactive_engagement_priorities: async (workspaceDir: string) =>
    loadRecentJsonlLines(
      workspaceDir,
      ENGAGEMENT_PRIORITIES_FILE,
      Number.MAX_SAFE_INTEGER,
      "Engagement Priorities",
    ),
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
  // Cron profile is now derived from the prompt's frontmatter directly. A cron
  // prompt without a `cron_id` (or with no `system_files:` / `dynamic:` keys)
  // gets no plugin-injected context — that's a feature, not a bug.
  if (!parseCronId(prompt)) {
    return { systemSections: [], contextSections: [] };
  }

  const profile = buildCronProfileFromPrompt(prompt);
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
    systemSections.push(...(await buildSystemSections(workspaceDir, INTERACTIVE_SYSTEM_FILES)));
    const memorySection = await loadInteractiveMemory(workspaceDir);
    if (memorySection) {
      contextSections.push(memorySection);
    }
  }

  if (mode === "heartbeat") {
    systemSections.push(...(await buildSystemSections(workspaceDir, HEARTBEAT_SYSTEM_FILES)));
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

async function runEngagementPrioritySkill(
  payload: unknown,
  workspaceDir: string,
): Promise<EngagementPriorityDecision> {
  const data = payload as Record<string, unknown>;
  const userMessage = extractLatestUserMessage(data);
  const assistantResponse = extractLatestAssistantReply(data);
  if (!userMessage || !assistantResponse) {
    return {
      should_store: false,
      topic: "",
      kind: "general",
      prompt: "",
      expires_in_days: 30,
    };
  }

  const skillPath = path.join(workspaceDir, ENGAGEMENT_PRIORITIES_SKILL_FILE);
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
      const normalized = normalizeEngagementPriorityDecisionFromUnknown(result);
      if (normalized) {
        return normalized;
      }
    } catch {
      // Keep trying compatible runtime signatures.
    }

    try {
      const result = await candidate({ skill: skillPath, input: skillInput });
      const normalized = normalizeEngagementPriorityDecisionFromUnknown(result);
      if (normalized) {
        return normalized;
      }
    } catch {
      // Keep trying compatible runtime signatures.
    }
  }

  return {
    should_store: false,
    topic: "",
    kind: "general",
    prompt: "",
    expires_in_days: 30,
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

function normalizeEngagementPriorityDecisionFromUnknown(
  value: unknown,
): EngagementPriorityDecision | null {
  if (!value) {
    return null;
  }

  if (typeof value === "string") {
    const parsed = parsePossiblyWrappedJson(value);
    return parsed ? normalizeEngagementPriorityDecision(parsed) : null;
  }

  if (typeof value === "object") {
    const objectValue = value as Record<string, unknown>;
    const direct = normalizeEngagementPriorityDecision(objectValue);
    if (direct.topic || direct.prompt || direct.should_store) {
      return direct;
    }

    const content = objectValue.content;
    if (typeof content === "string") {
      const parsed = parsePossiblyWrappedJson(content);
      return parsed ? normalizeEngagementPriorityDecision(parsed) : null;
    }
  }

  return null;
}

export default definePluginEntry({
  id: "workspace-medium-memory",
  name: "Workspace Context Loader",
  description: "Loads frugal mode-aware workspace context and stores medium-term memory",
  register(api) {
    api.registerHook(["before_prompt_build"], async (event: unknown, context: unknown) =>
      buildPromptInjection(event, context),
    );

    api.registerHook(["agent_end"], async (payload: unknown, context: unknown) => {
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

      const priorityDecision = await runEngagementPrioritySkill(payload, workspaceDir);
      if (!priorityDecision.should_store || !priorityDecision.topic || !priorityDecision.prompt) {
        return undefined;
      }

      const engagementPrioritiesPath = path.join(workspaceDir, ENGAGEMENT_PRIORITIES_FILE);
      const existingPriorities = await loadEngagementPriorities(engagementPrioritiesPath);
      const hasTopic = existingPriorities.some(
        (entry) => entry.topic.toLowerCase().trim() === priorityDecision.topic.toLowerCase().trim(),
      );
      if (hasTopic) {
        return undefined;
      }

      const priorityRecord: EngagementPriorityRecord = {
        topic: priorityDecision.topic,
        kind: priorityDecision.kind,
        prompt: priorityDecision.prompt,
        created_at: createdAt,
        expires_at: addDays(createdAt, priorityDecision.expires_in_days),
      };

      await mkdir(path.dirname(engagementPrioritiesPath), { recursive: true });
      await appendFile(engagementPrioritiesPath, `${JSON.stringify(priorityRecord)}\n`, "utf8");
      return undefined;
    });
  },
});
