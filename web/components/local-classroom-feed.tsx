"use client";

import { useEffect, useState } from "react";
import { mayConnectLocalFeed } from "@/lib/local-feed-policy";
import { WorkspaceIcon } from "@/components/workspace-icon";

// Remembers, in this browser only, that the teacher turned the video on.
const VIDEO_KEY = "cues-video";


/** The classroom camera, center of the dashboard, with the vision service's own
 * overlay (a box and label per person, hand points). The browser reads this
 * laptop's loopback stream directly; frames never cross the app server or
 * leave the laptop. Off, it is one slim strip. */
export default function LocalClassroomFeed({hostedEnabled = false, hostedOrigin = "https://cues.nyc"}: {hostedEnabled?: boolean; hostedOrigin?: string}) {
  const [connection, setConnection] = useState<
    "off" | "connecting" | "live" | "error"
  >("off");
  const remember = (on: boolean) => {
    try {
      if (on) localStorage.setItem(VIDEO_KEY, "on");
      else localStorage.removeItem(VIDEO_KEY);
    } catch {}
  };
  const connect = () => {
    if (!mayConnectLocalFeed(window.location.origin, hostedEnabled, hostedOrigin)) {
      setConnection("error");
      return;
    }
    remember(true);
    setConnection("connecting");
  };
  const turnOff = () => {
    remember(false);
    setConnection("off");
  };
  // Turn the video back on if the teacher left it on last time.
  useEffect(() => {
    let on = false;
    try {
      on = localStorage.getItem(VIDEO_KEY) === "on";
    } catch {}
    if (on && mayConnectLocalFeed(window.location.origin, hostedEnabled, hostedOrigin)) {
      const timer = setTimeout(() => setConnection("connecting"), 0);
      return () => clearTimeout(timer);
    }
  }, [hostedEnabled, hostedOrigin]);
  const streaming = connection === "connecting" || connection === "live";
  return (
    <section
      className="ws-panel classroom-feed"
      data-streaming={streaming || undefined}
      aria-labelledby="feed-heading"
    >
      <header className="panel-heading">
        <h2 id="feed-heading">Camera</h2>
        {connection === "live" ? (
          <button className="ws-pill" type="button" onClick={turnOff}>
            Turn off
          </button>
        ) : null}
      </header>
      <div className="video-stage" data-live={connection === "live" || undefined}>
        {streaming ? (
          // MJPEG requires a native image; Next Image cannot optimize an open multipart stream.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            className="local-stream"
            src="http://127.0.0.1:8000/stream"
            crossOrigin="anonymous"
            alt="Your classroom camera, with a box around each person Cues is tracking"
            onLoad={() => setConnection("live")}
            onError={() => setConnection("error")}
          />
        ) : null}
        {connection !== "live" ? (
          <div className="video-placeholder">
            <WorkspaceIcon name="camera" />
            {connection === "error" ? (
              <p>Can’t reach this laptop’s camera. Start Cues vision on this laptop and allow Local network access in your browser’s site permissions, then try again.</p>
            ) : connection === "connecting" ? (
              <p>Connecting to this laptop’s camera…</p>
            ) : null}
            {connection === "connecting" ? (
              <button type="button" className="ws-pill" onClick={turnOff}>
                Cancel
              </button>
            ) : (
              <button type="button" className="ws-pill is-dark" onClick={connect}>
                {connection === "error" ? "Try again" : "Turn on video"}
              </button>
            )}
          </div>
        ) : null}
      </div>
    </section>
  );
}
