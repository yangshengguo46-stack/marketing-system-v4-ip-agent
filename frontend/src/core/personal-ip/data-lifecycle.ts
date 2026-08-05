import { fetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

type PersonalIPBackupBase = {
  owner_user_id: string;
  exported_at: string;
  credential_policy?: {
    credentials_included: false;
    oauth_states_included: false;
    platform_reauthorization_required_after_restore: true;
  };
  datasets: Array<{
    name: string;
    count?: number;
    digest?: string;
    records?: unknown[];
  }>;
};

export type PersonalIPBackup = PersonalIPBackupBase &
  (
    | {
        schema_version:
          | "personal-ip-owner-backup-v1"
          | "personal-ip-owner-backup-v2"
          | "personal-ip-owner-backup-v3";
        verification: {
          algorithm: "sha256-canonical-json-v1";
          data_digest: string;
          manifest_digest: string;
        };
      }
    | {
        schema_version: "personal-ip-owner-backup-v4";
        verification: {
          algorithm: "hmac-sha256-canonical-json-v1";
          key_id: string;
          data_digest: string;
          manifest_digest: string;
        };
      }
  );

type PersonalIPBackupCandidate = Partial<PersonalIPBackupBase> & {
  schema_version?: unknown;
  verification?: {
    algorithm?: unknown;
    key_id?: unknown;
    data_digest?: unknown;
    manifest_digest?: unknown;
  };
};

export function isPersonalIPBackup(value: unknown): value is PersonalIPBackup {
  if (!value || typeof value !== "object") return false;
  const candidate = value as PersonalIPBackupCandidate;
  const hasBaseContract =
    Array.isArray(candidate.datasets) &&
    typeof candidate.verification?.data_digest === "string" &&
    typeof candidate.verification?.manifest_digest === "string";
  if (!hasBaseContract) return false;

  if (candidate.schema_version === "personal-ip-owner-backup-v4") {
    return (
      candidate.verification?.algorithm === "hmac-sha256-canonical-json-v1" &&
      typeof candidate.verification.key_id === "string" &&
      candidate.verification.key_id.trim().length > 0
    );
  }

  return (
    (candidate.schema_version === "personal-ip-owner-backup-v1" ||
      candidate.schema_version === "personal-ip-owner-backup-v2" ||
      candidate.schema_version === "personal-ip-owner-backup-v3") &&
    candidate.verification?.algorithm === "sha256-canonical-json-v1"
  );
}

export type PersonalIPDeletePreview = {
  schema_version: "personal-ip-destructive-delete-preview-v1";
  owner_user_id: string;
  record_counts: Record<string, number>;
  total_records: number;
  state_digest: string;
  confirmation_phrase: string;
  requires_backup_acknowledgement: true;
  requires_artifact_file_acknowledgement: boolean;
  includes_local_context: true;
  includes_artifact_files: boolean;
  irreversible: true;
};

export type PersonalIPDeleteConfirmation = {
  schema_version: "personal-ip-destructive-delete-confirmation-v1";
  owner_user_id: string;
  state_digest: string;
  confirmation_phrase: string;
  backup_acknowledged: true;
  artifact_files_acknowledged: true;
  delete_local_context: true;
};

async function requestJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${getBackendBaseURL()}${path}`;
  const response = init ? await fetch(url, init) : await fetch(url);
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(payload?.detail ?? `Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export function exportPersonalIPBackup() {
  return requestJSON<PersonalIPBackup>("/api/personal-ip/data/export");
}

export function restorePersonalIPBackup(backup: PersonalIPBackup) {
  return requestJSON<{ verified: true; restored_records?: number }>(
    "/api/personal-ip/data/restore",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ backup }),
    },
  );
}

export function previewPersonalIPDelete() {
  return requestJSON<PersonalIPDeletePreview>(
    "/api/personal-ip/data/delete-preview",
  );
}

export function deleteAllPersonalIPData(
  confirmation: PersonalIPDeleteConfirmation,
) {
  return requestJSON<{ deleted_records: number; local_context_deleted?: true }>(
    "/api/personal-ip/data/delete",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(confirmation),
    },
  );
}
