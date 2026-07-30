import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));
const readJson = (relative) =>
  JSON.parse(fs.readFileSync(path.join(root, relative), "utf8"));
const policy = readJson("version-policy.json");
const manifest = readJson("package.json");
const lock = readJson("package-lock.json");
const expected = policy.dependencies;

const assertVersions = (label, actual) => {
  for (const [name, version] of Object.entries(expected)) {
    if (actual?.[name] !== version) {
      throw new Error(
        `${label} drifted: ${name} must remain ${version}, got ${actual?.[name] ?? "missing"}`,
      );
    }
  }
};

assertVersions("package.json", manifest.dependencies);
assertVersions("package-lock root", lock.packages?.[""]?.dependencies);
for (const [name, version] of Object.entries(expected)) {
  const key = `node_modules/${name}`;
  if (lock.packages?.[key]?.version !== version) {
    throw new Error(`package-lock package drifted: ${name} must remain ${version}`);
  }
  const installedManifest = path.join(root, key, "package.json");
  if (fs.existsSync(installedManifest)) {
    const installed = JSON.parse(fs.readFileSync(installedManifest, "utf8"));
    if (installed.version !== version) {
      throw new Error(`installed package drifted: ${name} must remain ${version}`);
    }
  }
}
if (policy.default_renderer !== "hyperframes") {
  throw new Error("HyperFrames must remain the default renderer");
}
if (
  policy.remotion?.bundled !== true ||
  policy.remotion?.version !== expected.remotion ||
  policy.remotion?.distribution_gate?.length < 20
) {
  throw new Error("Remotion MVP use and customer-distribution gate must remain explicit");
}

process.stdout.write(
  `video renderer pins verified; HyperFrames ${expected.hyperframes} is default and Remotion ${expected.remotion} is available\n`,
);
