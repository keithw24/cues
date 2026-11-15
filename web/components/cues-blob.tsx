"use client";

import {
  useEffect,
  useId,
  useMemo,
  useState,
  useSyncExternalStore,
} from "react";
import { Avatar } from "@bible-strong/avatar-react";
import type { AvatarCharacter } from "@bible-strong/avatar-core";
import "./cues-blob.css";

/** The body shapes the companion can take (from the avatar package). */
export type BlobShape =
  | "sphere"
  | "capsule"
  | "cube"
  | "cylinder"
  | "cone"
  | "diamond"
  | "trapezoid";

// Proportions per shape, at the sphere's 240-unit scale, so every shape
// fills the same space and keeps the same face.
const shapes: Record<BlobShape, { width: number; height: number; depth: number; roundness: number }> = {
  sphere: { width: 240, height: 240, depth: 240.03671875, roundness: 1 },
  capsule: { width: 190, height: 260, depth: 190, roundness: 1 },
  cube: { width: 230, height: 230, depth: 230, roundness: 0.55 },
  cylinder: { width: 220, height: 250, depth: 220, roundness: 0.5 },
  cone: { width: 240, height: 250, depth: 240, roundness: 0.5 },
  diamond: { width: 240, height: 260, depth: 240, roundness: 0.5 },
  trapezoid: { width: 240, height: 230, depth: 230, roundness: 0.55 },
};

// Body and face proportions adapted from the MIT-licensed Strobi example.
// The blob is Cues' companion, never a teacher or learner identity.
const character: AvatarCharacter = {
  name: "Cues companion",
  body: {
    primary: {
      type: "sphere",
      width: 240,
      height: 240,
      depth: 240.03671875,
      roundness: 1,
    },
    nodes: [],
  },
  // Cues blue leaning toward the lavender in the workspace glow, so the
  // companion reads as part of the same palette rather than a flat accent.
  colors: { body: "#5763d2", eyes: "#ffffff" },
  face: {
    eyes: { width: 1.05, height: 0.85, gap: 0.72, shiftY: -7 / 120 },
    perspective: 1,
  },
};

// How long one walk from one side to the other takes, in ms.
const STRIDE_MS = 3600;

const subscribe = (callback: () => void) => {
  const query = window.matchMedia("(prefers-reduced-motion: reduce)");
  query.addEventListener("change", callback);
  return () => query.removeEventListener("change", callback);
};

export default function CuesBlob({
  size = 132,
  wander = true,
  busy = false,
  privacy = false,
  shape = "sphere",
  color,
  glance = false,
  seed,
}: {
  /** Animation seed. Companions with the same seed play the same clips at the
   * same moment, so give each one on a screen its own. */
  seed?: number;
  /** Look around on its own, at its own pace (several companions on one
   * screen don't all follow the pointer together). */
  glance?: boolean;
  size?: number;
  /** Body shape; the sign-in companion is a sphere. */
  shape?: BlobShape;
  /** Body color as hex; defaults to the companion's indigo. */
  color?: `#${string}`;
  /** Walk from side to side and look where it is going. */
  wander?: boolean;
  busy?: boolean;
  privacy?: boolean;
}) {
  const filterId = useId().replaceAll(":", "");
  const look = useMemo<AvatarCharacter>(
    () =>
      shape === "sphere" && !color
        ? character
        : {
            ...character,
            body: {
              ...character.body,
              primary: { ...character.body.primary, type: shape, ...shapes[shape] },
            },
            colors: { ...character.colors, body: color ?? character.colors.body },
          },
    [shape, color],
  );
  const reduced = useSyncExternalStore(
    subscribe,
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    () => true,
  );
  const walking = wander && !reduced && !busy && !privacy;
  // Glancing: every 1.6–4s, look somewhere new within a small range. Each
  // instance keeps its own timer and random targets, so a group never moves
  // in step. Off under reduced motion.
  const [gaze, setGaze] = useState<[number, number]>([0, 0]);
  useEffect(() => {
    if (!glance || reduced || walking) return;
    let timer = 0;
    const next = () => {
      setGaze([
        Math.round((Math.random() * 0.5 - 0.25) * 100) / 100,
        Math.round((Math.random() * 0.24 - 0.08) * 100) / 100,
      ]);
      timer = window.setTimeout(next, 1600 + Math.random() * 2400);
    };
    timer = window.setTimeout(next, Math.random() * 1500);
    return () => window.clearTimeout(timer);
  }, [glance, reduced, walking]);
  const [side, setSide] = useState(0);
  useEffect(() => {
    if (!walking) return;
    // Start the first step on the next frame so the transition runs.
    const first = requestAnimationFrame(() => setSide(1));
    const timer = window.setInterval(
      () => setSide((current) => (current === 1 ? -1 : 1)),
      STRIDE_MS,
    );
    return () => {
      cancelAnimationFrame(first);
      window.clearInterval(timer);
      setSide(0);
    };
  }, [walking]);

  return (
    <div
      className="cues-blob"
      aria-hidden="true"
      style={
        {
          "--blob-size": `${size}px`,
          "--blob-side": side,
          "--blob-stride": `${STRIDE_MS}ms`,
          "--blob-filter": `url(#${filterId})`,
        } as React.CSSProperties
      }
    >
      <svg className="cues-blob-defs" width="0" height="0" focusable="false">
        <filter
          id={filterId}
          x="-15%"
          y="-15%"
          width="130%"
          height="130%"
          colorInterpolationFilters="sRGB"
        >
          {/* A feathered edge: the body fades out over its last few pixels. */}
          <feGaussianBlur in="SourceAlpha" stdDeviation="5" result="soft" />
          {/* A light band inside the edge, so the rim reads paler than the middle. */}
          <feGaussianBlur in="SourceAlpha" stdDeviation="26" result="deep" />
          <feComposite in="soft" in2="deep" operator="out" result="rim" />
          <feFlood floodColor="#cdc8f6" floodOpacity="0.85" />
          <feComposite in2="rim" operator="in" result="rimLight" />
          {/* Fine light and dark grain, as on a soft felt ball. */}
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.75"
            numOctaves="3"
            seed="7"
            stitchTiles="stitch"
            result="noise"
          />
          <feColorMatrix
            in="noise"
            type="matrix"
            values="0 0 0 0 0.9  0 0 0 0 0.88  0 0 0 0 1  1.2 0 0 0 -0.62"
            result="light"
          />
          <feColorMatrix
            in="noise"
            type="matrix"
            values="0 0 0 0 0.11  0 0 0 0 0.16  0 0 0 0 0.42  -1.2 0 0 0 0.5"
            result="dark"
          />
          <feMerge result="painted">
            <feMergeNode in="SourceGraphic" />
            <feMergeNode in="dark" />
            <feMergeNode in="rimLight" />
            <feMergeNode in="light" />
          </feMerge>
          <feComposite in="painted" in2="soft" operator="in" />
        </filter>
      </svg>
      <div className="cues-blob-walker">
        <Avatar
          character={look}
          seed={seed}
          size={size}
          state={privacy ? "sleeping" : busy ? "thinking" : "idle"}
          lookAt={
            reduced
              ? [0, 0]
              : walking
                ? [side * 0.16, 0.03]
                : glance
                  ? gaze
                  : null
          }
          paused={reduced}
          ariaLabel="Cues companion"
        />
      </div>
    </div>
  );
}
