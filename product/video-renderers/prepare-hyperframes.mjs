import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const rendererRoot = path.dirname(fileURLToPath(import.meta.url));
const [specArgument, projectArgument] = process.argv.slice(2);
if (!specArgument || !projectArgument) {
  throw new Error("usage: prepare-hyperframes.mjs <scene-spec.json> <project-dir>");
}

const specPath = path.resolve(specArgument);
const sourceRoot = path.dirname(specPath);
const projectRoot = path.resolve(projectArgument);
const spec = JSON.parse(fs.readFileSync(specPath, "utf8"));
const contractVersion = "personal-ip-render-scene-v1";
if (spec.contract_version !== contractVersion) {
  throw new Error(`scene spec contract_version must be ${contractVersion}`);
}

const numberInRange = (value, field, minimum, maximum) => {
  if (
    typeof value !== "number" ||
    !Number.isFinite(value) ||
    value < minimum ||
    value > maximum
  ) {
    throw new Error(`${field} must be between ${minimum} and ${maximum}`);
  }
  return value;
};
const text = (value, field, limit, required = false) => {
  const normalized = String(value ?? "").replace(/\s+/g, " ").trim();
  if ((required && !normalized) || normalized.length > limit) {
    throw new Error(`${field} must contain ${required ? `1 to ${limit}` : `at most ${limit}`} characters`);
  }
  return normalized;
};
const color = (value, field) => {
  const normalized = String(value ?? "").trim();
  if (!/^#[0-9a-fA-F]{6}$/.test(normalized)) {
    throw new Error(`${field} must be a six-digit hex color`);
  }
  return normalized.toLowerCase();
};
const inside = (candidate, root) =>
  candidate === root || candidate.startsWith(`${root}${path.sep}`);
const sha256 = (file) =>
  crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
const escapeHtml = (value) =>
  String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");

const canvas = spec.canvas ?? {};
const width = Math.trunc(numberInRange(canvas.width, "canvas.width", 320, 7680));
const height = Math.trunc(numberInRange(canvas.height, "canvas.height", 320, 7680));
const fps = Math.trunc(numberInRange(canvas.fps, "canvas.fps", 24, 60));
const duration = numberInRange(spec.duration_seconds, "duration_seconds", 0.5, 600);
const headline = text(spec.headline, "headline", 160, true);
const body = text(spec.body, "body", 600);
const label = text(spec.label, "label", 80);
const accent = color(spec.accent ?? "#f05a36", "accent");
const background = color(spec.background ?? "#101418", "background");

const rawMedia = Array.isArray(spec.media) ? spec.media : [];
if (rawMedia.length > 80) {
  throw new Error("media may contain at most 80 items");
}
fs.mkdirSync(projectRoot, { recursive: true });
const assetsRoot = path.join(projectRoot, "assets");
fs.mkdirSync(assetsRoot, { recursive: true });
fs.copyFileSync(
  path.join(rendererRoot, "node_modules", "gsap", "dist", "gsap.min.js"),
  path.join(projectRoot, "gsap.min.js"),
);

const inputs = [];
const mediaMarkup = rawMedia.map((item, index) => {
  if (!item || typeof item !== "object" || Array.isArray(item)) {
    throw new Error(`media[${index}] must be an object`);
  }
  const kind = String(item.kind ?? "").trim();
  if (!["image", "video", "audio"].includes(kind)) {
    throw new Error(`media[${index}].kind must be image, video or audio`);
  }
  const relativeFile = text(item.file, `media[${index}].file`, 1024, true);
  const source = path.resolve(sourceRoot, relativeFile);
  if (!inside(source, sourceRoot) || !fs.statSync(source).isFile()) {
    throw new Error(`media[${index}].file must be a file below the scene spec directory`);
  }
  const start = numberInRange(item.start_seconds ?? 0, `media[${index}].start_seconds`, 0, duration);
  const clipDuration = numberInRange(
    item.duration_seconds ?? duration - start,
    `media[${index}].duration_seconds`,
    0.04,
    duration,
  );
  if (start + clipDuration > duration + 0.000001) {
    throw new Error(`media[${index}] exceeds duration_seconds`);
  }
  const mediaStart = numberInRange(
    item.media_start_seconds ?? 0,
    `media[${index}].media_start_seconds`,
    0,
    86400,
  );
  const fit = String(item.fit ?? "cover").trim();
  if (!["cover", "contain"].includes(fit)) {
    throw new Error(`media[${index}].fit must be cover or contain`);
  }
  const extension = path.extname(source).toLowerCase().replace(/[^.a-z0-9]/g, "");
  const filename = `media-${String(index).padStart(3, "0")}${extension}`;
  const target = path.join(assetsRoot, filename);
  fs.copyFileSync(source, target);
  inputs.push({
    file: relativeFile,
    sha256: sha256(source),
    size_bytes: fs.statSync(source).size,
  });
  const common = `id="media-${index}" class="clip media media-${kind}" src="assets/${filename}" data-start="${start}" data-duration="${clipDuration}" data-track-index="${index}" data-media-start="${mediaStart}"`;
  if (kind === "video") {
    return `<video ${common} muted playsinline preload="auto" style="object-fit:${fit}"></video>`;
  }
  if (kind === "audio") {
    return `<audio ${common} data-volume="1"></audio>`;
  }
  return `<img ${common} alt="" style="object-fit:${fit}" />`;
});

