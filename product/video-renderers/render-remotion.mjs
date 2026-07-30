import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));
const [specArgument, outputArgument, browserArgument, ffmpegArgument] =
  process.argv.slice(2);
if (
  !specArgument ||
  !outputArgument ||
  !browserArgument ||
  !ffmpegArgument
) {
  throw new Error(
    "usage: render-remotion.mjs <scene-spec.json> <output.mp4> <browser> <ffmpeg>",
  );
}
const specPath = path.resolve(specArgument);
const outputPath = path.resolve(outputArgument);
const browserPath = path.resolve(browserArgument);
const ffmpegPath = path.resolve(ffmpegArgument);
for (const [label, target] of [
  ["scene spec", specPath],
  ["browser", browserPath],
  ["project-local FFmpeg", ffmpegPath],
]) {
  if (!fs.existsSync(target) || !fs.statSync(target).isFile()) {
    throw new Error(`${label} is missing`);
  }
}

const spec = JSON.parse(fs.readFileSync(specPath, "utf8"));
if (spec.contract_version !== "personal-ip-render-scene-v1") {
  throw new Error(
    "scene spec contract_version must be personal-ip-render-scene-v1",
  );
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
const fps = Math.trunc(
  numberInRange(spec.canvas?.fps, "canvas.fps", 24, 60),
);
numberInRange(spec.canvas?.width, "canvas.width", 320, 7680);
numberInRange(spec.canvas?.height, "canvas.height", 320, 7680);
const duration = numberInRange(
  spec.duration_seconds,
  "duration_seconds",
  0.5,
  600,
);
if (
  typeof spec.headline !== "string" ||
  !spec.headline.trim() ||
  spec.headline.length > 160
) {
  throw new Error("headline must contain 1 to 160 characters");
}
if (!Array.isArray(spec.media) || spec.media.length > 80) {
  throw new Error("scene spec media must be an array with at most 80 items");
}
const sourceRoot = path.dirname(specPath);
for (const [index, item] of spec.media.entries()) {
  if (
    !item ||
    typeof item !== "object" ||
    !["image", "video", "audio"].includes(item.kind)
  ) {
    throw new Error(`media[${index}].kind must be image, video or audio`);
  }
  const source = path.resolve(sourceRoot, String(item.file ?? ""));
  if (
    (source !== sourceRoot && !source.startsWith(`${sourceRoot}${path.sep}`)) ||
    !fs.existsSync(source) ||
    !fs.statSync(source).isFile()
  ) {
    throw new Error(
      `media[${index}].file must stay below the scene spec directory`,
    );
  }
  const start = numberInRange(
    item.start_seconds ?? 0,
    `media[${index}].start_seconds`,
    0,
    duration,
  );
  const clipDuration = numberInRange(
    item.duration_seconds ?? duration - start,
    `media[${index}].duration_seconds`,
    0.04,
    duration,
  );
  if (start + clipDuration > duration + 0.000001) {
    throw new Error(`media[${index}] exceeds duration_seconds`);
  }
  numberInRange(
    item.media_start_seconds ?? 0,
    `media[${index}].media_start_seconds`,
    0,
    86400,
  );
}

const cli = path.join(
  root,
  "node_modules",
  "@remotion",
  "cli",
  "remotion-cli.js",
);
const entry = path.join(root, "remotion", "index.ts");
const common = [
  cli,
  "render",
  entry,
  "PersonalIPScene",
  `--props=${specPath}`,
  `--public-dir=${sourceRoot}`,
  `--browser-executable=${browserPath}`,
  "--gl=swiftshader",
  "--concurrency=1",
  "--overwrite",
  "--log=error",
];
const environment = {
  ...process.env,
  REMOTION_NO_UPDATE_CHECK: "1",
};
const temporaryRoot = fs.mkdtempSync(
  path.join(os.tmpdir(), "ip-agent-remotion-"),
);
const warmupRoot = path.join(temporaryRoot, "warmup");
const framesRoot = path.join(temporaryRoot, "frames");
const audioPath = path.join(temporaryRoot, "audio.wav");
const run = (command, label) => {
  const result = spawnSync(process.execPath, command, {
    cwd: root,
    env: environment,
    stdio: "inherit",
  });
  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    throw new Error(`${label} failed with exit code ${result.status ?? 1}`);
  }
};

try {
  run(
    [
      ...common.slice(0, 4),
      warmupRoot,
      ...common.slice(4),
      "--sequence",
      "--image-format=png",
      "--image-sequence-pattern=frame-[frame].[ext]",
      `--frames=0-${Math.min(6, Math.max(0, Math.ceil(duration * fps) - 1))}`,
    ],
    "Remotion cold-start warmup",
  );
  run(
    [
      ...common.slice(0, 4),
      framesRoot,
      ...common.slice(4),
      "--sequence",
      "--image-format=png",
      "--image-sequence-pattern=frame-[frame].[ext]",
    ],
    "Remotion frame rendering",
  );
  const expectedFrames = Math.max(1, Math.ceil(duration * fps));
  const frameFiles = fs
    .readdirSync(framesRoot)
    .filter((name) => /^frame-\d+\.png$/.test(name))
    .sort();
  if (frameFiles.length !== expectedFrames) {
    throw new Error(
      `Remotion returned ${frameFiles.length} frames; expected ${expectedFrames}`,
    );
  }
  const hasAudio = spec.media.some((item) => item.kind === "audio");
  if (hasAudio) {
    run(
      [
        ...common.slice(0, 4),
        audioPath,
        ...common.slice(4),
        "--codec=wav",
        "--audio-codec=pcm-16",
      ],
      "Remotion audio rendering",
    );
  }

  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  const frameDigits = String(Math.max(0, expectedFrames - 1)).length;
  const ffmpegArguments = [
    "-y",
    "-v",
    "error",
    "-framerate",
    String(fps),
    "-start_number",
    "0",
    "-i",
    path.join(framesRoot, `frame-%0${frameDigits}d.png`),
  ];
  if (hasAudio) {
    ffmpegArguments.push("-i", audioPath);
  }
  ffmpegArguments.push(
    "-map",
    "0:v:0",
    ...(hasAudio ? ["-map", "1:a:0"] : ["-an"]),
    "-c:v",
    "libopenh264",
    "-b:v",
    "8M",
    "-maxrate",
    "8M",
    "-bufsize",
    "16M",
    "-pix_fmt",
    "yuv420p",
    "-r",
    String(fps),
    "-g",
    String(fps * 2),
    "-keyint_min",
    String(fps * 2),
    "-sc_threshold",
    "0",
    "-threads",
    "1",
  );
  if (hasAudio) {
    ffmpegArguments.push(
      "-c:a",
      "aac",
      "-b:a",
      "192k",
      "-ar",
      "48000",
    );
  }
  ffmpegArguments.push(
    "-map_metadata",
    "-1",
    "-fflags",
    "+bitexact",
    "-flags:v",
    "+bitexact",
    "-movflags",
    "+faststart",
    "-t",
    String(duration),
    outputPath,
  );
  const finishing = spawnSync(ffmpegPath, ffmpegArguments, {
    cwd: root,
    stdio: "inherit",
  });
  if (finishing.error) {
    throw finishing.error;
  }
  if (finishing.status !== 0) {
    throw new Error(
      `project-local FFmpeg finishing failed with exit code ${finishing.status ?? 1}`,
    );
  }
} finally {
  fs.rmSync(temporaryRoot, { recursive: true, force: true });
}
