/** Light/dark choice, saved per browser. With no choice, each page keeps its
 * own default (Night for the landing page and dashboard, white for log-in). */
export const THEME_KEY = "cues-theme";
export type Theme = "light" | "dark";

/** Runs in <head> before first paint, so a saved choice never flashes. */
export const themeScript = `(function(){try{var t=localStorage.getItem("${THEME_KEY}");if(t==="light"||t==="dark")document.documentElement.setAttribute("data-theme",t)}catch(e){}})()`;
