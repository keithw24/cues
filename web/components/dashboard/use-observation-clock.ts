import { useEffect, useState } from "react";

/** The page clock, ticking once a second (and on return to the tab), or null until the first
 * tick. */
export function useObservationClock() {
  const [observationNow, setObservationNow] = useState<number | null>(null);
  useEffect(() => {
    const tick = () => setObservationNow(Date.now());
    const initial = setTimeout(tick, 0);
    const timer = setInterval(tick, 1000);
    const visible = () => {
      if (!document.hidden) tick();
    };
    document.addEventListener("visibilitychange", visible);
    return () => {
      clearTimeout(initial);
      clearInterval(timer);
      document.removeEventListener("visibilitychange", visible);
    };
  }, []);
  return observationNow;
}
