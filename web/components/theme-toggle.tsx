"use client";

import { useSyncExternalStore } from "react";
import { RiMoonLine, RiSunLine } from "@remixicon/react";
import { THEME_KEY, type Theme } from "@/lib/theme";

// Light/dark switch. The choice lives on <html data-theme> and in
// localStorage; with no choice each page keeps its own default.
const subscribe = (callback: () => void) => {
  const observer = new MutationObserver(callback);
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["data-theme"],
  });
  return () => observer.disconnect();
};

export function ThemeToggle({
  pageDefault,
  className,
}: {
  pageDefault: Theme;
  className?: string;
}) {
  const theme = useSyncExternalStore(
    subscribe,
    () => (document.documentElement.dataset.theme as Theme) || pageDefault,
    () => pageDefault,
  );
  const next: Theme = theme === "dark" ? "light" : "dark";
  return (
    <button
      type="button"
      className={className ?? "theme-toggle"}
      aria-label={`Switch to ${next} mode`}
      title={`Switch to ${next} mode`}
      onClick={() => {
        // Switch every color at once: no transitions fire during the swap.
        const root = document.documentElement;
        const pause = document.createElement("style");
        pause.textContent = "*,*::before,*::after{transition:none!important}";
        document.head.appendChild(pause);
        root.dataset.theme = next;
        void getComputedStyle(root).color;
        requestAnimationFrame(() => pause.remove());
        try {
          localStorage.setItem(THEME_KEY, next);
        } catch {}
      }}
    >
      {theme === "dark" ? (
        <RiSunLine aria-hidden="true" />
      ) : (
        <RiMoonLine aria-hidden="true" />
      )}
    </button>
  );
}
