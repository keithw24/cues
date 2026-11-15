"use client";

import { useEffect } from "react";
import { AUTO_THEME_ATTRIBUTE, THEME_KEY } from "@/lib/theme";

// The landing page starts light when the visitor has not chosen a theme. The head script does it
// on a full page load (no flash); this covers arriving by a link inside the app, and takes the
// default away again when leaving, so the dashboard keeps its own default (Night).
export default function LandingThemeDefault() {
  useEffect(() => {
    const root = document.documentElement;
    let chosen = false;
    try {
      const saved = localStorage.getItem(THEME_KEY);
      chosen = saved === "light" || saved === "dark";
    } catch {}
    if (!chosen && !root.hasAttribute("data-theme")) {
      root.setAttribute("data-theme", "light");
      root.setAttribute(AUTO_THEME_ATTRIBUTE, "1");
    }
    return () => {
      if (root.hasAttribute(AUTO_THEME_ATTRIBUTE)) {
        root.removeAttribute(AUTO_THEME_ATTRIBUTE);
        root.removeAttribute("data-theme");
      }
    };
  }, []);
  return null;
}
