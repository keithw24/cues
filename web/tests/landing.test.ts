import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { isEnabled } from "../lib/flags.ts";

const read = (path: string) =>
  readFileSync(new URL(path, import.meta.url), "utf8");

test("landing defaults on and the server override turns it off", () => {
  assert.equal(isEnabled("web.landing", {}), true);
  assert.equal(isEnabled("web.landing", { CUES_FLAG_WEB_LANDING: "0" }), false);
});

test("with landing off, / still renders the dashboard", () => {
  const home = read("../app/page.tsx");
  assert.match(
    home,
    /if \(!isEnabled\("web\.landing"\)\) return DashboardPage\(\);/,
  );
  assert.match(
    read("../app/dashboard/page.tsx"),
    /isEnabled\("web\.dashboard"\)/,
  );
});

test("sign-up defaults on and shows an unavailable page when turned off", () => {
  assert.equal(isEnabled("web.teacher_signup", {}), true);
  assert.equal(
    isEnabled("web.teacher_signup", { CUES_FLAG_WEB_TEACHER_SIGNUP: "0" }),
    false,
  );
  const page = read("../app/signup/page.tsx");
  assert.match(page, /if \(!isEnabled\("web\.teacher_signup"\)\)/);
  assert.match(page, /Teacher sign-up is unavailable\./);
  // With sign-up off, the landing page sends teachers to sign in instead.
  assert.match(
    read("../components/landing.tsx"),
    /isEnabled\("web\.teacher_signup"\) \? "\/signup" : "\/login"/,
  );
});

test("the email-confirmed page is unavailable when sign-up is off", () => {
  const page = read("../app/auth/confirmed/page.tsx");
  assert.match(page, /if \(!isEnabled\("web\.teacher_signup"\)\)/);
  assert.match(page, /Teacher sign-up is unavailable\./);
});

test("FAQ and site footer default on; turned off, the landing keeps its short footer", () => {
  assert.equal(isEnabled("web.landing_faq", {}), true);
  assert.equal(
    isEnabled("web.landing_faq", { CUES_FLAG_WEB_LANDING_FAQ: "0" }),
    false,
  );
  assert.equal(
    isEnabled("web.landing_faq", { CUES_FLAG_WEB_LANDING_FAQ: "1" }),
    true,
  );
  const landing = read("../components/landing.tsx");
  assert.match(landing, /const faq = isEnabled\("web\.landing_faq"\);/);
  assert.match(landing, /\{faq \? <LandingFaq \/> : null\}/);
  assert.match(landing, /<footer className="ln-footer">/);
});

test("the dashboard demo defaults on; turned off, the hero keeps the older preview", () => {
  assert.equal(isEnabled("web.landing_demo", {}), true);
  assert.equal(
    isEnabled("web.landing_demo", { CUES_FLAG_WEB_LANDING_DEMO: "0" }),
    false,
  );
  const landing = read("../components/landing.tsx");
  assert.match(
    landing,
    /preview=\{demo \? <LandingDemo \/> : <LandingPreview \/>\}/,
  );
  // The demo reuses the dashboard's own rows and never touches Supabase.
  const demo = read("../components/landing-demo.tsx");
  assert.match(demo, /from "@\/components\/workspace-rows"/);
  assert.doesNotMatch(
    demo,
    /@\/lib\/(supabase|dashboard-feed|teacher-review-feed)/,
  );
});

test("with the demo on, the mock task and approval cards give way to the steps", () => {
  const landing = read("../components/landing.tsx");
  assert.match(landing, /\{demo \? \(\s*<LandingSteps \/>\s*\) : \(/);
  // The flag-off page keeps both original sections and their anchors.
  assert.match(landing, /id="how"\s+className="ln-section"/);
  assert.match(landing, /id="control"/);
  const steps = read("../components/landing-steps.tsx");
  assert.match(steps, /id="how"/);
  assert.match(steps, /id: "control"/);
});

test("the demo turns on with its override, stays labelled and stays offline", () => {
  assert.equal(
    isEnabled("web.landing_demo", { CUES_FLAG_WEB_LANDING_DEMO: "1" }),
    true,
  );
  const demo = read("../components/landing-demo.tsx");
  assert.match(demo, /Simulated students/);
  assert.match(demo, /simulated students/);
  // The demo's rows must not pull in a feed or Supabase either.
  assert.doesNotMatch(
    read("../components/workspace-rows.tsx"),
    /@\/lib\/(supabase|dashboard-feed|teacher-review-feed)/,
  );
});

test("scroll reveal defaults on; without it every section is visible", () => {
  assert.equal(isEnabled("web.landing_motion", {}), true);
  assert.equal(
    isEnabled("web.landing_motion", { CUES_FLAG_WEB_LANDING_MOTION: "0" }),
    false,
  );
  assert.equal(
    isEnabled("web.landing_motion", { CUES_FLAG_WEB_LANDING_MOTION: "1" }),
    true,
  );
  // Both the scroll reveal and the hero glow drift mount only with the flag.
  assert.match(
    read("../components/landing.tsx"),
    /\{motion \? \(\s*<>\s*<LandingReveal \/>\s*<LandingAmbient \/>\s*<\/>\s*\) : null\}/,
  );
  // The drift is transform-only, paused unless the hero is visible, and
  // absent under reduced motion.
  const css = read("../components/landing.css");
  assert.match(
    css,
    /@media \(prefers-reduced-motion: no-preference\) \{\s*\.ln-hero::before \{\s*animation: ln-drift[^}]*animation-play-state: paused;/,
  );
  assert.match(css, /\.ln-hero\[data-drift\]::before \{\s*animation-play-state: running;/);
  assert.match(css, /@keyframes ln-drift \{\s*from \{\s*transform:[^}]*\}\s*to \{\s*transform:[^}]*\}\s*\}/);
  // Content is hidden only once the reveal script marks the page ready.
  assert.match(
    read("../components/landing.css"),
    /\.landing\[data-reveal-ready\] \[data-reveal\] \{\s*opacity: 0;/,
  );
});

test("the landing header keeps only the theme switch and Get Started", async () => {
  const { readFileSync } = await import("node:fs");
  const landing = readFileSync(new URL("../components/landing.tsx", import.meta.url), "utf8");
  const nav = landing.slice(landing.indexOf('<nav aria-label="Main">'), landing.indexOf("</nav>"));
  for (const href of ["#how", "#control", "#needs", "#privacy"])
    assert.ok(!nav.includes(`href="${href}"`), `no ${href} link in the header`);
  assert.ok(nav.includes("Get Started"));
});
