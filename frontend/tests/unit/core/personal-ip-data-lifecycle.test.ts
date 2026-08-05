import { beforeEach, describe, expect, it, rs } from "@rstest/core";

rs.mock("@/core/api/fetcher", () => ({
  fetch: rs.fn(),
}));
rs.mock("@/core/config", () => ({
  getBackendBaseURL: () => "/backend",
}));

import { fetch as fetcher } from "@/core/api/fetcher";
import {
  deleteAllPersonalIPData,
  exportPersonalIPBackup,
  isPersonalIPBackup,
  previewPersonalIPDelete,
  restorePersonalIPBackup,
} from "@/core/personal-ip/data-lifecycle";

const mockedFetch = rs.mocked(fetcher);

function response(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  mockedFetch.mockReset();
});

describe("Personal-IP data lifecycle API", () => {
  it("exports and restores the credential-free owner backup contract", async () => {
    const backup = {
      schema_version: "personal-ip-owner-backup-v4" as const,
      owner_user_id: "user-1",
      exported_at: "2026-07-30T12:00:00Z",
      datasets: [],
      verification: {
        algorithm: "hmac-sha256-canonical-json-v1" as const,
        key_id: "owner-backup-key-2026-08",
        data_digest: "a".repeat(64),
        manifest_digest: "b".repeat(64),
      },
    };
    mockedFetch
      .mockResolvedValueOnce(response(200, backup))
      .mockResolvedValueOnce(
        response(200, {
          schema_version: "personal-ip-owner-restore-receipt-v1",
          verified: true,
        }),
      );

    await expect(exportPersonalIPBackup()).resolves.toEqual(backup);
    await restorePersonalIPBackup(backup);

    expect(mockedFetch).toHaveBeenNthCalledWith(
      1,
      "/backend/api/personal-ip/data/export",
    );
    expect(mockedFetch).toHaveBeenNthCalledWith(
      2,
      "/backend/api/personal-ip/data/restore",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ backup }),
      },
    );
  });

  it("accepts the exact legacy and HMAC-authenticated v4 verification contracts", () => {
    const legacyCandidate = {
      owner_user_id: "user-1",
      exported_at: "2026-08-05T00:00:00Z",
      datasets: [],
      verification: {
        algorithm: "sha256-canonical-json-v1",
        data_digest: "a".repeat(64),
        manifest_digest: "b".repeat(64),
      },
    };

    for (const schemaVersion of [
      "personal-ip-owner-backup-v1",
      "personal-ip-owner-backup-v2",
      "personal-ip-owner-backup-v3",
    ]) {
      expect(
        isPersonalIPBackup({
          ...legacyCandidate,
          schema_version: schemaVersion,
        }),
      ).toBe(true);
    }

    const v4Candidate = {
      ...legacyCandidate,
      schema_version: "personal-ip-owner-backup-v4",
      verification: {
        ...legacyCandidate.verification,
        algorithm: "hmac-sha256-canonical-json-v1",
        key_id: "owner-backup-key-2026-08",
      },
    };
    expect(isPersonalIPBackup(v4Candidate)).toBe(true);
    expect(
      isPersonalIPBackup({
        ...legacyCandidate,
        schema_version: "personal-ip-owner-backup-v4",
      }),
    ).toBe(false);
    expect(
      isPersonalIPBackup({
        ...v4Candidate,
        verification: { ...v4Candidate.verification, key_id: "" },
      }),
    ).toBe(false);
    expect(
      isPersonalIPBackup({
        ...v4Candidate,
        schema_version: "personal-ip-owner-backup-v3",
      }),
    ).toBe(false);
    expect(
      isPersonalIPBackup({
        ...legacyCandidate,
        schema_version: "personal-ip-owner-backup-v5",
      }),
    ).toBe(false);
    expect(
      isPersonalIPBackup({
        ...v4Candidate,
        schema_version: "personal-ip-owner-backup-v4",
        datasets: null,
      }),
    ).toBe(false);
  });

  it("binds destructive deletion to the preview digest and exact acknowledgement", async () => {
    const preview = {
      schema_version: "personal-ip-destructive-delete-preview-v1" as const,
      owner_user_id: "user-1",
      record_counts: { subjects: 1 },
      total_records: 1,
      state_digest: "c".repeat(64),
      confirmation_phrase: "永久删除我的全部个人IP数据",
      requires_backup_acknowledgement: true,
      requires_artifact_file_acknowledgement: true,
      includes_local_context: true,
      includes_artifact_files: true,
      irreversible: true,
    };
    mockedFetch
      .mockResolvedValueOnce(response(200, preview))
      .mockResolvedValueOnce(
        response(200, {
          schema_version: "personal-ip-destructive-delete-receipt-v1",
          deleted_records: 1,
        }),
      );

    await expect(previewPersonalIPDelete()).resolves.toEqual(preview);
    await deleteAllPersonalIPData({
      schema_version: "personal-ip-destructive-delete-confirmation-v1",
      owner_user_id: preview.owner_user_id,
      state_digest: preview.state_digest,
      confirmation_phrase: preview.confirmation_phrase,
      backup_acknowledged: true,
      artifact_files_acknowledged: true,
      delete_local_context: true,
    });

    expect(mockedFetch).toHaveBeenLastCalledWith(
      "/backend/api/personal-ip/data/delete",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          schema_version: "personal-ip-destructive-delete-confirmation-v1",
          owner_user_id: preview.owner_user_id,
          state_digest: preview.state_digest,
          confirmation_phrase: preview.confirmation_phrase,
          backup_acknowledged: true,
          artifact_files_acknowledged: true,
          delete_local_context: true,
        }),
      },
    );
  });

  it("surfaces server conflict details", async () => {
    mockedFetch.mockResolvedValueOnce(
      response(409, { detail: "prepare a fresh confirmation" }),
    );
    await expect(previewPersonalIPDelete()).rejects.toThrow(
      "prepare a fresh confirmation",
    );
  });
});
