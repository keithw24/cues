import { RiAddLine } from "@remixicon/react";

// Answers stay within what the PRD promises: local video, no face
// recognition, expression as supporting context only, teacher approval.
const questions = [
  {
    q: "What does Cues watch for?",
    a: "Simple tasks you choose: a raised hand, a thumbs up, or a gesture you record yourself. One camera follows each seat by where it sits in the frame.",
  },
  {
    q: "Does classroom video leave the room?",
    a: "No. Camera images and video are processed on the station laptop. Only short task events, such as “Seat 2 finished thumbs up”, are sent on.",
  },
  {
    q: "Does Cues recognise faces or read emotions?",
    a: "No. There is no face recognition: a seat is known only by its place in the frame. Facial-expression context can support a task signal, but it never raises an alert on its own, and Cues makes no claim about how a student feels.",
  },
  {
    q: "Who decides what changes for a student?",
    a: "You do. Cues suggests support from your approved list and says why. Nothing about a student’s task or instructions changes until you approve it.",
  },
  {
    q: "What do I need to run it?",
    a: "A laptop with a webcam at the station, and a browser for your dashboard.",
  },
  {
    q: "Is any real student data used?",
    a: "Not yet. During the hackathon, Cues runs on simulated student data only.",
  },
] as const;

export default function LandingFaq() {
  return (
    <section id="faq" className="ln-faq" aria-labelledby="faq-heading">
      <h2 id="faq-heading">Questions teachers ask</h2>
      <div className="ln-faq-list">
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
