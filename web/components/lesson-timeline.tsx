"use client";

import { useEffect, useState } from "react";

// A thin strip of the last hour. Marks come only from backend timestamps
// (when a review was created); nothing is recorded in the browser.
const WINDOW_MS = 60 * 60 * 1000;

export type TimelineMark = { id: string; at: string; label: string };

const clock = (value: number) =>
  new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));

export function LessonTimeline({ marks }: { marks: TimelineMark[] }) {
  // Set after mount, so the server and the first client render agree.
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    const tick = () => setNow(Date.now());
    const first = window.setTimeout(tick, 0);
    const timer = window.setInterval(tick, 30_000);
    return () => {
      window.clearTimeout(first);
      window.clearInterval(timer);
    };
  }, []);
  if (now === null) return <section className="timeline" aria-hidden="true" />;
  const start = now - WINDOW_MS;
  const recent = marks.filter((mark) => Date.parse(mark.at) >= start);
  const earlier = marks.length - recent.length;
  return (
    <section className="timeline" aria-labelledby="timeline-heading">
      <header className="timeline-head">
        <h2 id="timeline-heading">Last hour</h2>
        {earlier ? <span>{earlier} earlier</span> : null}
      </header>
      <div className="timeline-track">
        {recent.map((mark) => {
          const left = ((Date.parse(mark.at) - start) / WINDOW_MS) * 100;
          return (
            <span
              key={mark.id}
              className="timeline-mark"
              style={{ left: `${Math.min(100, Math.max(0, left))}%` }}
            >
              <span className="sr-only">
                {mark.label} at {clock(Date.parse(mark.at))}
              </span>
              <span className="timeline-tip" aria-hidden="true">
                {mark.label} · {clock(Date.parse(mark.at))}
              </span>
            </span>
          );
        })}
        <span className="timeline-now" aria-hidden="true">
          now
        </span>
      </div>
      <div className="timeline-scale" aria-hidden="true">
        <span>{clock(start)}</span>
        <span>{clock(now)}</span>
      </div>
      {!recent.length ? (
        <p className="timeline-empty">Nothing flagged in the last hour.</p>
      ) : null}
    </section>
  );
}
