import test from "node:test";
import assert from "node:assert/strict";
import {mayConnectLocalFeed} from "../lib/local-feed-policy.ts";
test("local remains available; hosted access is opt-in and exact-origin", () => {
  assert.equal(mayConnectLocalFeed("http://localhost:3000", false), true);
  assert.equal(mayConnectLocalFeed("https://cues.nyc", false), false);
  assert.equal(mayConnectLocalFeed("https://cues.nyc", true), true);
  for (const origin of ["http://cues.nyc", "https://evil.example", "https://cues.nyc.evil.example"])
    assert.equal(mayConnectLocalFeed(origin, true), false);
});
