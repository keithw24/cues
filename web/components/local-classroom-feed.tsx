"use client";

import { useState } from "react";
import { Card } from "@/components/ui/card";

/** The browser connects directly to the station's loopback stream; frames never cross the app server. */
export default function LocalClassroomFeed({ activity }: { activity: string }) {
  const [connection, setConnection] = useState<
    "off" | "connecting" | "live" | "error"
  >("off");
  const connect = () => {
    if (
      !["localhost", "127.0.0.1", "[::1]"].includes(window.location.hostname)
    ) {
      setConnection("error");
      return;
    }
    setConnection("connecting");
  };
  return (
    <Card
      className="classroom-feed"
      role="region"
      aria-labelledby="feed-heading"
    >
      <header className="feed-toolbar">
        <h2 id="feed-heading">Live classroom</h2>
        <span
          className={`feed-indicator ${connection === "live" ? "is-live" : ""}`}
          role="status"
        >
          {connection === "live"
            ? "Live video"
            : connection === "connecting"
              ? "Connecting"
              : "Video disconnected"}
        </span>
      </header>
      <div className="video-stage">
        {connection === "connecting" || connection === "live" ? (
          // MJPEG requires a native image; Next Image cannot optimize an open multipart stream.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            className="local-stream"
            src="http://127.0.0.1:8000/stream"
            alt="Local classroom camera feed"
            onLoad={() => setConnection("live")}
            onError={() => setConnection("error")}
          />
        ) : null}
        {connection !== "live" ? (
          <div className="video-placeholder">
            <p className="video-state-title">
              {connection === "error"
                ? "Local camera unavailable"
                : connection === "connecting"
                  ? "Connecting to the station"
                  : "Connect your classroom camera"}
            </p>
            <p>
              {connection === "error"
                ? "Check that the vision service is running on this station laptop, then retry."
                : "View the station’s local camera alongside live seat observations."}
            </p>
            {connection !== "connecting" ? (
              <button className="connect-feed" type="button" onClick={connect}>
                {connection === "error"
                  ? "Retry local feed"
                  : "Connect local feed"}
              </button>
            ) : null}
            {connection === "connecting" ? (
              <button type="button" onClick={() => setConnection("off")}>
                Cancel connection
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
      <footer className="feed-footer">
        <span className="feed-activity">{activity}</span>
        {connection === "live" ? (
          <button
            className="text-button"
            type="button"
            onClick={() => setConnection("off")}
          >
            Disconnect video
          </button>
        ) : null}
        <span className="privacy-note">
          Video processed locally · Frames never sent to the LLM
        </span>
      </footer>
    </Card>
  );
}
