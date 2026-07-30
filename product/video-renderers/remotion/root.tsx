import { Composition } from "remotion";
import { PersonalIPScene, type SceneProps } from "./scene";

const defaults: SceneProps = {
  contract_version: "personal-ip-render-scene-v1",
  canvas: { width: 1280, height: 720, fps: 30 },
  duration_seconds: 3,
  label: "",
  headline: "Personal-IP scene",
  body: "",
  accent: "#f05a36",
  background: "#101418",
  media: [],
};

export const VideoRendererRoot = () => (
  <Composition
    id="PersonalIPScene"
    component={PersonalIPScene}
    defaultProps={defaults}
    durationInFrames={90}
    fps={30}
    width={1280}
    height={720}
    calculateMetadata={({ props }) => ({
      durationInFrames: Math.max(
        1,
        Math.ceil(props.duration_seconds * props.canvas.fps),
      ),
      fps: props.canvas.fps,
      width: props.canvas.width,
      height: props.canvas.height,
    })}
  />
);
