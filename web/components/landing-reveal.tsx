"use client";

import { useEffect } from "react";

// Reveals [data-reveal] blocks once as they scroll into view. The page only
// hides them after this runs, so without JavaScript everything stays visible.
export default function LandingReveal() {
  useEffect(() => {
    const root = document.querySelector<HTMLElement>(".landing");
    if (!root) return;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          entry.target.setAttribute("data-shown", "");
          observer.unobserve(entry.target);
        }
      },
      { rootMargin: "0px 0px -10% 0px" },
    );
    root
      .querySelectorAll("[data-reveal]")
      .forEach((item) => observer.observe(item));
    root.setAttribute("data-reveal-ready", "");
    return () => {
      observer.disconnect();
      root.removeAttribute("data-reveal-ready");
    };
  }, []);
  return null;
}
