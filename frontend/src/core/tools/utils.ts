import type { ToolCall } from "@langchain/core/messages";
import type { AIMessage } from "@langchain/langgraph-sdk";

import type { Translations } from "../i18n";
import { hasToolCalls } from "../messages/utils";
import { isInternalSkillToolCall } from "../skills";

export function explainLastToolCall(message: AIMessage, t: Translations) {
  if (hasToolCalls(message)) {
    const lastToolCall = message.tool_calls![message.tool_calls!.length - 1]!;
    return explainToolCall(lastToolCall, t);
  }
  return t.common.thinking;
}

export function explainToolCall(
  toolCall: Pick<ToolCall, "name" | "args">,
  t: Translations,
) {
  if (
    isInternalSkillToolCall(
      toolCall.name,
      (toolCall.args ?? {}) as Record<string, unknown>,
    )
  ) {
    return t.common.thinking;
  } else if (
    toolCall.name === "personal_ip_collect_browser_page" ||
    toolCall.name === "personal_ip_collect_douyin_browser_page"
  ) {
    return t.toolCalls.personalIpCollectingAccount;
  } else if (
    toolCall.name === "personal_ip_collect_browser_portfolio_today" ||
    toolCall.name === "personal_ip_sync_douyin_portfolio" ||
    toolCall.name === "personal_ip_sync_douyin_post"
  ) {
    return t.toolCalls.personalIpCollectingPortfolio;
  } else if (toolCall.name === "personal_ip_metrics_aggregate") {
    return t.toolCalls.personalIpAggregating;
  } else if (
    toolCall.name === "personal_ip_performance_inventory" ||
    toolCall.name === "personal_ip_platform_observation_inventory" ||
    toolCall.name === "personal_ip_read_platform_observation" ||
    toolCall.name === "personal_ip_read_retrospective"
  ) {
    return t.toolCalls.personalIpReadingEvidence;
  } else if (toolCall.name === "personal_ip_select_browser_account") {
    return t.toolCalls.personalIpPreparingOperation;
  } else if (
    toolCall.name.startsWith("personal_ip_") &&
    toolCall.name.includes("video")
  ) {
    return t.toolCalls.personalIpProducingVideo;
  } else if (
    toolCall.name === "web_search" ||
    toolCall.name === "image_search"
  ) {
    return t.toolCalls.searchFor(toolCall.args.query);
  } else if (toolCall.name === "web_fetch") {
    return t.toolCalls.viewWebPage;
  } else if (toolCall.name === "present_files") {
    return t.toolCalls.presentFiles;
  } else if (toolCall.name === "write_todos") {
    return t.toolCalls.writeTodos;
  } else if (toolCall.args.description) {
    return toolCall.args.description;
  } else {
    return t.common.thinking;
  }
}
