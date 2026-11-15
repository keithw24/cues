import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { flaggedWithoutRequest } from "../lib/classroom-view.ts";
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

test("web.review_waiting is registered off by default and wired from both pages", () => {
  const flag = JSON.parse(read("../../flags.json"))["web.review_waiting"];
  assert.equal(flag.default, false);
  assert.equal(flag.owner, "evan");
  for (const page of ["../app/review/page.tsx", "../app/dashboard/page.tsx"])
    assert.match(read(page), /reviewWaitingEnabled=\{isEnabled\("web\.review_waiting"\)\}/);
});

test("with the flag off the To review page lists only Cues's requests, as before", () => {
  const dashboard = read("../components/dashboard.tsx");
  assert.match(dashboard, /reviewWaitingEnabled = false,/);
  // Off: nothing is computed, so the count, cards and All clear behave as before.
  assert.match(dashboard, /reviewWaitingEnabled && reviewsLive\s*\?\s*flaggedWithoutRequest\(/);
  assert.match(dashboard, /:\s*\[\];\s*const waitingCount = reviewsLive\s*\?\s*reviewGroups\.length \+ flaggedOnly\.length/);
  // Flagged people only get Mark as reviewed: nothing is written as a review for them.
  const card = read("../components/review-card.tsx");
  const waiting = card.slice(card.indexOf("export function WaitingReviewCard"));
  assert.doesNotMatch(waiting, /TeacherReviewActions|resolve_teacher_review/);
  assert.match(waiting, /No suggestion yet/);
});
