import type { Message } from "@langchain/langgraph-sdk";
import { expect, test } from "@rstest/core";

import {
  channelSourceOfThread,
  pathOfThread,
  textOfMessage,
  titleOfThread,
  visibleThreadTitle,
} from "@/core/threads/utils";

test("uses standard chat route when thread has no agent context", () => {
  expect(pathOfThread("thread-123")).toBe("/workspace/chats/thread-123");
  expect(
    pathOfThread({
      thread_id: "thread-123",
    }),
  ).toBe("/workspace/chats/thread-123");
});

test("encodes thread ids in standard chat routes", () => {
  expect(pathOfThread("thread#1?draft")).toBe(
    "/workspace/chats/thread%231%3Fdraft",
  );
});

test("keeps agent-backed threads in the standard user conversation route", () => {
  expect(pathOfThread("thread#1?draft", { agent_name: "researcher" })).toBe(
    "/workspace/chats/thread%231%3Fdraft",
  );
  expect(
    pathOfThread({
      thread_id: "thread-123",
      context: { agent_name: "researcher" },
    }),
  ).toBe("/workspace/chats/thread-123");
  expect(pathOfThread("thread-123", { agent_name: "ops agent" })).toBe(
    "/workspace/chats/thread-123",
  );
  expect(
    pathOfThread({
      thread_id: "thread-456",
      metadata: { agent_name: "coder" },
    }),
  ).toBe("/workspace/chats/thread-456");
  expect(
    pathOfThread({
      thread_id: "thread-789",
      context: { agent_name: "from-context" },
      metadata: { agent_name: "from-metadata" },
    }),
  ).toBe("/workspace/chats/thread-789");
});

test("reads IM channel source metadata", () => {
  expect(
    channelSourceOfThread({
      metadata: {
        channel_source: {
          type: "im_channel",
          provider: "feishu",
          chat_id: "oc_123",
        },
      },
    }),
  ).toEqual({
    type: "im_channel",
    provider: "feishu",
    label: "Feishu",
  });
});

test("ignores threads without valid IM channel source metadata", () => {
  expect(channelSourceOfThread({ metadata: {} })).toBeNull();
  expect(
    channelSourceOfThread({
      metadata: { channel_source: { provider: "" } },
    }),
  ).toBeNull();
  expect(
    channelSourceOfThread({
      metadata: {
        channel_source: {
          type: "other",
          provider: "feishu",
        },
      },
    }),
  ).toBeNull();
});

test("textOfMessage concatenates object and bare-string content parts", () => {
  // Gemini's finalized shape: first signed {type:text} block + bare-string
  // continuation. textOfMessage joins flat ("") for single-line consumers.
  const message = {
    id: "ai-1",
    type: "ai",
    content: [
      {
        type: "text",
        text: "First block.",
        extras: { signature: "abc123" },
        index: 0,
      },
      " Continuation as a bare string.",
    ],
  } as unknown as Message;

  expect(textOfMessage(message)).toBe(
    "First block. Continuation as a bare string.",
  );
});

test("textOfMessage returns null when array content has no text", () => {
  const message = {
    id: "ai-1",
    type: "ai",
    content: [{ type: "image_url", image_url: "https://example.com/x.png" }],
  } as unknown as Message;

  expect(textOfMessage(message)).toBeNull();
});

test("hides internal execution context from customer-facing titles", () => {
  expect(
    visibleThreadTitle(
      "【视频工作台操作上下文】 production_id=video-production-1",
      "未命名",
    ),
  ).toBe("未命名");
  expect(
    visibleThreadTitle(
      "调用 personal_ip_select_browser_account，account_id=account-1",
      "未命名",
    ),
  ).toBe("未命名");
  expect(
    visibleThreadTitle(
      "<uploaded_files> The following files were uploaded",
      "未命名",
    ),
  ).toBe("未命名");
  expect(visibleThreadTitle("帮我复盘今天的作品", "未命名")).toBe(
    "帮我复盘今天的作品",
  );
});

test("reads customer-visible titles from current and legacy thread shapes", () => {
  expect(
    titleOfThread({
      thread_id: "thread-values",
      values: { title: "First conversation" },
    } as never),
  ).toBe("First conversation");
  expect(
    titleOfThread({
      thread_id: "thread-top-level",
      title: "Second conversation",
    } as never),
  ).toBe("Second conversation");
});
