"use client";

import { useEffect, useState } from "react";
import {
  cameraHealth,
  readLocalVision,
  updatesFresh,
  type LocalVisionReading,
} from "@/lib/camera-health";
import { WorkspaceIcon } from "@/components/workspace-icon";
import { mayConnectLocalFeed } from "@/lib/local-feed-policy";

const POLL_MS = 3000;

// Four plain facts about the camera, each as a word (color only supports it), and one
// sentence naming the most useful cause when something is wrong. It reads this laptop's
// vision service and the station's rows; no frames, scores or claims about a child.
export function CameraHealthStrip({
  station,
  updatedAt,
  inView,
  conflict,
  hostedEnabled = false,
  hostedOrigin,
}: {
  station: string;
  /** updated_at of each person's latest row at this station. */
  updatedAt: readonly (string | null | undefined)[];
  inView: number;
  /** Another camera is being refused on this station (from its writer row). */
  conflict: boolean;
  /** web.hosted_local_feed: the hosted dashboard may read this laptop's service. */
  hostedEnabled?: boolean;
  hostedOrigin?: string;
}) {
  const [vision, setVision] = useState<LocalVisionReading | null>(null);
  // The clock starts on the first poll (in the effect), never during render.
  const [now, setNow] = useState(0);
  // Known only in the browser; until then the strip reads "Checking".
  const [localReadable, setLocalReadable] = useState<boolean | null>(null);
  useEffect(() => {
    let disposed = false;
    // Only a page allowed to reach this laptop (localhost, or the hosted origin with
    // web.hosted_local_feed) reads its vision service, as the video feed does.
    const readable = mayConnectLocalFeed(window.location.origin, hostedEnabled, hostedOrigin);
    queueMicrotask(() => {
      if (!disposed) setLocalReadable(readable);
    });
    const tick = () => {
      if (document.hidden) return;
      setNow(Date.now());
      if (!readable) return;
      void readLocalVision().then((reading) => {
        if (!disposed) setVision(reading);
      });
    };
    tick();
    const timer = setInterval(tick, POLL_MS);
    document.addEventListener("visibilitychange", tick);
    return () => {
      disposed = true;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [hostedEnabled, hostedOrigin]);
  const health = cameraHealth({
    vision,
    station,
    updatesFresh: updatesFresh(updatedAt, now),
    inView,
    conflict,
    localReadable: localReadable ?? undefined,
  });
  // Closed by default: one pill with a dot that turns amber when any check
  // needs a look. The four checks and the sentence open underneath.
  const tone = health.items.some((item) => item.tone === "warn")
    ? "warn"
    : health.items.every((item) => item.tone === "good")
      ? "good"
      : "quiet";
  const summary =
    tone === "warn" ? "Needs a look" : tone === "good" ? "All good" : "Checking";
  return (
    <details className="health-strip">
      <summary>
        <span className={`health-dot is-${tone}`} aria-hidden="true" />
        Camera status
        <span className="health-summary">{summary}</span>
        <WorkspaceIcon name="chevronDown" />
      </summary>
      <ul>
        {health.items.map((item) => (
          <li key={item.key} className={`health-item is-${item.tone}`}>
            <span className="health-label">{item.label}</span>
            <span className="health-value">{item.value}</span>
          </li>
        ))}
      </ul>
      {health.problem ? (
        <p className="health-problem" role="status">
          {health.problem}
        </p>
      ) : null}
    </details>
  );
}
