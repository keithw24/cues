"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import dynamic from "next/dynamic";
import type { BlobShape } from "@/components/cues-blob";
import { WorkspaceIcon } from "@/components/workspace-icon";
import { ReviewCompanion } from "@/components/review-companion";
import CuesMark from "@/components/cues-mark";
import { ReviewRowContent, initials } from "@/components/workspace-rows";
import "./workspace.css";

// The real dashboard's layout (title, camera beside ATTENTION, the student
// cards underneath), driven by a scripted, simulated classroom. The camera
// is an illustration of the vision overlay (a box and label per person), not
// video. Nothing is read from or sent to Supabase.
type Tone = "working" | "done" | "review" | "quiet";
type Person = { name: string; status: string; tone: Tone };

// Each simulated student is drawn as one of the sign-in companion's
// characters: its own shape and color, eyes neutral. The box around it carries
// the status, as the vision overlay does; the character never acts out a mood.
const Character = dynamic(() => import("@/components/cues-blob"), {
  ssr: false,
});
// Each has its own animation seed, so their idle moves never line up.
const looks: Record<
  string,
  { shape: BlobShape; color: `#${string}`; seed: number }
> = {
  Michelle: { shape: "capsule", color: "#3aa58f", seed: 1103 },
  Keith: { shape: "cube", color: "#e07a5f", seed: 2741 },
  Evan: { shape: "sphere", color: "#5763d2", seed: 3919 },
  Eric: { shape: "trapezoid", color: "#e2a33b", seed: 5087 },
};
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
  status: "Check in",
  tone: "review",
};

const frames: Frame[] = [
  {
    caption:
      "You start a thumbs-up task with four simulated students. Cues watches each one’s place in the frame.",
    people: [
      { name: "Michelle", ...working },
      { name: "Keith", ...working },
      { name: "Evan", ...working },
      { name: "Eric", ...ready },
    ],
    review: false,
  },
  {
    caption: "Michelle finishes. Nothing for you to do.",
    people: [
      { name: "Michelle", ...done },
      { name: "Keith", ...working },
      { name: "Evan", ...working },
      { name: "Eric", ...working },
    ],
    review: false,
  },
  {
    caption:
      "Keith keeps trying without finishing, so Cues asks you to take a look.",
    people: [
      { name: "Michelle", ...done },
      { name: "Keith", ...review },
      { name: "Evan", ...working },
      { name: "Eric", ...working },
    ],
    review: true,
  },
  {
    caption:
      "You check in with Keith and close the review. Keith is back to working.",
    people: [
      { name: "Michelle", ...done },
      { name: "Keith", ...working },
      { name: "Evan", ...done },
      { name: "Eric", ...working },
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

export default function LandingDemo({ companion = false }: { companion?: boolean }) {
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
        Simulated students: a demo of the Cues classroom where one finishes,
        another keeps trying, Cues asks the teacher to check in, and the
        teacher closes the review.
      </p>
      <div className="dashboard-shell ws-demo" aria-hidden="true">
        <div className="ws-demo-rail">
          <CuesMark className="brand-mark" size={26} />
          <span className="ws-demo-rail-item is-current">
            <WorkspaceIcon name="classroom" />
          </span>
          <span className="ws-demo-rail-item">
            <WorkspaceIcon name="review" />
            {frame.review ? <span className="rail-badge">1</span> : null}
          </span>
          <span className="ws-demo-rail-item">
            <WorkspaceIcon name="account" />
          </span>
        </div>
        <div className="ws-demo-main">
          <div className="ws-hero">
            <header className="page-intro">
              <h1>classroom</h1>
              <span
                className={`ws-pill review-link${companion ? " has-companion" : ""}${frame.review ? " has-items" : ""}`}
              >
                TO REVIEW
                {frame.review ? <span className="ws-count">1</span> : null}
                {companion ? (
                  <ReviewCompanion count={frame.review ? 1 : 0} />
                ) : null}
              </span>
            </header>
            <div className="session-controls">
              <div className="session-row">
                <span className="ws-demo-select">
                  Thumbs up
                  <WorkspaceIcon name="chevronDown" />
                </span>
                <span className="ws-pill is-dark">Change activity</span>
                <span className="ws-pill">End</span>
                <span className="ws-icon-button">
                  <WorkspaceIcon name="refresh" />
                </span>
              </div>
            </div>
          </div>
          <div className="monitor-workspace">
            <section className="ws-panel classroom-feed">
              <header className="panel-heading">
                <h2>Camera</h2>
              </header>
              <div className="video-stage ws-demo-stage">
                {frame.people.map((person, index) => (
                  <span
                    key={person.name}
                    className={`ws-demo-box is-${person.tone}`}
                    style={{ left: `${6 + index * 23.5}%` }}
                  >
                    <span className="ws-demo-figure">
                      <Character
                        size={84}
                        wander={false}
                        glance
                        seed={looks[person.name].seed}
                        shape={looks[person.name].shape}
                        color={looks[person.name].color}
                      />
                    </span>
                    <span className="ws-demo-tag">{person.name}</span>
                  </span>
                ))}
              </div>
            </section>
            <section className="ws-panel class-panel">
              <header className="panel-heading">
                <h2>Attention</h2>
                {frame.review ? <span className="ws-count">1</span> : null}
              </header>
              {frame.review ? (
                <ul className="row-list ws-demo-arrive">
                  <li>
                    <div className="ws-row">
                      <ReviewRowContent
                        name="Keith"
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
          <ul className="strip-track ws-demo-strip">
            {frame.people.map((person) => (
              <li key={person.name}>
                <div className={`strip-card is-${person.tone}`}>
                  <span className="row-avatar is-ring">
                    {initials(person.name)}
                  </span>
                  <span className="row-body">
                    <span className="row-name">{person.name}</span>
                    <span className="strip-status">{person.status}</span>
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>
      <figcaption className="ln-demo-caption" key={frame.caption}>
        {frame.caption}
      </figcaption>
    </figure>
  );
}
