"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { WorkspaceIcon } from "@/components/workspace-icon";
import CuesMark from "@/components/cues-mark";
import {
  PersonRowContent,
  ReviewRowContent,
} from "@/components/workspace-rows";
import "./workspace.css";

// The real dashboard's banner and rows, driven by a scripted, simulated
// classroom. Nothing is read from or sent to Supabase.
type Tone = "working" | "done" | "review" | "quiet";
type Person = { name: string; status: string; tone: Tone };
type Frame = { caption: string; people: Person[]; review: boolean };

const ready: Omit<Person, "name"> = {
  status: "Ready",
  tone: "quiet",
};
const working: Omit<Person, "name"> = {
  status: "Working",
  tone: "working",
};
const done: Omit<Person, "name"> = {
  status: "Finished",
  tone: "done",
};
const review: Omit<Person, "name"> = {
  status: "Needs you",
  tone: "review",
};

const frames: Frame[] = [
  {
    caption:
      "You start a thumbs-up task with four simulated students. Cues watches each one’s place in the frame.",
    people: [
      { name: "Maya", ...working },
      { name: "Leo", ...working },
      { name: "Ava", ...working },
      { name: "Noah", ...ready },
    ],
    review: false,
  },
  {
    caption: "Maya finishes. Nothing for you to do.",
    people: [
      { name: "Maya", ...done },
      { name: "Leo", ...working },
      { name: "Ava", ...working },
      { name: "Noah", ...working },
    ],
    review: false,
  },
  {
    caption:
      "Leo keeps trying without finishing, so Cues asks you to take a look.",
    people: [
      { name: "Maya", ...done },
      { name: "Leo", ...review },
      { name: "Ava", ...working },
      { name: "Noah", ...working },
    ],
    review: true,
  },
  {
    caption:
      "You check in with Leo and close the review. He’s back to working.",
    people: [
      { name: "Maya", ...done },
      { name: "Leo", ...working },
      { name: "Ava", ...done },
      { name: "Noah", ...working },
    ],
    review: false,
  },
];
const HOLD_MS = [2600, 2400, 3800, 3200];

const subscribe = (callback: () => void) => {
  const query = window.matchMedia("(prefers-reduced-motion: reduce)");
  query.addEventListener("change", callback);
  return () => query.removeEventListener("change", callback);
};

export default function LandingDemo() {
  const reduced = useSyncExternalStore(
    subscribe,
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    () => false,
  );
  const [index, setIndex] = useState(0);
  const [visible, setVisible] = useState(false);
  const ref = useRef<HTMLElement>(null);

  // Only play while the demo is on screen.
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
    <figure ref={ref} className="ln-demo">
      <p className="sr-only">
        A demo of the Cues dashboard with simulated students: one finishes,
        another keeps trying, Cues asks the teacher to take a look, and the
        teacher closes the review.
      </p>
      <div className="dashboard-shell ws-demo" aria-hidden="true">
        <div className="ws-demo-rail">
          <CuesMark className="brand-mark" size={26} />
          <span className="ws-demo-rail-item is-current">
            <WorkspaceIcon name="classroom" />
          </span>
          <span className="ws-demo-rail-item">
            <WorkspaceIcon name="account" />
          </span>
        </div>
        <div className="ws-demo-main">
          <div className="ws-hero">
            <header className="page-intro">
              <div>
                <h1>your classroom</h1>
                <p className="ws-subtitle">Thumbs up</p>
              </div>
              <span className="ws-pill">Simulated students</span>
            </header>
          </div>
          <div className="ws-demo-grid">
            <section className="ws-panel">
              <header className="panel-heading">
                <h2>People</h2>
                <span className="ws-caption">Left to right</span>
              </header>
              <ul className="row-list">
                {frame.people.map((person) => (
                  <li key={person.name}>
                    <div className="ws-row">
                      <PersonRowContent
                        name={person.name}
                        status={person.status}
                        tone={person.tone}
                        activity=""
                      />
                    </div>
                  </li>
                ))}
              </ul>
            </section>
            <section className="ws-panel">
              <header className="panel-heading">
                <h2>Needs you</h2>
                {frame.review ? <span className="ws-count">1</span> : null}
              </header>
              {frame.review ? (
                <ul className="row-list ws-demo-arrive">
                  <li>
                    <div className="ws-row">
                      <ReviewRowContent
                        name="Leo"
                        meta=""
                        time="2026-11-14T09:41:00"
                        timeLabel="9:41 AM"
                        elevated
                      />
                    </div>
                  </li>
                </ul>
              ) : (
                <p className="panel-empty ws-demo-arrive">
                  All clear. Cues will ask when someone may need you.
                </p>
              )}
            </section>
          </div>
        </div>
      </div>
      <figcaption className="ln-demo-caption" key={frame.caption}>
        {frame.caption}
      </figcaption>
    </figure>
  );
}
