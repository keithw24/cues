"use client";

import { useEffect, useState, useSyncExternalStore } from "react";

const subscribeMotion = (callback: () => void) => {
  const query = window.matchMedia("(prefers-reduced-motion: reduce)");
  query.addEventListener("change", callback);
  return () => query.removeEventListener("change", callback);
};

/** Types the heading in, with a block caret, unless motion is reduced. */
export default function TypedHeading({ text }: { text: string }) {
  const reduced = useSyncExternalStore(
    subscribeMotion,
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    () => true,
  );
  const [shown, setShown] = useState(0);
  useEffect(() => {
    if (reduced) return;
    const timer = window.setInterval(
      () =>
        setShown((count) => {
          if (count >= text.length) window.clearInterval(timer);
          return Math.min(count + 1, text.length);
        }),
      32,
    );
    return () => window.clearInterval(timer);
  }, [reduced, text]);
  const typing = !reduced && shown < text.length;
  return (
    <h1 id="auth-heading" aria-label={text}>
      {/* The invisible copy holds the final size, so nothing below jumps. */}
      <span className="auth-heading-size" aria-hidden="true">
        {text}
      </span>
      <span className="auth-heading-typed" aria-hidden="true">
        {reduced ? text : text.slice(0, shown)}
        {typing ? <span className="auth-caret" /> : null}
      </span>
    </h1>
  );
}
