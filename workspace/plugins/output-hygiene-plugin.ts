import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

type MessageSendingEvent = {
  content?: unknown;
  metadata?: unknown;
};

type MessageContext = {
  channelId?: unknown;
};

type HygieneResult =
  | {
      content?: string;
      cancel?: boolean;
    }
  | undefined;

const EMAIL_DIGEST_MARKER = "\u{1F4E7}";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isTelegramOutbound(event: MessageSendingEvent, context: MessageContext): boolean {
  const metadataChannel = isRecord(event.metadata) ? event.metadata.channel : undefined;
  return metadataChannel === "telegram" || context.channelId === "telegram";
}

function stripToolCallMarkup(content: string): { content: string; changed: boolean } {
  let next = content;

  for (const pattern of [
    /```(?:xml)?\s*<tool_call\b[\s\S]*?<\/tool_call>\s*```/gi,
    /<tool_call\b[\s\S]*?<\/tool_call>/gi,
    /<function_call\b[\s\S]*?<\/function_call>/gi,
  ]) {
    next = next.replace(pattern, "");
  }

  return {
    content: next.trim(),
    changed: next !== content,
  };
}

function isClassifierVerdictParagraph(content: string): boolean {
  return (
    /^Classifying:\s+/i.test(content) &&
    /\b(?:worth_knowing|not_worth_knowing|NO_REPLY)\b/i.test(content)
  );
}

function isProcessNarrationParagraph(content: string): boolean {
  const mentionsInternalSidecar = /\bsidecar\b/i.test(content);
  const startsLikeProcessNarration =
    /^(?:Good\.\s+I can see|(?:Now\s+)?I\s+need\b|I found\b|Looking at\b|The search\b|This email\b|This is\b|Since\b|(?:Perfect\.\s*)?(?:Now\s+)?(?:I(?:'ll| will)|Let me)\b)/i.test(
      content,
    );
  const describesWork =
    /\b(?:mark|record|build|classif|digest|check|read|fetch|search|run|use|call|handle|draft|summariz|process|preflight|header|mailbox|triage|state file|tool|cron|heartbeat|finali[sz]e|skip|verify)\b/i.test(
      content,
    );

  return (
    mentionsInternalSidecar ||
    isClassifierVerdictParagraph(content) ||
    (startsLikeProcessNarration && describesWork)
  );
}

function hasProcessNarration(content: string): boolean {
  if (
    /\b(?:Good\.\s+I can see|I need to|Now I need|Let me finali[sz]e|Now let me|Looking at the headers|build the digest|tool_call|function_call|sidecar|preflight|state file|cron wake)\b/i.test(
      content,
    )
  ) {
    return true;
  }

  return content
    .split(/\n{2,}/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean)
    .some(isProcessNarrationParagraph);
}

function stripBeforeFinalMarker(content: string): { content: string; changed: boolean } {
  for (const marker of [`NO_REPLY`, EMAIL_DIGEST_MARKER]) {
    const markerIndex = content.indexOf(marker);
    if (markerIndex <= 0) {
      continue;
    }

    const prefix = content.slice(0, markerIndex).trim();
    const candidate = content.slice(markerIndex).trim();
    if (prefix.length > 0 && candidate.length > 0 && hasProcessNarration(prefix)) {
      return { content: candidate, changed: true };
    }
  }

  return { content, changed: false };
}

function stripLeadingProcessNarration(content: string): { content: string; changed: boolean } {
  const trimmed = content.trim();
  const directPrefixPatterns = [
    /^Good\.\s+I can see[\s\S]*?(?=(?:NO_REPLY\b|\u{1F4E7}))/iu,
    /^(?:Now\s+)?I\s+need[\s\S]*?(?=(?:NO_REPLY\b|\u{1F4E7}))/iu,
    /^Looking at the headers[\s\S]*?(?=(?:NO_REPLY\b|\u{1F4E7}))/iu,
    /^Let me finali[sz]e[\s\S]*?(?=(?:NO_REPLY\b|\u{1F4E7}))/iu,
    /^Perfect\.\s+Now I(?:'ll| will)\s+build the digest\.[\s\S]*?:\s*/i,
    /^Now I(?:'ll| will)\s+build the digest\.[\s\S]*?:\s*/i,
    /^I(?:'ll| will)\s+mark[\s\S]*?digest\.[\s\S]*?(?=(?:NO_REPLY\b|On\s+|\u{1F4E7}))/iu,
    /^Now I(?:'ll| will)\s+classify[\s\S]*?(?=(?:NO_REPLY\b|On\s+|\u{1F4E7}))/iu,
    /^Classifying:[\s\S]*?\b(?:worth_knowing|not_worth_knowing|NO_REPLY)\b\.?\s*(?=(?:NO_REPLY\b|On\s+|\u{1F4E7}))/iu,
  ];

  for (const pattern of directPrefixPatterns) {
    const next = trimmed.replace(pattern, "").trim();
    if (next !== trimmed && next.length > 0) {
      return { content: next, changed: true };
    }
  }

  const markerStripped = stripBeforeFinalMarker(trimmed);
  if (markerStripped.changed) {
    return markerStripped;
  }

  const paragraphs = trimmed.split(/\n{2,}/);
  const [firstParagraph, ...rest] = paragraphs;
  if (!isProcessNarrationParagraph(firstParagraph)) {
    return { content, changed: false };
  }

  if (paragraphs.length < 2) {
    return { content: "", changed: true };
  }

  const next = rest.join("\n\n").trim();
  return next.length > 0 ? { content: next, changed: true } : { content, changed: false };
}

function cleanOutboundContent(content: string): HygieneResult {
  const withoutToolMarkup = stripToolCallMarkup(content);
  if (withoutToolMarkup.changed && withoutToolMarkup.content.length === 0) {
    return { cancel: true };
  }

  const withoutNarration = stripLeadingProcessNarration(withoutToolMarkup.content);
  const finalContent = withoutNarration.content.trim();

  if (finalContent.length === 0) {
    if (withoutNarration.changed) {
      return { cancel: true };
    }

    return undefined;
  }

  if (finalContent !== content.trim()) {
    return { content: finalContent };
  }

  return undefined;
}

export default definePluginEntry({
  id: "output-hygiene-plugin",
  name: "Mira Output Hygiene",
  description: "Filters obvious tool-call markup and process narration before Telegram delivery",
  register(api) {
    api.on(
      "message_sending",
      (event: unknown, context: unknown) => {
        const messageEvent = isRecord(event) ? (event as MessageSendingEvent) : {};
        const messageContext = isRecord(context) ? (context as MessageContext) : {};
        if (!isTelegramOutbound(messageEvent, messageContext)) {
          return undefined;
        }

        if (typeof messageEvent.content !== "string") {
          return undefined;
        }

        return cleanOutboundContent(messageEvent.content);
      },
    );
  },
});
