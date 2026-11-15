import type { CSSProperties } from "react";
import { RiFocus3Line, RiGroupLine, RiListCheck2 } from "@remixicon/react";

// Replaces the privacy section with the same card style (ln-privacy, ln-facts), written for
// special-education (SEN) teaching from what staff say they need. Every line describes something
// Cues really does; it makes no claim about reports, diagnoses or how a student feels. The privacy
// answers stay in the FAQ.
const needs = [
  {
    icon: RiGroupLine,
    title: "Many Needs, Few Hands",
    text: "Every student may need something different at once, often with little extra support. Cues keeps watch on simple tasks so you can keep your eyes on your students.",
  },
  {
    icon: RiListCheck2,
    title: "Less Tracking by Hand",
    text: "Who has finished, who is still going and who may need you is kept for you while the activity runs, so you are not tallying on paper.",
  },
  {
    icon: RiFocus3Line,
    title: "Fits How You Already Teach",
    text: "Pick a task, then teach. There is nothing to set up during class, and Cues only speaks up when someone may need you.",
  },
] as const;

export default function LandingNeeds() {
  return (
    <section id="needs" className="ln-privacy" aria-labelledby="needs-heading">
      <h2 id="needs-heading" data-reveal style={{ "--i": 0 } as CSSProperties}>
        Made for Special Education (SEN) Classrooms
      </h2>
      <p data-reveal style={{ "--i": 1 } as CSSProperties}>
        Progress notes and constant check-ins take time that SEN teaching rarely
        has. Cues takes care of the watching, so your attention stays on the
        students.
      </p>
      <ul className="ln-facts">
        {needs.map((need, index) => (
          <li
            key={need.title}
            data-reveal
            style={{ "--i": index + 2 } as CSSProperties}
          >
            <need.icon />
            <strong>{need.title}</strong>
            <span>{need.text}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
