import assert from "node:assert/strict";
import test from "node:test";
import type { SupabaseClient } from "@supabase/supabase-js";
import { flagLabel, parseStationFlags, readStationFlags } from "../lib/station-flags.ts";

function client(response: { data?: unknown; error?: unknown }) {
  const calls: unknown[][] = [];
  const value = {
    rpc(name: string, args: unknown) {
      calls.push([name, args]);
      return { abortSignal: async () => ({ data: null, error: null, ...response }) };
    },
  } as unknown as SupabaseClient;
  return { value, calls };
}

test("the timeline reads one station's last hour and sends no teacher", async () => {
  const { value, calls } = client({
    data: [
      { seat_id: "S1-P1", kind: "review", at: "2026-11-14T12:00:00Z" },
      { seat_id: "S1-P1", kind: "no_progress", at: "2026-11-14T12:10:00Z" },
    ],
  });
  const since = Date.parse("2026-11-14T11:30:00Z");
  const flags = await readStationFlags(value, "S1", since);
  assert.deepEqual(calls, [
    ["read_station_flags", { p_station_id: "S1", p_since: "2026-11-14T11:30:00.000Z" }],
  ]);
  assert.deepEqual(flags.map((f) => [f.seat_id, f.kind]), [
    ["S1-P1", "review"],
    ["S1-P1", "no_progress"],
  ]);
  assert.equal(new Set(flags.map((f) => f.id)).size, 2); // each mark has its own identity
});

test("every kind has plain words and a closed review is still a flag", () => {
  assert.equal(flagLabel("review", "Person 1"), "Person 1 flagged for review");
  assert.equal(flagLabel("review_needed", "Person 1"), "Person 1 flagged: needs review");
  assert.equal(flagLabel("no_progress", "Person 1"), "Person 1 flagged: no progress");
});

test("malformed answers are rejected", () => {
  for (const bad of [null, {}, [{}], [{ seat_id: "S1-P1", kind: "other", at: "2026-11-14T12:00:00Z" }],
    [{ seat_id: "bad seat", kind: "review", at: "2026-11-14T12:00:00Z" }],
    [{ seat_id: "S1-P1", kind: "review", at: "yesterday" }]])
    assert.throws(() => parseStationFlags(bad), /Invalid flags response/);
});

test("errors never show provider details and a bad station is refused first", async () => {
  const { value, calls } = client({ error: { code: "42501", message: "secret detail" } });
  await assert.rejects(readStationFlags(value, "S1", Date.now()), (e: Error) => {
    assert.equal(e.message, "The timeline could not be loaded.");
    return true;
  });
  await assert.rejects(readStationFlags(value, "S1; drop", Date.now()), /Invalid station/);
  assert.equal(calls.length, 1); // the bad station never reached the database
});

// The dashboard's "Last hour" timeline was removed in the workspace redesign
// (Evan's call, see DESIGN.md). readStationFlags stays, tested above, for a
// timeline or history view that reads it again.
