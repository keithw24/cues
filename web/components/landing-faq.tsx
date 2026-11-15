import type { CSSProperties } from "react";
import { RiAddLine } from "@remixicon/react";

// Answers stay within what the PRD promises: local video, no face
// recognition, expression as supporting context only, teacher approval.
const questions = [
  {
    q: "What Does Cues Watch For?",
    a: "Simple tasks you choose: a raised hand or a thumbs up. One camera follows each student by their place in the frame.",
  },
  {
    q: "Does Classroom Video Leave the Room?",
    a: "No. Camera images and video stay on the classroom laptop. Only structured status updates, such as “Seat 2 finished thumbs up”, are sent on.",
  },
  {
    q: "Does Cues Recognise Faces or Read Emotions?",
    a: "No. There is no face recognition: a student is known only by their place in the frame. Facial-expression context can support a task signal, but it never raises an alert on its own, and Cues makes no claim about how a student feels.",
  },
  {
    q: "Is Cues Made for Special Education (SEN)?",
    a: "Yes. It is built for special-education teachers and the way they work: simple observable tasks, one adult watching many students, and every change to a student’s task or support waiting for your approval. It does not diagnose or assess a student, and it replaces no professional judgement.",
  },
  {
    q: "Will This Add Work to My Day?",
    a: "It is meant not to. There is nothing to set up during class: pick a task and teach. Cues tracks who has finished for you and only flags someone who may need you, so your attention stays on your students.",
  },
  {
    q: "Who Decides What Changes for a Student?",
    a: "You do. Cues flags a student who may need your attention and says why. Nothing about a student’s task, instructions or support changes unless you approve it.",
  },
  {
    q: "What Do I Need to Run It?",
    a: "A laptop with a webcam in the classroom, and a browser for your dashboard.",
  },
  {
    q: "Is Any Real Student Data Used?",
    a: "No. Cues runs on simulated student data only.",
  },
] as const;

export default function LandingFaq() {
  return (
    <section id="faq" className="ln-faq" aria-labelledby="faq-heading">
      <h2 id="faq-heading" data-reveal style={{ "--i": 0 } as CSSProperties}>
        Questions Teachers Ask
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
