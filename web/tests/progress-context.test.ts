import assert from "node:assert/strict";
import test from "node:test";
import { matchingTaskObservation } from "../lib/progress-context.ts";
import type { SeatState } from "../lib/dashboard.ts";
const observation: SeatState = {
  session_id: "session-one",
  seat_id: "S1-L",
  activity_id: "raise_hand",
  status: "review",
  task_score: 0.55,
  updated_at: "2026-11-14T12:00:00Z",
};
test("current task context requires the exact session, seat and activity", () => {
  assert.equal(matchingTaskObservation(observation, observation), observation);
  for (const patch of [
    { session_id: "session-two" },
    { seat_id: "S1-R" },
    { activity_id: "thumbs_up" },
  ]) {
    assert.equal(
      matchingTaskObservation(observation, { ...observation, ...patch }),
      null,
    );
  }
  assert.equal(matchingTaskObservation(null, observation), null);
});
test("task observations remain observations, never invented evaluated progress or stall duration", () => {
  const result = matchingTaskObservation(observation, observation)!;
  assert.equal(result.status, "review");
  assert.equal("trend" in result, false);
  assert.equal("stalled_seconds" in result, false);
  assert.equal("history" in result, false);
});
