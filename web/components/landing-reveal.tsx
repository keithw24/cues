"use client";

import { useEffect } from "react";

// Reveals [data-reveal] blocks once as they come into view. Anything above
// the fold line counts, so blocks skipped by a fast scroll or an anchor jump
// still appear. The page only hides them after this runs, so without
// JavaScript everything stays visible.
export default function LandingReveal() {
  useEffect(() => {
    const root = document.querySelector<HTMLElement>(".landing");
    if (!root) return;
    let pending = Array.from(
      root.querySelectorAll<HTMLElement>("[data-reveal]"),
    );
    const reveal = (item: HTMLElement) => {
      item.setAttribute("data-shown", "");
      // Once the staggered reveal is over, drop its delay so hover feels
      // immediate. The timeout covers the case with no transition.
      const settle = () => item.setAttribute("data-settled", "");
      item.addEventListener("transitionend", settle, { once: true });
      window.setTimeout(settle, 1000);
    };
    let frame = 0;
    const check = () => {
      frame = 0;
      const fold = window.innerHeight * 0.9;
      pending = pending.filter((item) => {
        if (item.getBoundingClientRect().top >= fold) return true;
        reveal(item);
        return false;
      });
      if (!pending.length) stop();
    };
    const schedule = () => {
      if (!frame) frame = window.requestAnimationFrame(check);
    };
    const stop = () => {
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
    };
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    root.setAttribute("data-reveal-ready", "");
    check();
    return () => {
      stop();
      window.cancelAnimationFrame(frame);
      root.removeAttribute("data-reveal-ready");
    };
  }, []);
  return null;
}
