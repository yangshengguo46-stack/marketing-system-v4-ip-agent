import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { expect, test } from "@rstest/core";

const workspacePolicy = readFileSync(
  resolve(process.cwd(), "pnpm-workspace.yaml"),
  "utf8",
);

test("keeps explicitly ignored dependency builds non-fatal on pnpm 11", () => {
  expect(workspacePolicy).toContain("strictDepBuilds: false");
  expect(workspacePolicy).toMatch(
    /ignoredBuiltDependencies:\s+[- ]+esbuild\s+[- ]+sharp\s+[- ]+unrs-resolver/,
  );
  expect(workspacePolicy).toMatch(
    /allowBuilds:\s+esbuild: false\s+sharp: false\s+unrs-resolver: false/,
  );
});
