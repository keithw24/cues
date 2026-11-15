import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");

test("the needs section is registered, wired to its flag, and shows three needs", () => {
  const flags = JSON.parse(read("../../flags.json"));
  assert.ok("web.landing_needs" in flags);
  assert.match(read("../components/landing.tsx"), /isEnabled\("web\.landing_needs"\)/);
  const section = read("../components/landing-needs.tsx");
  assert.equal((section.match(/title: "/g) ?? []).length, 3);
});

test("the new copy makes no claim the product rules forbid", () => {
  // Only the visible strings of the new section, not its comments.
  const copy = (read("../components/landing-needs.tsx").match(/(?:title|text): "[^"]*"/g) ?? []).join(" ");
  // No emotion, diagnosis or attention claims, no reports or behaviour data, no endorsements.
  assert.doesNotMatch(copy, /\b(detects?|reads?|senses?) (emotions?|feelings?|distress)|diagnos/i);
  assert.doesNotMatch(copy, /parent report|therapist|ABC data|Bridge AI|Victor/i);
});
