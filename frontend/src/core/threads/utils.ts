import type { Message } from "@langchain/langgraph-sdk";

import type { AgentThread, AgentThreadContext } from "./types";

export type ChannelThreadSource = {
  type: "im_channel";
  provider: string;
  label: string;
};

type ThreadRouteTarget =
  | string
  | {
      thread_id: string;
      context?: Pick<AgentThreadContext, "agent_name"> | null;
      metadata?: Record<string, unknown> | null;
    };

export function pathOfThread(
  thread: ThreadRouteTarget,
  _context?: Pick<AgentThreadContext, "agent_name"> | null,
) {
  const threadId = typeof thread === "string" ? thread : thread.thread_id;
  const encodedThreadId = encodeURIComponent(threadId);
  return `/workspace/chats/${encodedThreadId}`;
}

export function textOfMessage(message: Message) {
  if (typeof message.content === "string") {
    return message.content;
  } else if (Array.isArray(message.content)) {
    // Flat join ("") for single-line consumers (input box, titles); the rendered
    // body uses extractContentFromMessage, which joins multi-part content with "\n".
    const text = message.content
      .map((part) =>
        typeof part === "string" ? part : part.type === "text" ? part.text : "",
      )
      .join("");
    return text.length > 0 ? text : null;
  }
  return null;
}

const INTERNAL_THREAD_TITLE_RE =
  /<uploaded_files>|<slash_skill_activation>|【视频工作台操作上下文】|(?:^|\b)personal_ip_[a-z0-9_]+|(?:production|account|provider_task|candidate|shot|asset|event|revision)_id\s*=|SKILL\.md|\/mnt\/(?:user-data|skills)\//i;

export function visibleThreadTitle(
  title: string | null | undefined,
  fallback = "Untitled",
) {
  const normalized = title?.replace(/\s+/g, " ").trim();
  if (!normalized || INTERNAL_THREAD_TITLE_RE.test(normalized)) {
    return fallback;
  }
  return normalized;
}

export function titleOfThread(thread: AgentThread, fallback = "Untitled") {
  const metadataTitle = thread.metadata?.title;
  const topLevelTitle = Reflect.get(thread, "title");
  const title =
    thread.values?.title ??
    (typeof metadataTitle === "string" ? metadataTitle : undefined) ??
    (typeof topLevelTitle === "string" ? topLevelTitle : undefined);
  return visibleThreadTitle(title, fallback);
}

const CHANNEL_PROVIDER_LABELS: Record<string, string> = {
  dingtalk: "DingTalk",
  discord: "Discord",
  feishu: "Feishu",
  slack: "Slack",
  telegram: "Telegram",
  wechat: "WeChat",
  wecom: "WeCom",
};

function labelOfChannelProvider(provider: string) {
  return CHANNEL_PROVIDER_LABELS[provider] ?? provider;
}

export function channelSourceOfThread(
  thread: Pick<AgentThread, "metadata">,
): ChannelThreadSource | null {
  const source = thread.metadata?.channel_source;
  if (!source || typeof source !== "object" || Array.isArray(source)) {
    return null;
  }

  if (Reflect.get(source, "type") !== "im_channel") {
    return null;
  }

  const provider = Reflect.get(source, "provider");
  if (typeof provider !== "string" || provider.trim().length === 0) {
    return null;
  }

  const normalizedProvider = provider.trim().toLowerCase();
  return {
    type: "im_channel",
    provider: normalizedProvider,
    label: labelOfChannelProvider(normalizedProvider),
  };
}
