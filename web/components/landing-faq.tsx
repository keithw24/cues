import type { CSSProperties } from "react";
import { RiAddLine } from "@remixicon/react";

// Answers stay within what the PRD promises: local video, no face
// recognition, expression as supporting context only, teacher approval.
const questions = [
  {
    q: "What does Cues watch for?",
    a: "Simple tasks you choose: a raised hand or a thumbs up. One camera follows each student by their place in the frame.",
  },
  {
    q: "Does classroom video leave the room?",
    a: "No. Camera images and video stay on the classroom laptop. Only structured status updates, such as “Seat 2 finished thumbs up”, are sent on.",
  },
  {
    q: "Does Cues recognise faces or read emotions?",
    a: "No. There is no face recognition: a student is known only by their place in the frame. Facial-expression context can support a task signal, but it never raises an alert on its own, and Cues makes no claim about how a student feels.",
  },
  {
    q: "Who decides what changes for a student?",
    a: "You do. Cues flags a student who may need your attention and says why. Nothing about a student’s task, instructions or support changes unless you approve it.",
  },
  {
    q: "What do I need to run it?",
    a: "A laptop with a webcam in the classroom, and a browser for your dashboard.",
  },
  {
    q: "Is any real student data used?",
    a: "No. Cues runs on simulated student data only.",
  },
] as const;

export default function LandingFaq() {
  return (
    <section id="faq" className="ln-faq" aria-labelledby="faq-heading">
      <h2 id="faq-heading" data-reveal style={{ "--i": 0 } as CSSProperties}>
        Questions teachers ask
      </h2>
      <div
        className="ln-faq-list"
        data-reveal
        style={{ "--i": 1 } as CSSProperties}
      >
        {questions.map(({ q, a }) => (
          <details key={q}>
            <summary>
              {q}
              <RiAddLine aria-hidden="true" />
            </summary>
            <p>{a}</p>
          </details>
        ))}
      </div>
    </section>
  );
}
