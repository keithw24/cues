import test from "node:test";
import assert from "node:assert/strict";
import {evaluatedProgress} from "../lib/progress-context.ts";
import type {SeatState} from "../lib/dashboard.ts";
const now = Date.parse("2026-11-14T23:00:00Z");
const observation: SeatState = {seat_id: "S2-P1", session_id: "session", activity_id: "raise_hand",
  session_revision: 2, status: "in_progress", tracking_valid: true, task_score: 0.4,
  updated_at: new Date(now).toISOString(), evaluated_progress: {
    session_id: "session", activity_id: "raise_hand", session_revision: 2,
    observed_at: new Date(now).toISOString(), trend: "stalled", stalled_seconds: 6,
    recent: [{observed_at: new Date(now).toISOString(), progress: {trend: "stalled", stalled_seconds: 6}}],
  }};
test("backend trend/stall/history can be displayed without browser inference", () => {
  const p = evaluatedProgress(observation, now);
  assert.equal(p?.trend, "stalled"); assert.equal(p?.stalled_seconds, 6);
  assert.equal(p?.recent.length, 1);
});
test("wrong session/task/revision, tracking loss and stale evaluations are hidden", () => {
  for (const patch of [{session_id: "other"}, {activity_id: "other"}, {session_revision: 3},
    {tracking_valid: false}]) assert.equal(evaluatedProgress({...observation, ...patch}, now), null);
  assert.equal(evaluatedProgress(observation, now + 6000), null);
  assert.equal(evaluatedProgress({...observation, evaluated_progress: {trend: "stalled"}}, now), null);
});
