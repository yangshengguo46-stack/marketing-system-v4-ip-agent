import { type PersonalIPAccount } from "./accounts";

export type PersonalIPConnectionState =
  | "not_added"
  | "pending_login"
  | "logged_in"
  | "collection_limited"
  | "actionable";

export const PERSONAL_IP_CONNECTION_STATE_COPY = {
  not_added: {
    label: "未添加",
    description: "还没有为这个平台创建账号位置。",
    action: "登录",
  },
  pending_login: {
    label: "待登录",
    description: "账号已添加，请本人登录平台。",
    action: "登录",
  },
  logged_in: {
    label: "已登录",
    description: "登录已确认，可以读取获授权的账号页面。",
    action: "退出登录",
  },
  collection_limited: {
    label: "采集受限",
    description: "登录仍可用，但部分经营数据暂时无法完整读取。",
    action: "退出登录",
  },
  actionable: {
    label: "可执行",
    description: "账号可读取数据，并可执行经过确认的操作。",
    action: "退出登录",
  },
} as const satisfies Record<
  PersonalIPConnectionState,
  { label: string; description: string; action: string }
>;

const DIRECT_STATE_ALIASES: Record<string, PersonalIPConnectionState> = {
  not_added: "pending_login",
  not_connected: "pending_login",
  pending: "pending_login",
  pending_login: "pending_login",
  login_required: "pending_login",
  authenticated: "logged_in",
  connected: "logged_in",
  logged_in: "logged_in",
  collection_limited: "collection_limited",
  limited: "collection_limited",
  partial: "collection_limited",
  restricted: "collection_limited",
  actionable: "actionable",
  executable: "actionable",
  ready: "actionable",
};

const LIMITED_COLLECTION_STATES = new Set([
  "blocked",
  "error",
  "limited",
  "partial",
  "permission_required",
  "restricted",
  "unavailable",
]);

const READY_COLLECTION_STATES = new Set([
  "available",
  "complete",
  "ready",
  "success",
]);

function metadataString(
  metadata: Record<string, unknown>,
  key: string,
): string | null {
  const value = metadata[key];
  return typeof value === "string" ? value.trim().toLowerCase() : null;
}

/**
 * Derive the customer-facing account state from non-secret account metadata.
 * Raw credentials and browser profile details are deliberately not inputs.
 */
export function personalIPAccountConnectionState(
  account: PersonalIPAccount,
): Exclude<PersonalIPConnectionState, "not_added"> {
  const metadata = account.metadata ?? {};
  const direct =
    metadataString(metadata, "connection_state") ??
    metadataString(metadata, "connection_status");
  const directState = direct ? DIRECT_STATE_ALIASES[direct] : undefined;
  if (
    directState === "pending_login" ||
    directState === "collection_limited" ||
    directState === "actionable"
  ) {
    return directState;
  }

  const collectionState = metadataString(metadata, "collection_status");
  if (
    metadata.collection_restricted === true ||
    (collectionState !== null && LIMITED_COLLECTION_STATES.has(collectionState))
  ) {
    return "collection_limited";
  }
  if (
    metadata.execution_ready === true ||
    (collectionState !== null && READY_COLLECTION_STATES.has(collectionState))
  ) {
    return "actionable";
  }
  if (directState === "logged_in") {
    return "logged_in";
  }
  if (metadata.browser_authenticated === true) {
    return "logged_in";
  }
  return "pending_login";
}

export type PersonalIPConnectionSummary = {
  platformCount: number;
  accountCount: number;
  notAdded: number;
  pendingLogin: number;
  loggedIn: number;
  collectionLimited: number;
  actionable: number;
};

export function summarizePersonalIPConnections(
  accounts: PersonalIPAccount[],
  platformIds: readonly string[],
): PersonalIPConnectionSummary {
  const supported = new Set(platformIds);
  const supportedAccounts = accounts.filter((account) =>
    supported.has(account.platform),
  );
  const usedPlatforms = new Set(
    supportedAccounts.map((account) => account.platform),
  );
  const summary: PersonalIPConnectionSummary = {
    platformCount: platformIds.length,
    accountCount: supportedAccounts.length,
    notAdded: platformIds.filter((platform) => !usedPlatforms.has(platform))
      .length,
    pendingLogin: 0,
    loggedIn: 0,
    collectionLimited: 0,
    actionable: 0,
  };

  for (const account of supportedAccounts) {
    const state = personalIPAccountConnectionState(account);
    if (state === "pending_login") summary.pendingLogin += 1;
    if (state === "logged_in") summary.loggedIn += 1;
    if (state === "collection_limited") summary.collectionLimited += 1;
    if (state === "actionable") summary.actionable += 1;
  }
  return summary;
}
