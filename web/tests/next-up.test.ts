import assert from "node:assert/strict";
import test from "node:test";
import { nextUp } from "../lib/next-up.ts";

const leo = { name: "Leo", activity: "Thumbs up", count: 3, elevated: true };
const ava = { name: "Ava", activity: "Thumbs up", count: 1, elevated: false };

test("the first review group leads, and later names queue behind it", () => {
  const next = nextUp({
    reviews: [leo, ava],
    flagged: [{ name: "Noah", activity: "Raise your hand" }],
    inView: 4,
    cameraReporting: true,
  });
  assert.equal(next.kind, "review");
  assert.equal(next.kind === "review" && next.name, "Leo");
  assert.equal(
    next.kind === "review" && next.detail,
    "Thumbs up · 3 reviews waiting",
  );
  assert.deepEqual(next.kind === "review" && next.then, ["Ava", "Noah"]);
});

test("without reviews, a Needs Review status leads", () => {
  const next = nextUp({
    reviews: [],
    flagged: [{ name: "Noah", activity: "Raise your hand" }],
    inView: 2,
    cameraReporting: true,
  });
  assert.equal(next.kind, "status");
  assert.equal(
    next.kind === "status" && next.detail,
    "Raise your hand · may need a hand",
  );
});

test("calm states follow the camera: working, no one in view, camera off", () => {
  const calm = (inView: number, cameraReporting: boolean) => {
    const next = nextUp({ reviews: [], flagged: [], inView, cameraReporting });
    return next.kind === "calm" ? next.message : "";
  };
  assert.match(calm(3, true), /Everyone’s working/);
  assert.match(calm(0, true), /No one is in view/);
  assert.match(calm(0, false), /camera is off/);
});

test("room view defaults off; the card layout stays without it", async () => {
  const { isEnabled } = await import("../lib/flags.ts");
  const { readFileSync } = await import("node:fs");
  assert.equal(isEnabled("web.room_view", {}), true);
  assert.equal(
    isEnabled("web.room_view", { CUES_FLAG_WEB_ROOM_VIEW: "1" }),
    true,
  );
  const read = (path: string) =>
    readFileSync(new URL(path, import.meta.url), "utf8");
  assert.match(
    read("../app/dashboard/page.tsx"),
    /roomViewEnabled=\{isEnabled\("web\.room_view"\)\}/,
  );
  const dashboard = read("../components/dashboard.tsx");
  assert.match(dashboard, /roomViewEnabled = false,/);
  // Off: the original banner and card grid render as before.
  assert.match(
    dashboard,
    /\{roomViewEnabled \? \([\s\S]*<header className="room-header">[\s\S]*\) : \([\s\S]*<div className="ws-hero">/,
  );
  // The timeline reads backend timestamps only.
  assert.match(read("../components/lesson-timeline.tsx"), /backend timestamps/);
});
