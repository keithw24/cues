"use client";

import { useEffect, useRef, useState } from "react";
import CuesBlob from "@/components/cues-blob";

// The Cues companion perched on the To review pill. It is always Cues itself,
// never a student, and it reacts only to the teacher's own queue:
//   - nothing waiting: blue, resting on the pill;
//   - a request arrives: it turns orange and hops (again for each new one);
//   - the queue clears: it eats the count, smiles and turns green, then
//     settles back to blue.
// Decoration only (aria-hidden): the pill's text and count carry the meaning.
type Phase = "rest" | "waiting" | "eating" | "done";

const COLORS = {
  rest: "#5763d2",
  waiting: "#e8741f",
  eating: "#e8741f",
  done: "#34a46a",
} as const satisfies Record<Phase, `#${string}`>;

/** The chomp runs this long; then it stays green this long before resting. */
const EAT_MS = 700;
const DONE_MS = 2200;

export function ReviewCompanion({ count }: { count: number }) {
  const previous = useRef(count);
  const [phase, setPhase] = useState<Phase>(count > 0 ? "waiting" : "rest");
  const [eaten, setEaten] = useState(0);
  const [hop, setHop] = useState(0);

  useEffect(() => {
    const before = previous.current;
    previous.current = count;
    if (count > before) {
      queueMicrotask(() => {
        setPhase("waiting");
        setHop((n) => n + 1);
      });
      return;
    }
    if (count === 0 && before > 0) {
      queueMicrotask(() => {
        setEaten(before);
        setPhase("eating");
      });
      const ate = window.setTimeout(() => {
        setPhase("done");
        setHop((n) => n + 1);
      }, EAT_MS);
      const rest = window.setTimeout(() => setPhase("rest"), EAT_MS + DONE_MS);
      return () => {
        window.clearTimeout(ate);
        window.clearTimeout(rest);
      };
    }
  }, [count]);

  return (
    <>
      {/* The count it eats sits in the count's own slot, so the pill keeps its
          width while it goes. */}
      {phase === "eating" ? (
        <span className="ws-count review-companion-crumb" aria-hidden="true">
          {eaten}
        </span>
      ) : null}
      <span className="review-companion" data-phase={phase} aria-hidden="true">
        <span className="review-companion-body">
          <CuesBlob
            size={30}
            wander={false}
            seed={11}
            color={COLORS[phase]}
            face={phase === "eating" || phase === "done" ? "happy" : undefined}
            look={
              phase === "eating"
                ? [0.5, -0.6]
                : phase === "rest"
                  ? [0, 0]
                  : [0.5, -0.4]
            }
            bounce={hop}
          />
        </span>
      </span>
    </>
  );
}
