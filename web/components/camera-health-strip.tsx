"use client";

import { useEffect, useState } from "react";
import {
  cameraHealth,
  readLocalVision,
  updatesFresh,
  type LocalVisionReading,
} from "@/lib/camera-health";
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
  const [now, setNow] = useState(() => Date.now());
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
  return (
    <section className="health-strip" aria-label="Camera health">
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
    </section>
  );
}
