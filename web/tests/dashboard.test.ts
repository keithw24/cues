import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { parseSnapshot, seatViews, statuses } from "../lib/dashboard.ts";
import { isEnabled } from "../lib/flags.ts";

const states = JSON.parse(
  readFileSync(
    new URL("../../shared/fixtures/seat_states.json", import.meta.url),
    "utf8",
  ),
);
const seats = [
  {
    id: "S1-L",
    station_id: "S1",
    side: "left",
    display_name: "Left seat",
    is_simulated: true,
  },
  {
    id: "S1-R",
    station_id: "S1",
    side: "right",
    display_name: "Right seat",
    is_simulated: true,
  },
];
const input = {
  seats,
  states,
  activities: [{ id: "raise_hand", name: "Raise your hand" }],
  stations: [{ id: "S1", name: "Demo station" }],
};

test("canonical fixtures cover exactly the dashboard status vocabulary", () => {
  const parsed = parseSnapshot(input);
  assert.deepEqual(
    new Set(parsed.states.map((s) => s.status)),
    new Set(Object.keys(statuses)),
  );
});
test("missing observations remain unknown, never successful or failed", () => {
  const views = seatViews(
    parseSnapshot({ ...input, seats: seats.toReversed(), states: [] }),
  );
  assert.deepEqual(
    views.map((s) => s.id),
    ["S1-L", "S1-R"],
  );
  assert.equal(views[0].state, null);
  assert.equal(views[0].activity, "No activity assigned");
});
test("missing activity metadata stays explicit instead of inventing a task", () => {
  const state = { ...states[0], seat_id: "S1-L", activity_id: "unavailable" };
  const views = seatViews(parseSnapshot({ ...input, states: [state] }));
  assert.equal(views[0].activity, "Activity unavailable");
});
test("invalid scores and unknown statuses fail visibly", () => {
  for (const patch of [
    { task_score: 1.1 },
    { task_score: NaN },
    { status: "success" },
    { updated_at: "yesterday" },
  ]) {
    assert.throws(() =>
      parseSnapshot({ ...input, states: [{ ...states[0], ...patch }] }),
    );
  }
});
test("dashboard defaults off, server override wins, invalid and unknown flags fail", () => {
  assert.equal(isEnabled("web.dashboard", {}), false);
  assert.equal(
    isEnabled("web.dashboard", { NEXT_PUBLIC_CUES_FLAG_WEB_DASHBOARD: "true" }),
    true,
  );
  assert.equal(
    isEnabled("web.dashboard", {
      CUES_FLAG_WEB_DASHBOARD: "0",
      NEXT_PUBLIC_CUES_FLAG_WEB_DASHBOARD: "1",
    }),
    false,
  );
  assert.throws(() =>
    isEnabled("web.dashboard", { CUES_FLAG_WEB_DASHBOARD: "yes" }),
  );
  assert.throws(() => isEnabled("web.unknown", {}));
});
