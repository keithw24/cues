import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("camera pairing is gone; the old URL goes to the classroom", () => {
  const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");
  assert.match(read("../app/settings/stations/page.tsx"), /redirect\("\/dashboard"\)/);
  for (const file of [
    "../app/settings/profile/page.tsx",
    "../components/session-controls.tsx",
    "../components/workspace-sidebar.tsx",
  ])
    assert.doesNotMatch(read(file), /settings\/stations|[Pp]airing/, file);
});

test("teachers never see the word station", () => {
  const files = [
    "../components/session-controls.tsx",
    "../components/dashboard.tsx",
    "../components/local-classroom-feed.tsx",
    "../components/landing.tsx",
    "../components/landing-faq.tsx",
    "../app/settings/profile/page.tsx",
    "../lib/default-station.ts",
    "../lib/session-controls.ts",
    "../components/person-panel.tsx",
  ];
  for (const file of files) {
    // Comments may still say "station" (the backend entity); visible text may not.
    const source = readFileSync(new URL(file, import.meta.url), "utf8")
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/^\s*\/\/.*$/gm, "");
    assert.doesNotMatch(
      source,
      /Station access|the station|station laptop|station camera|Invalid station response|Connect station|Station idle|Waiting for station|this station|a station\b|Not authorized for this station/,
      file,
    );
  }
});
