/** Light/dark choice, saved per browser. With no choice, each page keeps its
 * own default: white for the landing page and log-in, Night for the dashboard. */
export const THEME_KEY = "cues-theme";
export type Theme = "light" | "dark";

/** Marks a theme the page chose itself (the landing page's light default), not the visitor. */
export const AUTO_THEME_ATTRIBUTE = "data-theme-auto";

/** Runs in <head> before first paint, so a saved choice never flashes. With no saved choice the
 * landing page (/) starts light; the mark lets the app drop it again when the visitor moves on to
 * a page with another default, which a client-side navigation would otherwise carry over. */
export const themeScript = `(function(){try{var d=document.documentElement,t=localStorage.getItem("${THEME_KEY}");if(t!=="light"&&t!=="dark"){t=location.pathname==="/"?"light":null;if(t)d.setAttribute("${AUTO_THEME_ATTRIBUTE}","1")}if(t)d.setAttribute("data-theme",t)}catch(e){}})()`;
