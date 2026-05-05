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

function stripLeadingProcessNarration(content: string): { content: string; changed: boolean } {
  const trimmed = content.trim();
  const directPrefixPatterns = [
    /^Perfect\.\s+Now I(?:'ll| will)\s+build the digest\.[\s\S]*?:\s*/i,
    /^Now I(?:'ll| will)\s+build the digest\.[\s\S]*?:\s*/i,
    /^I(?:'ll| will)\s+mark[\s\S]*?digest\.[\s\S]*?(?=(?:NO_REPLY\b|On\s+|\u{1F4E7}))/iu,
    /^Now I(?:'ll| will)\s+classify[\s\S]*?(?=(?:NO_REPLY\b|On\s+|\u{1F4E7}))/iu,
  ];

  for (const pattern of directPrefixPatterns) {
    const next = trimmed.replace(pattern, "").trim();
    if (next !== trimmed && next.length > 0) {
      return { content: next, changed: true };
    }
  }

  const paragraphs = trimmed.split(/\n{2,}/);
  if (paragraphs.length < 2) {
    return { content, changed: false };
  }

  const [firstParagraph, ...rest] = paragraphs;
  const startsLikeProcessNarration =
    /^(?:Perfect\.\s*)?(?:Now\s+)?(?:I(?:'ll| will)|Let me)\b/i.test(firstParagraph);
  const describesWork =
    /\b(?:mark|record|build|classif|digest|check|read|fetch|search|run|use|call|handle|draft|summariz|process)\b/i.test(
      firstParagraph,
    );

  if (!startsLikeProcessNarration || !describesWork) {
    return { content, changed: false };
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
    return undefined;
  }

  if (finalContent !== content.trim()) {
    return { content: finalContent };
  }

  return undefined;
}

export default definePluginEntry({
  id: "output-hygiene-plugin",
  name: "Rumi Output Hygiene",
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
