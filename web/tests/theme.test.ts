import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { isEnabled } from "../lib/flags.ts";
import { THEME_KEY, themeScript } from "../lib/theme.ts";

const read = (path: string) =>
  readFileSync(new URL(path, import.meta.url), "utf8");

test("theme toggle defaults off; without it no script runs and no toggle shows", () => {
  assert.equal(isEnabled("web.theme_toggle", {}), false);
  assert.equal(
    isEnabled("web.theme_toggle", { CUES_FLAG_WEB_THEME_TOGGLE: "1" }),
    true,
  );
  assert.match(
    read("../app/layout.tsx"),
    /isEnabled\("web\.theme_toggle"\) \? \(\s*<head>/,
  );
  assert.match(read("../components/landing.tsx"), /\{themeToggle \? \(/);
  assert.match(
    read("../components/workspace-sidebar.tsx"),
    /\{themeToggle \? \(/,
  );
  assert.match(
    read("../components/teacher-login.tsx"),
    /\{themeToggleEnabled \? \(/,
  );
});

test("the saved theme applies only for known values", () => {
  const root = { attrs: {} as Record<string, string> };
  const run = (stored: string | null) => {
    root.attrs = {};
    const localStorage = {
      getItem: (key: string) => (key === THEME_KEY ? stored : null),
    };
    const document = {
      documentElement: {
        setAttribute: (name: string, value: string) =>
          (root.attrs[name] = value),
      },
    };
    new Function("localStorage", "document", themeScript)(
      localStorage,
      document,
    );
    return root.attrs["data-theme"];
  };
  assert.equal(run("light"), "light");
  assert.equal(run("dark"), "dark");
  assert.equal(run("purple"), undefined);
  assert.equal(run(null), undefined);
});

test("the live mock defaults off and never touches Supabase", () => {
  assert.equal(isEnabled("web.live_view", {}), false);
  assert.match(
    read("../app/live/page.tsx"),
    /if \(!isEnabled\("web\.live_view"\)\)/,
  );
  const mock = read("../components/live-mock.tsx");
  assert.match(mock, /\bsimulated\n/);
  assert.match(read("../components/live-screen.tsx"), /Simulated class/);
  for (const file of ["live-mock.tsx", "live-screen.tsx"])
    assert.doesNotMatch(
      read(`../components/${file}`),
      /@\/lib\/(supabase|dashboard-feed|teacher-review-feed|teacher-review-actions)/,
    );
});

test("live data defaults off, so /live keeps the simulated mock", () => {
  assert.equal(isEnabled("web.live_data", {}), false);
  assert.equal(
    isEnabled("web.live_data", { CUES_FLAG_WEB_LIVE_DATA: "1" }),
    true,
  );
  const page = read("../app/live/page.tsx");
  assert.match(page, /const liveData = isEnabled\("web\.live_data"\)/);
  assert.match(
    page,
    /liveData\s*\?\s*await import\("@\/components\/live-connected"\)/,
  );
  assert.match(page, /:\s*await import\("@\/components\/live-mock"\)/);
  // Decisions follow the dashboard and PRD §13: Support needed saves the
  // model review as confirmed and No support needed as dismissed, only when
  // the review action flag is on, keyed by the review and its seat.
  const connected = read("../components/live-connected.tsx");
  assert.match(connected, /if \(reviewActionsEnabled && client\)/);
  assert.match(connected, /resolveTeacherReview\(client, lead, decision\)/);
  assert.match(
    connected,
    /decide\("confirmed"\)[\s\S]*resolutionLabels\.confirmed/,
  );
  assert.match(
    connected,
    /decide\("dismissed"\)[\s\S]*resolutionLabels\.dismissed/,
  );
  assert.match(connected, /reviewId: lead\.id,\s*seatId: lead\.seat_id/);
  assert.doesNotMatch(connected, /item\.name ===/);
});

test("review decisions read as support needed or not, on the same statuses", async () => {
  const { resolutionLabels, reviewPrompt } =
    await import("../lib/teacher-reviews.ts");
  // The labels change; the stored values do not, and no new status exists.
  assert.deepEqual(resolutionLabels, {
    confirmed: "Support needed",
    dismissed: "No support needed",
  });
  assert.equal(reviewPrompt.title, "Student may need support");
  assert.doesNotMatch(
    `${reviewPrompt.title} ${reviewPrompt.detail}`,
    /diagnos|emotion|distress|attention span|struggl/i,
  );
  const actions = read("../components/teacher-review-actions.tsx");
  assert.match(
    actions,
    /resolve\("confirmed"\)[\s\S]*resolutionLabels\.confirmed/,
  );
  assert.match(
    actions,
    /resolve\("dismissed"\)[\s\S]*resolutionLabels\.dismissed/,
  );
  assert.doesNotMatch(actions, /"Needs attention"|"Dismiss"/);
});

test("the rail links to /live only when the live view is on", () => {
  const rail = read("../components/workspace-sidebar.tsx");
  assert.match(rail, /\{liveView \? \(\s*<Link href="\/live"/);
  // The current entry follows the URL, not a fixed page.
  assert.match(rail, /usePathname\(\)/);
  for (const page of [
    "../app/dashboard/page.tsx",
    "../app/settings/profile/page.tsx",
    "../app/settings/notifications/page.tsx",
  ])
    assert.match(read(page), /isEnabled\("web\.live_view"\)/);
});
