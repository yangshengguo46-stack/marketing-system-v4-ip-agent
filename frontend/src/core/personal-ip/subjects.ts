"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { fetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

import { PERSONAL_IP_COCKPIT_QUERY_KEY } from "./cockpit";

export type PersonalIPSubject = {
  id: string;
  owner_user_id: string;
  display_name: string;
  subject_type: "creator" | "brand" | "organization";
  relationship: "self" | "client" | "partner";
  description: string;
  status: "active" | "archived";
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type PersonalIPSubjectInput = Pick<
  PersonalIPSubject,
  "display_name" | "subject_type" | "relationship" | "description"
> & { metadata?: Record<string, unknown> };

const SUBJECTS_QUERY_KEY = ["personal-ip", "subjects"] as const;

async function requestJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${getBackendBaseURL()}${path}`, init);
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(payload?.detail ?? `Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export function usePersonalIPSubjects(includeArchived = false) {
  return useQuery({
    queryKey: [...SUBJECTS_QUERY_KEY, includeArchived],
    queryFn: () =>
      requestJSON<PersonalIPSubject[]>(
        `/api/personal-ip/subjects${includeArchived ? "?include_archived=true" : ""}`,
      ),
  });
}

export function useCreatePersonalIPSubject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: PersonalIPSubjectInput) =>
      requestJSON<PersonalIPSubject>("/api/personal-ip/subjects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: SUBJECTS_QUERY_KEY }),
        queryClient.invalidateQueries({
          queryKey: PERSONAL_IP_COCKPIT_QUERY_KEY,
        }),
      ]);
    },
  });
}

export function useUpdatePersonalIPSubject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      subjectId,
      updates,
    }: {
      subjectId: string;
      updates: Partial<PersonalIPSubjectInput> & {
        status?: "active" | "archived";
      };
    }) =>
      requestJSON<PersonalIPSubject>(
        `/api/personal-ip/subjects/${encodeURIComponent(subjectId)}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(updates),
        },
      ),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: SUBJECTS_QUERY_KEY }),
        queryClient.invalidateQueries({
          queryKey: PERSONAL_IP_COCKPIT_QUERY_KEY,
        }),
      ]);
    },
  });
}
