"use client";

import { useEffect, useState } from "react";
import { WorkspaceIcon } from "@/components/workspace-icon";
import {
  OTHER_CAMERA,
  cameraHealth,
  healthSummary,
  readLocalVision,
  updatesFresh,
  type CameraHealth,
  type HealthSummary,
  type LocalVisionReading,
} from "@/lib/camera-health";
import { mayConnectLocalFeed } from "@/lib/local-feed-policy";

const POLL_MS = 3000;

type CameraHealthProps = {
  station: string;
  /** updated_at of each person's latest row at this station. */
  updatedAt: readonly (string | null | undefined)[];
  inView: number;
  /** Another camera is being refused on this station (from its writer row). */
  conflict: boolean;
  /** web.hosted_local_feed: the hosted dashboard may read this laptop's service. */
  hostedEnabled?: boolean;
  hostedOrigin?: string;
};

/** The strip's live state. */
function useCameraHealth({
  station,
  updatedAt,
  inView,
  conflict,
  hostedEnabled = false,
  hostedOrigin,
}: CameraHealthProps): { health: CameraHealth; summary: HealthSummary } {
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
  return { health, summary: healthSummary(health, inView) };
}

/** The four checks, each a label and a word. */
function HealthPills({ health }: { health: CameraHealth }) {
  return (
    <ul>
      {health.items.map((item) => (
        <li key={item.key} className={`health-item is-${item.tone}`}>
          <span className="health-label">{item.label}</span>
          <span className="health-value">{item.value}</span>
        </li>
      ))}
    </ul>
  );
}

/** The one sentence. A refused camera always shows, even with the strip closed;
 * other causes show only inside it. */
function HealthProblem({ health, open }: { health: CameraHealth; open: boolean }) {
  if (!health.problem) return null;
  if (!open && health.problem !== OTHER_CAMERA) return null;
  return (
    <p className="health-problem" role="status">
      {health.problem}
    </p>
  );
}

// The team's camera checks, folded behind a round "more" button (three dots)
// that sits in the row with the activity controls. Its badge is green when all
// is good, amber when something needs a look, grey while checking; the four
// checks open beside it. A refused second camera is always spelled out.
export function CameraHealthStrip(props: CameraHealthProps) {
  const { health, summary } = useCameraHealth(props);
  const [open, setOpen] = useState(false);
  return (
    <div className="health-strip" aria-label="Camera health" role="group">
      <div className="health-row">
        <button
          type="button"
          className="ws-icon-button health-more"
          aria-expanded={open}
          aria-controls="health-pills"
          aria-label={`Camera status: ${summary.label}`}
          title={`Camera status: ${summary.label}`}
          onClick={() => setOpen((value) => !value)}
        >
          <WorkspaceIcon name="more" />
          <span className={`health-dot is-${summary.tone}`} aria-hidden="true" />
        </button>
        <div id="health-pills" hidden={!open}>
          <HealthPills health={health} />
        </div>
      </div>
      <HealthProblem health={health} open={open} />
    </div>
  );
}
