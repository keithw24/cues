import assert from "node:assert/strict";
import test from "node:test";
import { seatViews, type SeatState, type Snapshot } from "../lib/dashboard.ts";
import {
  liveCounts,
  livePeople,
  waitingCount,
  type LiveDecision,
} from "../lib/live-class.ts";
import {
  MOCK_FEED,
  MOCK_LABELS,
  MOCK_STUDENTS,
  mockSummary,
} from "../lib/live-mock-data.ts";

// Observation freshness off, as when web.person_observations is off.
const OPTIONS = { enabled: false, now: null, connected: true };

const state = (seat_id: string, status: SeatState["status"]): SeatState => ({
  seat_id,
  session_id: "sess-1",
  activity_id: "raise_hand",
  status,
  task_score: null,
  updated_at: "2026-11-14T15:00:00Z",
});

function snapshot(states: SeatState[]): Snapshot {
  return {
    seats: ["S1-P1", "S1-P2", "S1-P3", "S1-P4"].map((id, i) => ({
      id,
      station_id: "S1",
      side: null,
      display_name: `Person ${i + 1}`,
      is_simulated: true,
    })),
    states,
    activities: [{ id: "raise_hand", name: "Raise your hand" }],
    stations: [{ id: "S1", name: "Station 1" }],
  };
}

test("the simulated class shows 2 of 4 finished, the review, feed and list", () => {
  assert.deepEqual(mockSummary(MOCK_STUDENTS), {
    finished: 2,
    total: 4,
    needs: 1,
    working: 1,
  });
  assert.deepEqual(
    MOCK_STUDENTS.map((s) => [s.name, MOCK_LABELS[s.status]]),
    [
      ["Maya", "Finished"],
      ["Leo", "Needs you"],
      ["Ava", "Finished"],
      ["Noah", "Working"],
    ],
  );
  assert.equal(MOCK_FEED.length, 5);
  assert.equal(MOCK_FEED[0].text, "Leo flagged · 3 tries");
  // After the teacher confirms, the row reads as the decision, not a diagnosis.
  assert.equal(MOCK_LABELS.checking, "Support needed");
});

test("live data: Supabase rows become the people in view and their statuses", () => {
  const seats = seatViews(
    snapshot([
      state("S1-P1", "in_progress"),
      state("S1-P2", "done"),
      state("S1-P3", "needs_help"),
      state("S1-P4", "tracking_lost"),
    ]),
  );
  const people = livePeople(seats, OPTIONS, new Set(), []);
  // Tracking lost means out of view: only the people the camera sees.
  assert.deepEqual(
    people.map((p) => [p.id, p.status, p.label]),
    [
      ["S1-P1", "working", "Working"],
      ["S1-P2", "finished", "Finished"],
      ["S1-P3", "needs", "Needs you"],
    ],
  );
  assert.match(
    people[0].details[1],
    /Raise your hand · position 1 from the left/,
  );
  assert.deepEqual(liveCounts(people), { finished: 1, working: 1, total: 3 });
  // A seat with a pending model review shows as waiting on the teacher.
  const withReview = livePeople(seats, OPTIONS, new Set(["S1-P1"]), []);
  assert.deepEqual(withReview[0].label, "Review waiting");
});

test("a 'Support needed' marker yields to the camera's next status", () => {
  const confirmed: LiveDecision = {
    reviewId: "r1",
    seatId: "S1-P3",
    decision: "confirmed",
    saved: true,
    at: 1,
    statusAtDecision: "needs_help",
  };
  const before = livePeople(
    seatViews(snapshot([state("S1-P3", "needs_help")])),
    OPTIONS,
    new Set(),
    [confirmed],
  );
  assert.deepEqual(
    [before[0].status, before[0].label],
    ["checking", "Support needed"],
  );
  // The camera then reports the student finished: they count as finished.
  const after = livePeople(
    seatViews(snapshot([state("S1-P3", "done")])),
    OPTIONS,
    new Set(),
    [confirmed],
  );
  assert.deepEqual([after[0].status, after[0].label], ["finished", "Finished"]);
  assert.equal(liveCounts(after).finished, 1);
  // A dismissed review leaves the live status alone.
  const dismissed = livePeople(
    seatViews(snapshot([state("S1-P3", "in_progress")])),
    OPTIONS,
    new Set(),
    [{ ...confirmed, decision: "dismissed", statusAtDecision: "in_progress" }],
  );
  assert.equal(dismissed[0].status, "working");
});

test("waiting is counted by seat id, so same-named seats both count", () => {
  assert.equal(waitingCount(["S1-P1"], ["S1-P9"]), 2);
  assert.equal(waitingCount(["S1-P1"], ["S1-P1"]), 1);
});
