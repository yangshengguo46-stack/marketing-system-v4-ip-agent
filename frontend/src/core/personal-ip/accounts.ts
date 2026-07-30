"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { fetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

import { PERSONAL_IP_COCKPIT_QUERY_KEY } from "./cockpit";

export type PersonalIPAccount = {
  id: string;
  owner_user_id: string;
  subject_id: string | null;
  platform: string;
  display_name: string;
  handle: string | null;
  avatar_url: string | null;
  status: "active" | "archived";
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type PersonalIPAccountInput = Pick<
  PersonalIPAccount,
  "platform" | "subject_id" | "display_name" | "handle" | "avatar_url"
> & { metadata?: Record<string, unknown> };

const ACCOUNTS_QUERY_KEY = ["personal-ip", "accounts"] as const;

async function readError(response: Response): Promise<string> {
  const payload = (await response.json().catch(() => null)) as {
    detail?: string;
  } | null;
  return payload?.detail ?? `Request failed (${response.status})`;
}

async function requestJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${getBackendBaseURL()}${path}`, init);
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return (await response.json()) as T;
}

export function usePersonalIPAccounts(includeArchived = false) {
  return useQuery({
    queryKey: [...ACCOUNTS_QUERY_KEY, includeArchived],
    queryFn: () =>
      requestJSON<PersonalIPAccount[]>(
        `/api/personal-ip/accounts${includeArchived ? "?include_archived=true" : ""}`,
      ),
  });
}

export function useCreatePersonalIPAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: PersonalIPAccountInput) =>
      requestJSON<PersonalIPAccount>("/api/personal-ip/accounts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ACCOUNTS_QUERY_KEY }),
        queryClient.invalidateQueries({
          queryKey: PERSONAL_IP_COCKPIT_QUERY_KEY,
        }),
      ]);
    },
  });
}

export function useUpdatePersonalIPAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      accountId,
      updates,
    }: {
      accountId: string;
      updates: Partial<PersonalIPAccountInput> & {
        status?: "active" | "archived";
      };
    }) =>
      requestJSON<PersonalIPAccount>(
        `/api/personal-ip/accounts/${encodeURIComponent(accountId)}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(updates),
        },
      ),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ACCOUNTS_QUERY_KEY }),
        queryClient.invalidateQueries({
          queryKey: PERSONAL_IP_COCKPIT_QUERY_KEY,
        }),
      ]);
    },
  });
}

export function useLogoutPersonalIPAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (accountId: string) =>
      requestJSON<PersonalIPAccount>(
        `/api/personal-ip/accounts/${encodeURIComponent(accountId)}/logout`,
        { method: "POST" },
      ),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ACCOUNTS_QUERY_KEY }),
        queryClient.invalidateQueries({
          queryKey: PERSONAL_IP_COCKPIT_QUERY_KEY,
        }),
      ]);
    },
  });
}

export function useDeletePersonalIPAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (accountId: string) =>
      requestJSON<{ success: boolean }>(
        `/api/personal-ip/accounts/${encodeURIComponent(accountId)}`,
        { method: "DELETE" },
      ),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ACCOUNTS_QUERY_KEY }),
        queryClient.invalidateQueries({
          queryKey: PERSONAL_IP_COCKPIT_QUERY_KEY,
        }),
      ]);
    },
  });
}
