import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import type { SupabaseClient } from "@supabase/supabase-js";
import {
  CAMERA_CONFLICT_MESSAGE,
  cameraConflict,
  parseStationWriter,
  readStationWriter,
} from "../lib/station-writer.ts";

const T = Date.parse("2026-11-14T12:00:00Z");
const iso = (offsetSeconds: number) => new Date(T + offsetSeconds * 1000).toISOString();

function table(response: { data?: unknown; error?: unknown }) {
  const calls: unknown[] = [];
  const query = {
    select(columns: string) { calls.push(["select", columns]); return query; },
    eq(key: string, value: string) { calls.push(["eq", key, value]); return query; },
    abortSignal() { return query; },
    maybeSingle: async () => ({ data: null, error: null, ...response }),
  };
  const client = {
    from(name: string) { calls.push(["from", name]); return query; },
  } as unknown as SupabaseClient;
  return { client, calls };
}

test("a refused camera shows the warning while the holder keeps running", () => {
  // The extra camera was refused 1 s before the holder's last renewal, and that was just now.
  const writer = { seen_at: iso(0), contested_at: iso(-1) };
  assert.equal(cameraConflict(writer, T + 2_000), true);
});

test("no refusal recorded means no warning", () => {
  assert.equal(cameraConflict({ seen_at: iso(0), contested_at: null }, T), false);
  assert.equal(cameraConflict(null, T), false);
});

test("the warning clears once the extra camera stops retrying", () => {
  // The holder has renewed for 30 s since the last refusal.
  assert.equal(cameraConflict({ seen_at: iso(30), contested_at: iso(0) }, T + 31_000), false);
});

test("the warning clears when the holder is gone (nothing is running)", () => {
  assert.equal(cameraConflict({ seen_at: iso(0), contested_at: iso(-1) }, T + 5 * 60_000), false);
});

test("only the station's own row is read, nothing else", async () => {
  const { client, calls } = table({ data: { seen_at: iso(0), contested_at: iso(-1) } });
  const writer = await readStationWriter(client, "S1");
  assert.deepEqual(writer, { seen_at: iso(0), contested_at: iso(-1) });
  assert.deepEqual(calls, [["from", "station_writers"], ["select", "seen_at,contested_at"], ["eq", "station_id", "S1"]]);
});

test("a station with no writer row yet is simply no conflict", async () => {
  assert.equal(await readStationWriter(table({ data: null }).client, "S1"), null);
});

test("malformed rows are rejected and errors never show provider details", async () => {
  for (const bad of [{ seen_at: "yesterday" }, { seen_at: iso(0), contested_at: 5 }, "x"])
    assert.throws(() => parseStationWriter(bad), /Invalid response/);
  await assert.rejects(
    readStationWriter(table({ error: { message: "secret detail" } }).client, "S1"),
    (e: Error) => e.message === "The camera status could not be loaded." && !/secret/.test(e.message),
  );
  await assert.rejects(readStationWriter(table({}).client, "S1; drop"), /Invalid station/);
});

test("the dashboard shows the warning under the session controls", () => {
  const dashboard = readFileSync(new URL("../components/dashboard.tsx", import.meta.url), "utf8");
  assert.ok(dashboard.includes("readStationWriter(client, station)"));
  assert.ok(dashboard.includes("{CAMERA_CONFLICT_MESSAGE}"));
  assert.match(CAMERA_CONFLICT_MESSAGE, /Only one camera can use a station/);
});
