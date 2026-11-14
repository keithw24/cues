"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { RiCheckLine } from "@remixicon/react";

type Tone = "active" | "done" | "review";
type Seat = { seat: string; task: string; note: string; status: string; tone: Tone };
type Frame = { seats: Seat[]; suggest: boolean; approved: boolean };

// A scripted, simulated classroom: no real student data.
const seat1 = { seat: "Seat 1", task: "Thumbs up" };
const seat2 = { seat: "Seat 2", task: "Raise hand" };
const seat3 = { seat: "Seat 3", task: "Wave hello" };
const going = { status: "In progress", tone: "active" } as const;

const frames: Frame[] = [
  {
    seats: [
      { ...seat1, note: "Working on it", ...going },
      { ...seat2, note: "First attempt", ...going },
      { ...seat3, note: "Teacher-recorded gesture", ...going },
    ],
    suggest: false,
    approved: false,
  },
  {
    seats: [
      { ...seat1, note: "Finished on the second try", status: "Completed", tone: "done" },
      { ...seat2, note: "Second attempt", ...going },
      { ...seat3, note: "Teacher-recorded gesture", ...going },
    ],
    suggest: false,
    approved: false,
  },
  {
    seats: [
      { ...seat1, note: "Finished on the second try", status: "Completed", tone: "done" },
      { ...seat2, note: "Three attempts in two minutes", status: "Needs a look", tone: "review" },
      { ...seat3, note: "Teacher-recorded gesture", ...going },
    ],
    suggest: true,
    approved: false,
  },
  {
    seats: [
      { ...seat1, note: "Finished on the second try", status: "Completed", tone: "done" },
      { ...seat2, note: "Watching the gesture, then trying again", ...going },
      { ...seat3, note: "Finished first try", status: "Completed", tone: "done" },
    ],
    suggest: true,
    approved: true,
  },
];
const HOLD_MS = [1800, 1800, 2800, 3200];

const subscribe = (callback: () => void) => {
  const query = window.matchMedia("(prefers-reduced-motion: reduce)");
  query.addEventListener("change", callback);
  return () => query.removeEventListener("change", callback);
};

export default function LandingPreview() {
  const reduced = useSyncExternalStore(
    subscribe,
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    () => false,
  );
  const [index, setIndex] = useState(0);
  const [visible, setVisible] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Only play while the card is on screen.
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const observer = new IntersectionObserver(([entry]) =>
      setVisible(entry.isIntersecting),
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (reduced || !visible) return;
    const timer = window.setTimeout(
      () => setIndex((current) => (current + 1) % frames.length),
      HOLD_MS[index],
    );
    return () => window.clearTimeout(timer);
  }, [index, reduced, visible]);

  // With reduced motion, hold the frame that tells the whole story.
  const frame = frames[reduced ? 2 : index];

  return (
    <div
      ref={ref}
      className="ln-preview ln-enter"
      role="img"
      aria-label="Simulated classroom: one student finishes, another keeps trying, Cues suggests support and the teacher approves it."
    >
      <div className="ln-preview-head" aria-hidden="true">
        <span className="ln-preview-title">
          <span className="ln-live" />
          Classroom · Live
        </span>
        <span className="ln-chip">Simulated</span>
      </div>
      <ul className="ln-seats" aria-hidden="true">
        {frame.seats.map((seat) => (
          <li key={seat.seat} className="ln-seat">
            <div>
              <p className="ln-seat-meta">
                {seat.seat} · {seat.task}
              </p>
              <p className="ln-seat-note" key={seat.note}>
                {seat.note}
              </p>
            </div>
            <span className={`ln-status ln-status-${seat.tone}`}>
              {seat.status}
            </span>
          </li>
        ))}
      </ul>
      <div
        className="ln-suggestion"
        data-open={frame.suggest || undefined}
        aria-hidden="true"
      >
        <div className="ln-suggestion-inner">
          <p className="ln-seat-meta">Suggested support · Seat 2</p>
          <p className="ln-suggestion-text">
            Model the gesture once, then let them try again.
          </p>
          <div className="ln-suggestion-actions">
            <span
              className="ln-button ln-button-dark ln-button-small"
              data-done={frame.approved || undefined}
            >
              {frame.approved ? (
                <>
                  <RiCheckLine aria-hidden="true" />
                  Approved
                </>
              ) : (
                "Approve"
              )}
            </span>
            {frame.approved ? null : (
              <span className="ln-button ln-button-outline ln-button-small">
                Not now
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
