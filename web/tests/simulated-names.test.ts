import assert from "node:assert/strict";
import test from "node:test";
import { displayName } from "../lib/simulated-names.ts";
import { isEnabled } from "../lib/flags.ts";

const person = { id: "S1-P3", display_name: "Person 3", is_simulated: true };

test("simulated names default off and keep the position label", () => {
  assert.equal(isEnabled("web.simulated_names", {}), true);
  assert.equal(displayName(person, false), "Person 3");
});

test("with the flag on, simulated people get a made-up name by position", () => {
  assert.equal(displayName(person, true), "Ava");
  assert.equal(displayName({ ...person, id: "S1-P11" }, true), "Ava");
});

test("seats that are not simulated, or not person positions, keep their label", () => {
  assert.equal(
    displayName({ ...person, is_simulated: false }, true),
    "Person 3",
  );
  assert.equal(
    displayName(
      { id: "S1-L", display_name: "Left seat", is_simulated: true },
      true,
    ),
    "Left seat",
  );
});
