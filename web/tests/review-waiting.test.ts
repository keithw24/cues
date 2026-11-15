import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { flaggedWithoutRequest, reviewQueue } from "../lib/classroom-view.ts";
import { observationPresentation } from "../lib/observation-presentation.ts";
import type { SeatState } from "../lib/dashboard.ts";

const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");
const NOW = Date.parse("2026-11-15T04:41:00Z");
const options = { enabled: true, now: NOW, connected: true };
const state = (status: SeatState["status"], seconds = 1): SeatState =>
  ({
    seat_id: "S1-P1",
    session_id: "ba133be2-fb9a-42ee-aed6-915eede898e2",
    activity_id: "raise_hand",
    status,
    task_score: 0,
    expression_context: null,
    tracking_valid: true,
    session_revision: 1,
    updated_at: new Date(NOW - seconds * 1000).toISOString(),
  }) as SeatState;
const person = (id: string, status: SeatState["status"], seconds = 1) => ({
  id,
  state: state(status, seconds),
});
// The same test the person row uses for "Needs Review".
const flagged = (p: { state: SeatState }) =>
  observationPresentation(p.state, options).needsReview;

test("a person flagged review or needs_help with no request is listed on To review", () => {
  const people = [
    person("S1-P1", "review"),
    person("S1-P2", "needs_help"),
    person("S1-P3", "in_progress"),
    person("S1-P4", "done"),
  ];
  const listed = flaggedWithoutRequest(people, flagged, new Set(), new Set());
  assert.deepEqual(listed.map((p) => p.id), ["S1-P1", "S1-P2"]);
  // Exactly the people whose row reads Needs Review.
  for (const p of people)
    assert.equal(listed.includes(p), observationPresentation(p.state, options).label === "Needs Review");
});

test("someone with a pending request, or just marked reviewed, is not listed twice", () => {
  const people = [person("S1-P1", "review"), person("S1-P2", "needs_help"), person("S1-P3", "review")];
  const listed = flaggedWithoutRequest(people, flagged, new Set(["S1-P1"]), new Set(["S1-P2"]));
  assert.deepEqual(listed.map((p) => p.id), ["S1-P3"]);
});

test("a stale observation no longer reads Needs Review, so it is not listed", () => {
  const listed = flaggedWithoutRequest([person("S1-P1", "review", 30)], flagged, new Set(), new Set());
  assert.deepEqual(listed, []);
});

test("web.review_waiting is registered on by default and wired from both pages", () => {
  const flag = JSON.parse(read("../../flags.json"))["web.review_waiting"];
  // On at Evan's request (he owns it): a flagged person shows on To review and
  // in Attention at once, not only after the agent's request arrives.
  assert.equal(flag.default, true);
  assert.equal(flag.owner, "evan");
  for (const page of ["../app/review/page.tsx", "../app/dashboard/page.tsx"])
    assert.match(read(page), /reviewWaitingEnabled=\{isEnabled\("web\.review_waiting"\)\}/);
});

test("with the flag off the To review queue is exactly as before", () => {
  const people = [person("S1-P1", "review"), person("S1-P2", "needs_help"), person("S1-P3", "in_progress")];
  const base = { people, flagged, askedSeatIds: ["S1-P1"], marked: new Set<string>() };
  assert.deepEqual(reviewQueue({ ...base, enabled: false, live: true }), { flagged: [], count: 1 });
  assert.deepEqual(reviewQueue({ ...base, enabled: false, live: false }), { flagged: [], count: 0 });
  // On: the flagged person without a request joins the list and the count.
  const on = reviewQueue({ ...base, enabled: true, live: true });
  assert.deepEqual(on.flagged.map((p) => p.id), ["S1-P2"]);
  assert.equal(on.count, 2);
  // Never before the review feed is live, so no one shows twice while it loads.
  assert.deepEqual(reviewQueue({ ...base, enabled: true, live: false }), { flagged: [], count: 0 });
});

test("the rail and the header show the same count, and reset clears waiting cards", () => {
  const dashboard = read("../components/dashboard.tsx");
  assert.match(dashboard, /reviewCount=\{waitingCount\}/);
  assert.match(dashboard, /\[\.\.\.ids, \.\.\.flaggedOnly\.map\(\(seat\) => seat\.id\)\]\.forEach\(/);
  // Flagged people only get Mark as reviewed: nothing is written as a review for them.
  const card = read("../components/review-card.tsx");
  const waiting = card.slice(card.indexOf("export function WaitingReviewCard"));
  assert.doesNotMatch(waiting, /TeacherReviewActions|resolve_teacher_review/);
  assert.match(waiting, /No suggestion yet/);
});
