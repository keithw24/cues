import assert from "node:assert/strict";
import test from "node:test";
import {
  CHECK_IN_LABEL,
  reviewIssueLine,
  stripEntries,
  type StripSource,
} from "../lib/classroom-view.ts";

const person = (id: string, label = "Working", tone: StripSource["tone"] = "working"): StripSource => ({
  id,
  name: `Person ${id}`,
  label,
  tone,
  activity: "Raise hand",
});

test("the student row keeps the camera's left-to-right order", () => {
  const row = stripEntries([person("3"), person("1"), person("2")], new Set(), null, false);
  assert.deepEqual(row.map((entry) => entry.id), ["3", "1", "2"]);
});

test("someone Cues asked about reads Check in, never a claim about the child", () => {
  const [asked, other] = stripEntries(
    [person("1", "Completed", "done"), person("2")],
    new Set(["1"]),
    null,
    false,
  );
  assert.equal(asked.status, CHECK_IN_LABEL);
  assert.equal(asked.tone, "review");
  assert.equal(other.status, "Working");
  assert.equal(other.tone, "working");
  assert.doesNotMatch(CHECK_IN_LABEL, /attention|distress|struggl|emotion/i);
});

test("the opened card is marked selected; activities show only when mixed", () => {
  const same = stripEntries([person("1"), person("2")], new Set(), "2", false);
  assert.deepEqual(same.map((entry) => entry.selected), [false, true]);
  assert.deepEqual(same.map((entry) => entry.activity), ["", ""]);
  const mixed = stripEntries([person("1")], new Set(), null, true);
  assert.equal(mixed[0].activity, "Raise hand");
});

test("a To review card says the task, then not in view, then the request count", () => {
  assert.equal(reviewIssueLine("Raise hand", true, 1), "Raise hand");
  assert.equal(reviewIssueLine("Raise hand", false, 1), "Raise hand · not in view");
  assert.equal(reviewIssueLine("Raise hand", true, 2), "Raise hand · 2 requests");
  assert.equal(
    reviewIssueLine("Thumbs up", false, 3),
    "Thumbs up · not in view · 3 requests",
  );
});

test("Attention names camera-flagged people instead of All clear, or under the requests", async () => {
  const { attentionFlaggedLine, nameList } = await import("../lib/classroom-view.ts");
  assert.equal(attentionFlaggedLine([], false), null);
  assert.equal(
    attentionFlaggedLine(["Keith"], false),
    "No requests from Cues. The camera flagged Keith for a look.",
  );
  assert.equal(attentionFlaggedLine(["Keith"], true), "Also flagged by the camera: Keith.");
  assert.doesNotMatch(attentionFlaggedLine(["Keith"], false) ?? "", /All clear/);
  assert.equal(nameList(["Keith", "Evan"]), "Keith and Evan");
  assert.equal(nameList(["Keith", "Evan", "Eric"]), "Keith, Evan and Eric");
  assert.equal(nameList(["Keith", "Evan", "Eric", "Michelle"]), "Keith, Evan and 2 more");
});

test("the classroom wires the flagged line from the same list as To review", async () => {
  const { readFileSync } = await import("node:fs");
  const dash = readFileSync(new URL("../components/dashboard.tsx", import.meta.url), "utf8");
  // Built from reviewQueue's flagged list (marked people already left out).
  assert.match(dash, /attentionFlaggedLine\(\s*flaggedOnly\.map\(\(seat\) => seat\.display_name\),/);
  // All clear only when nobody is flagged and nobody marked is still catching up.
  assert.match(dash, /flaggedLine \?\?\s*\(catchingUp\s*\?\s*"Marked as reviewed\. The camera will catch up in a moment\."\s*:\s*"All clear\. Cues will ask when someone may need you\."\)/);
});
