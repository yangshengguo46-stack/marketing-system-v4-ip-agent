import { describe, expect, test } from "@rstest/core";

import {
  GET,
  resolveMockArtifactPath,
} from "@/app/mock/api/threads/[thread_id]/artifacts/[[...artifact_path]]/route";

const FIXTURE_THREAD = "3823e443-4e2b-4679-b496-a9506eae462b";
const FIXTURE_PATH = [
  "mnt",
  "user-data",
  "outputs",
  "fei-fei-li-podcast-timeline.md",
];

describe("mock artifact route", () => {
  test("resolves bundled demo artifacts within the selected thread", () => {
    expect(
      resolveMockArtifactPath({
        threadId: FIXTURE_THREAD,
        artifactPath: FIXTURE_PATH,
      }),
    ).toMatch(
      /public\/demo\/threads\/3823e443-4e2b-4679-b496-a9506eae462b\/user-data\/outputs\/fei-fei-li-podcast-timeline\.md$/,
    );
  });

  test("rejects thread and artifact traversal", () => {
    expect(
      resolveMockArtifactPath({
        threadId: "..",
        artifactPath: FIXTURE_PATH,
      }),
    ).toBeNull();
    expect(
      resolveMockArtifactPath({
        threadId: FIXTURE_THREAD,
        artifactPath: ["mnt", "user-data", "..", "thread.json"],
      }),
    ).toBeNull();
    expect(
      resolveMockArtifactPath({
        threadId: FIXTURE_THREAD,
        artifactPath: ["mnt", "user-data/../../thread.json"],
      }),
    ).toBeNull();
  });

  test("serves a valid artifact without leaking its absolute path", async () => {
    const response = await GET(
      {
        nextUrl: new URL("http://localhost/mock/artifact?download=true"),
      } as never,
      {
        params: Promise.resolve({
          thread_id: FIXTURE_THREAD,
          artifact_path: FIXTURE_PATH,
        }),
      },
    );

    expect(response.status).toBe(200);
    expect(response.headers.get("Content-Disposition")).toBe(
      'attachment; filename="fei-fei-li-podcast-timeline.md"',
    );
    expect(await response.text()).toContain("Fei-Fei");
  });

  test("returns 404 for invalid or missing artifacts", async () => {
    const response = await GET(
      {
        nextUrl: new URL("http://localhost/mock/artifact"),
      } as never,
      {
        params: Promise.resolve({
          thread_id: FIXTURE_THREAD,
          artifact_path: ["mnt", "user-data", "..", "thread.json"],
        }),
      },
    );

    expect(response.status).toBe(404);
  });
});
