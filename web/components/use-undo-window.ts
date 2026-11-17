"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Holds a decision for a few seconds so the teacher can take it back. When the
 * window ends, or the page using it goes away, the saved action runs once.
 * Nothing reaches the database during the window.
 */
export function useUndoWindow(ms = 6000) {
  const [pending, setPending] = useState<string | null>(null);
  const action = useRef<(() => void | Promise<void>) | null>(null);
  const timer = useRef<number | null>(null);

  const flush = useCallback(() => {
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = null;
    const run = action.current;
    action.current = null;
    setPending(null);
    if (run) void run();
  }, []);

  const start = useCallback(
    (label: string, run: () => void | Promise<void>) => {
      action.current = run;
      setPending(label);
      timer.current = window.setTimeout(flush, ms);
    },
    [flush, ms],
  );

  const cancel = useCallback(() => {
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = null;
    action.current = null;
    setPending(null);
  }, []);

  // Leaving the page counts as "keep it": the decision is saved, not lost.
  useEffect(() => {
    const onHide = () => flush();
    window.addEventListener("pagehide", onHide);
    return () => {
      window.removeEventListener("pagehide", onHide);
      const run = action.current;
      action.current = null;
      if (timer.current !== null) window.clearTimeout(timer.current);
      if (run) void run();
    };
  }, [flush]);

  return { pending, start, cancel };
}
