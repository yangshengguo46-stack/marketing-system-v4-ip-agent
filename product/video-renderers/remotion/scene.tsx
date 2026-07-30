import type { CSSProperties } from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  interpolate,
  OffthreadVideo,
  Sequence,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

export type SceneProps = {
  contract_version: "personal-ip-render-scene-v1";
  canvas: { width: number; height: number; fps: number };
  duration_seconds: number;
  label?: string;
  headline: string;
  body?: string;
  accent?: string;
  background?: string;
  media: Array<{
    file: string;
    kind: "image" | "video" | "audio";
    start_seconds?: number;
    duration_seconds?: number;
    media_start_seconds?: number;
    fit?: "cover" | "contain";
  }>;
};

const clamp = {
  extrapolateLeft: "clamp",
  extrapolateRight: "clamp",
} as const;

const MediaLayer = ({
  item,
}: {
  item: SceneProps["media"][number];
}) => {
  const { fps } = useVideoConfig();
  const style: CSSProperties = {
    width: "100%",
    height: "100%",
    objectFit: item.fit ?? "cover",
  };
  const startFrom = Math.round((item.media_start_seconds ?? 0) * fps);
  if (item.kind === "video") {
    return (
      <OffthreadVideo
        muted
        src={staticFile(item.file)}
        startFrom={startFrom}
        style={style}
      />
    );
  }
  if (item.kind === "audio") {
    return <Audio src={staticFile(item.file)} startFrom={startFrom} />;
  }
  return <Img src={staticFile(item.file)} style={style} />;
};

export const PersonalIPScene = (props: SceneProps) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames, width, height } = useVideoConfig();
  const enter = interpolate(
    frame,
    [0, Math.max(1, Math.round(fps * 0.55))],
    [0, 1],
    clamp,
  );
  const exit = interpolate(
    frame,
    [Math.max(0, durationInFrames - 8), durationInFrames],
    [1, 0],
    clamp,
  );
  const progress = interpolate(
    frame,
    [0, Math.max(1, durationInFrames - 1)],
    [0, 100],
    clamp,
  );
  const inset = Math.round(Math.min(width, height) * 0.07);
  const accent = props.accent ?? "#f05a36";
  const background = props.background ?? "#101418";

  return (
    <AbsoluteFill
      style={{
        backgroundColor: background,
        color: "#fff",
        fontFamily: "sans-serif",
        opacity: exit,
      }}
    >
      {props.media.map((item, index) => {
        const from = Math.round((item.start_seconds ?? 0) * fps);
        const duration = Math.max(
          1,
          Math.round(
            (item.duration_seconds ?? props.duration_seconds - from / fps) *
              fps,
          ),
        );
        return (
          <Sequence
            key={`${item.file}-${index}`}
            from={from}
            durationInFrames={duration}
          >
            <AbsoluteFill>
              <MediaLayer item={item} />
            </AbsoluteFill>
          </Sequence>
        );
      })}
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(180deg, rgba(0,0,0,.08), rgba(0,0,0,.72))",
        }}
      />
      <div
        style={{
          position: "absolute",
          left: inset,
          right: inset,
          bottom: Math.round(height * 0.09),
          transform: `translateY(${interpolate(enter, [0, 1], [44, 0])}px)`,
          opacity: enter,
        }}
      >
        {props.label ? (
          <div
            style={{
              display: "inline-block",
              marginBottom: 20,
              color: accent,
              fontSize: Math.round(width * 0.018),
              fontWeight: 750,
              letterSpacing: ".16em",
            }}
          >
            {props.label}
          </div>
        ) : null}
        <h1
          style={{
            margin: 0,
            maxWidth: "100%",
            fontSize: Math.round(width * 0.065),
            lineHeight: 1.08,
            fontWeight: 850,
            letterSpacing: "-.03em",
            textShadow: "0 4px 24px rgba(0,0,0,.35)",
          }}
        >
          {props.headline}
        </h1>
        {props.body ? (
          <p
            style={{
              margin: "24px 0 0",
              maxWidth: "88%",
              color: "rgba(255,255,255,.88)",
              fontSize: Math.round(width * 0.025),
              lineHeight: 1.55,
              fontWeight: 520,
            }}
          >
            {props.body}
          </p>
        ) : null}
        <div
          style={{
            width: "100%",
            height: 6,
            marginTop: 34,
            overflow: "hidden",
            background: "rgba(255,255,255,.24)",
          }}
        >
          <div
            style={{
              width: `${progress}%`,
              height: "100%",
              background: accent,
            }}
          />
        </div>
      </div>
    </AbsoluteFill>
  );
};
