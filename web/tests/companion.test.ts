import assert from "node:assert/strict";
import test from "node:test";
import {
  COMPANION_COLORS,
  DONE_MS,
  EAT_MS,
  companionStep,
  initialCompanionPhase,
} from "../lib/companion.ts";

test("the companion rests blue, waits orange and celebrates green", () => {
  assert.equal(COMPANION_COLORS.rest, "#5763d2");
  assert.equal(COMPANION_COLORS.waiting, "#e8741f");
  assert.equal(COMPANION_COLORS.eating, COMPANION_COLORS.waiting);
  assert.equal(COMPANION_COLORS.done, "#34a46a");
});

test("it starts where the queue is, without a hop", () => {
  assert.equal(initialCompanionPhase(0), "rest");
  assert.equal(initialCompanionPhase(3), "waiting");
  assert.deepEqual(companionStep(3, 3), { kind: "none" });
});

test("each new request is a hop; a smaller but non-empty queue changes nothing", () => {
  assert.deepEqual(companionStep(0, 1), { kind: "hop" });
  assert.deepEqual(companionStep(1, 2), { kind: "hop" });
  assert.deepEqual(companionStep(2, 1), { kind: "none" });
});

test("clearing the queue eats the last count, then green, then rest", () => {
  assert.deepEqual(companionStep(2, 0), { kind: "eat", eaten: 2 });
  assert.deepEqual(companionStep(0, 0), { kind: "none" });
  assert.ok(EAT_MS > 0 && EAT_MS <= 1000, "the eat is short");
  assert.ok(DONE_MS >= 1500 && DONE_MS <= 3000, "green lasts about 2s");
  // A request arriving mid-eat is a hop: the component cancels the eat timers.
  assert.deepEqual(companionStep(0, 1), { kind: "hop" });
});
