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

test("supporting expression context survives the person-state projection", () => {
  const expression = { label: 'sadness', probability: 0.62,
    duration_seconds: 5, supporting_only: true };
  const parsed = parseSnapshot({ ...input, states: [{ ...states[0],
    expression_context: expression }] }, true);
  assert.deepEqual(parsed.states[0].expression_context, expression);
  assert.throws(() => parseSnapshot({ ...input, states: [{ ...states[0],
    expression_context: { ...expression, probability: 2 } }] }, true));
});

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
test("dashboard defaults on, server override wins, invalid and unknown flags fail", () => {
  assert.equal(isEnabled("web.dashboard", {}), true);
  assert.equal(isEnabled("web.dashboard", { CUES_FLAG_WEB_DASHBOARD: "0" }), false);
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

test("teacher review transport defaults off independently of the seat dashboard", () => {
  assert.equal(isEnabled("web.teacher_reviews", {}), true);
  assert.equal(
    isEnabled("web.teacher_reviews", { CUES_FLAG_WEB_TEACHER_REVIEWS: "1" }),
    true,
  );
});

test("review actions stay disabled independently of review reads", () => {
  assert.equal(
    isEnabled("web.teacher_review_actions", {
      CUES_FLAG_WEB_TEACHER_REVIEWS: "1",
    }),
    false,
  );
  assert.equal(
    isEnabled("web.teacher_review_actions", {
      CUES_FLAG_WEB_TEACHER_REVIEW_ACTIONS: "1",
    }),
    true,
  );
});

test("person observations replace legacy seats per station without counting empty person metadata", () => {
  const input = {
    seats: [
      {
        id: "S1-L",
        station_id: "S1",
        side: "left",
        display_name: "Left seat",
        is_simulated: true,
      },
      ...[1, 2, 3, 4].map((n) => ({
        id: `S1-P${n}`,
        station_id: "S1",
        side: null,
        display_name: `Person ${n}`,
        is_simulated: true,
      })),
    ],
    states: [{ ...states[0], seat_id: "S1-P1" }],
    activities: [{ id: "raise_hand", name: "Raise hand" }],
    stations: [{ id: "S1", name: "Demo station" }],
  };
  assert.deepEqual(
    seatViews(parseSnapshot(input)).map((seat) => seat.id),
    ["S1-P1"],
  );
  assert.deepEqual(
    seatViews(parseSnapshot({ ...input, states: [] })).map((seat) => seat.id),
    ["S1-L"],
  );
});

test("teacher login defaults on and turns off independently of classroom access", () => {
  assert.equal(isEnabled("web.teacher_login", {}), true);
  assert.equal(
    isEnabled("web.teacher_login", { CUES_FLAG_WEB_TEACHER_LOGIN: "0" }),
    false,
  );
  assert.equal(
    isEnabled("web.teacher_login", { CUES_FLAG_WEB_TEACHER_LOGIN: "1" }),
    true,
  );
  assert.equal(
    isEnabled("web.dashboard", {
      CUES_FLAG_WEB_TEACHER_LOGIN: "1",
      CUES_FLAG_WEB_DASHBOARD: "0",
    }),
    false,
  );
});