const html = `<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=${width}, height=${height}" />
    <title>Personal-IP HyperFrames Scene</title>
    <script src="./gsap.min.js"></script>
    <style>
      * { box-sizing: border-box; }
      html, body { margin: 0; width: ${width}px; height: ${height}px; overflow: hidden; background: ${background}; }
      body { font-family: sans-serif; }
      #root { position: relative; width: ${width}px; height: ${height}px; overflow: hidden; }
      .background { position: absolute; inset: 0; background: ${background}; }
      .media { position: absolute; inset: 0; width: 100%; height: 100%; z-index: 1; }
      .media-audio { display: none; }
      .copy-clip { position: absolute; inset: 0; z-index: 10; color: #fff; }
      .shade { position: absolute; inset: 0; background: linear-gradient(180deg, rgba(0,0,0,.08), rgba(0,0,0,.72)); }
      .copy { position: absolute; left: 7%; right: 7%; bottom: 9%; max-width: 86%; }
      .label { display: inline-block; margin-bottom: 20px; color: ${accent}; font-size: ${Math.round(width * 0.018)}px; font-weight: 750; letter-spacing: .16em; }
      .headline { margin: 0; max-width: 100%; color: #fff; font-size: ${Math.round(width * 0.065)}px; line-height: 1.08; font-weight: 850; letter-spacing: -.03em; text-wrap: balance; text-shadow: 0 4px 24px rgba(0,0,0,.35); }
      .body { margin: 24px 0 0; max-width: 88%; color: rgba(255,255,255,.88); font-size: ${Math.round(width * 0.025)}px; line-height: 1.55; font-weight: 520; text-wrap: pretty; }
      .progress { width: 100%; height: 6px; margin-top: 34px; overflow: hidden; background: rgba(255,255,255,.24); }
      .progress-bar { display: block; width: 100%; height: 100%; background: ${accent}; transform-origin: left center; }
    </style>
  </head>
  <body>
    <main
      id="root"
      data-composition-id="main"
      data-start="0"
      data-width="${width}"
      data-height="${height}"
      data-duration="${duration}"
      data-fps="${fps}"
    >
      <div class="background" data-layout-ignore></div>
      ${mediaMarkup.join("\n      ")}
      <section id="scene-copy" class="clip copy-clip" data-start="0" data-duration="${duration}" data-track-index="90">
        <div class="shade" data-layout-ignore></div>
        <div class="copy">
          ${label ? `<div id="label" class="label">${escapeHtml(label)}</div>` : ""}
          <h1 id="headline" class="headline">${escapeHtml(headline)}</h1>
          ${body ? `<p id="body-copy" class="body">${escapeHtml(body)}</p>` : ""}
          <div class="progress" data-layout-ignore><span id="progress-bar" class="progress-bar"></span></div>
        </div>
      </section>
    </main>
    <script>
      window.__timelines = window.__timelines || {};
      const tl = gsap.timeline({ paused: true });
      tl.from("#headline", { y: 44, opacity: 0, duration: ${Math.min(0.7, duration * 0.2)}, ease: "power3.out" }, ${Math.min(0.12, duration * 0.04)});
      ${label ? `tl.from("#label", { y: 24, opacity: 0, duration: ${Math.min(0.45, duration * 0.14)}, ease: "power2.out" }, 0);` : ""}
      ${body ? `tl.from("#body-copy", { y: 28, opacity: 0, duration: ${Math.min(0.55, duration * 0.16)}, ease: "power2.out" }, ${Math.min(0.24, duration * 0.08)});` : ""}
      tl.fromTo("#progress-bar", { scaleX: 0 }, { scaleX: 1, duration: ${duration}, ease: "none" }, 0);
      window.__timelines.main = tl;
    </script>
  </body>
</html>
`;
const motion = {
  duration,
  assertions: [
    { kind: "appearsBy", selector: "#headline", bySec: Math.min(0.8, duration * 0.25) },
    { kind: "staysInFrame", selector: ".copy" },
    { kind: "keepsMoving", withinSelector: "#root", maxStaticSec: Math.min(2, duration * 0.45) },
  ],
};
fs.writeFileSync(path.join(projectRoot, "index.html"), html);
fs.writeFileSync(
  path.join(projectRoot, "index.motion.json"),
  `${JSON.stringify(motion, null, 2)}\n`,
);
const output = {
  contract_version: contractVersion,
  project_root: projectRoot,
  source_spec_sha256: sha256(specPath),
  html_sha256: sha256(path.join(projectRoot, "index.html")),
  motion_sha256: sha256(path.join(projectRoot, "index.motion.json")),
  inputs,
  canvas: { width, height, fps },
  duration_seconds: duration,
};
process.stdout.write(`${JSON.stringify(output)}\n`);
