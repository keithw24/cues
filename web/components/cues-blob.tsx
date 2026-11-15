"use client";

import { useEffect, useId, useState, useSyncExternalStore } from "react";
import { Avatar } from "@bible-strong/avatar-react";
import type { AvatarCharacter } from "@bible-strong/avatar-core";
import "./cues-blob.css";

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
}: {
  size?: number;
  /** Walk from side to side and look where it is going. */
  wander?: boolean;
  busy?: boolean;
  privacy?: boolean;
}) {
  const filterId = useId().replaceAll(":", "");
  const reduced = useSyncExternalStore(
    subscribe,
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    () => true,
  );
  const walking = wander && !reduced && !busy && !privacy;
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
          character={character}
          size={size}
          state={privacy ? "sleeping" : busy ? "thinking" : "idle"}
          lookAt={reduced ? [0, 0] : walking ? [side * 0.16, 0.03] : null}
          paused={reduced}
          ariaLabel="Cues companion"
        />
      </div>
    </div>
  );
}
