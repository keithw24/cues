import type { CSSProperties } from "react";
import { RiCheckboxCircleLine, RiEyeLine, RiHand } from "@remixicon/react";
import "./landing-steps.css";

// With the live demo above, the page explains the flow in three short steps
// instead of repeating it with mock cards.
const steps = [
  {
    id: undefined,
    icon: RiHand,
    title: "Pick a Task",
    text: "Choose a raised hand or a thumbs up from the list, then press Start. The whole class works on it.",
  },
  {
    id: undefined,
    icon: RiEyeLine,
    title: "Cues Watches",
    text: "One camera follows each student by their place in the frame, tracking who has finished and who keeps trying.",
  },
  {
    id: "control",
    icon: RiCheckboxCircleLine,
    title: "You Decide",
    text: "Cues flags who may need you and says why. Nothing changes for a student until you approve it.",
  },
] as const;

export default function LandingSteps() {
  return (
    <section id="how" className="ln-steps" aria-labelledby="how-heading">
      <h2 id="how-heading" data-reveal style={{ "--i": 0 } as CSSProperties}>
        How It Works
      </h2>
      <ol>
        {steps.map((step, index) => (
          <li
            key={step.title}
            id={step.id}
            data-reveal
            style={{ "--i": index + 1 } as CSSProperties}
          >
            <span className="ln-step-icon" aria-hidden="true">
              <step.icon />
            </span>
            <h3>{step.title}</h3>
            <p>{step.text}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}
