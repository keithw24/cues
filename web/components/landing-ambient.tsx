"use client";

import { useEffect } from "react";

// Lets the hero glow drift only while someone can see it: the hero is on
// screen and the tab is visible. Off screen or hidden, the drift pauses where
// it is, so it resumes without a jump. Mounted only with web.landing_motion.
export default function LandingAmbient() {
  useEffect(() => {
    const hero = document.querySelector<HTMLElement>(".ln-hero");
    if (!hero) return;
    let onScreen = true;
    const apply = () => {
      if (onScreen && !document.hidden) hero.setAttribute("data-drift", "");
      else hero.removeAttribute("data-drift");
    };
    const observer = new IntersectionObserver(([entry]) => {
      onScreen = entry.isIntersecting;
      apply();
    });
    observer.observe(hero);
    document.addEventListener("visibilitychange", apply);
    apply();
    return () => {
      observer.disconnect();
      document.removeEventListener("visibilitychange", apply);
      hero.removeAttribute("data-drift");
    };
  }, []);
  return null;
}
