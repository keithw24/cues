import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import type { SupabaseClient } from "@supabase/supabase-js";
import { parseDefaultStation, resolveDefaultStation, StationSignInRequired } from "../lib/default-station.ts";
import { watchDashboard, type FeedState } from "../lib/dashboard-feed.ts";
import { watchTeacherReviews } from "../lib/teacher-review-feed.ts";

function rpcClient(response: { data?: unknown; error?: unknown }) {
  const calls: unknown[][] = [];
  const client = {
    rpc(name: string, ...args: unknown[]) {
      calls.push([name, ...args]);
      return { abortSignal: async () => ({ data: null, error: null, ...response }) };
    },
  } as unknown as SupabaseClient;
  return { client, calls };
}

test("the station comes from one RPC that sends no teacher or station", async () => {
  const { client, calls } = rpcClient({
    data: { station_id: "S2", name: "Station S2", created: true },
  });
  assert.deepEqual(await resolveDefaultStation(client), {
    id: "S2",
    name: "Station S2",
    created: true,
  });
  assert.deepEqual(calls, [["get_or_create_my_default_station"]]); // no arguments at all
});

test("an existing teacher gets back their existing station", async () => {
  const { client } = rpcClient({ data: { station_id: "S1", name: "Demo station", created: false } });
  assert.equal((await resolveDefaultStation(client)).id, "S1");
});

test("signed-out callers are reported as needing to sign in", async () => {
  const { client } = rpcClient({ error: { code: "42501", message: "Authentication required" } });
  await assert.rejects(resolveDefaultStation(client), StationSignInRequired);
});

test("provider details never reach the page", async () => {
  const { client } = rpcClient({ error: { code: "XX000", message: "secret detail" } });
  await assert.rejects(resolveDefaultStation(client), (error: Error) => {
    assert.match(error.message, /could not be loaded/);
    assert.doesNotMatch(error.message, /secret/);
    return true;
  });
});

test("malformed station answers are rejected", () => {
  for (const bad of [null, {}, { station_id: "", created: true }, { station_id: "S 1", created: false },
    { station_id: "S1" }, { station_id: 1, created: false }, { station_id: "S1", name: 5, created: false }])
    assert.throws(() => parseDefaultStation(bad), /Unexpected response from your classroom camera/);
});

// ---- the feeds are limited to the resolved station --------------------------------
function feedClient() {
  const filters: Record<string, [string, unknown][]> = {};
  const rows: Record<string, Record<string, unknown>[]> = {
    seats: [
      { id: "S1-P1", station_id: "S1", side: null, display_name: "Person 1", is_simulated: true },
      { id: "S2-P1", station_id: "S2", side: null, display_name: "Person 1", is_simulated: true },
    ],
    seat_state: [
      { seat_id: "S1-P1", session_id: "s1", activity_id: "raise_hand", status: "idle", task_score: null, updated_at: "2026-11-14T00:00:00Z" },
      { seat_id: "S2-P1", session_id: "s2", activity_id: "raise_hand", status: "done", task_score: 0.9, updated_at: "2026-11-14T00:00:00Z" },
    ],
    activities: [{ id: "raise_hand", name: "Raise your hand" }],
    stations: [{ id: "S1", name: "Demo" }, { id: "S2", name: "Station S2" }],
    sessions: [{ id: "mine", station_id: "S2", teacher_id: "t1" }],
  };
  const channel = { on: () => channel, subscribe: () => channel };
  const client = {
    channel: () => channel,
    removeChannel: async () => {},
    auth: {
      getSession: async () => ({ data: { session: { user: { id: "t1" } } } }),
      onAuthStateChange: () => ({ data: { subscription: { unsubscribe() {} } } }),
    },
    from(table: string) {
      filters[table] = [];
      let result = rows[table] ?? [];
      const query = {
        select: () => query,
        eq(key: string, value: unknown) {
          filters[table].push([key, value]);
          result = result.filter((row) => row[key] === value);
          return query;
        },
        abortSignal: async () => ({ data: structuredClone(result), error: null }),
        then: undefined,
      };
      return query;
    },
  } as unknown as SupabaseClient;
  return { client, filters };
}

async function settle(ms = 30) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

test("the dashboard feed reads only the resolved station's seats and observations", async () => {
  const { client, filters } = feedClient();
  const seen: FeedState[] = [];
  const feed = watchDashboard(client, (s) => seen.push(s), false, "S2");
  await settle();
  const snapshot = seen.findLast((s) => s.snapshot)?.snapshot;
  assert.deepEqual(snapshot?.seats.map((s) => s.id), ["S2-P1"]);
  assert.deepEqual(snapshot?.states.map((s) => s.seat_id), ["S2-P1"]);
  assert.deepEqual(snapshot?.stations.map((s) => s.id), ["S2"]);
  assert.deepEqual(filters.seats, [["station_id", "S2"]]);
  feed.dispose();
});

test("without a station the feed is unchanged (no filters)", async () => {
  const { client, filters } = feedClient();
  const seen: FeedState[] = [];
  const feed = watchDashboard(client, (s) => seen.push(s));
  await settle();
  assert.deepEqual(seen.findLast((s) => s.snapshot)?.snapshot?.seats.length, 2);
  assert.deepEqual(filters.seats, []);
  feed.dispose();
});

test("the review feed reads only this teacher's sessions at the resolved station", async () => {
  const { client, filters } = feedClient();
  const feed = watchTeacherReviews(client, () => {}, true, "S2");
  await settle();
  assert.deepEqual(filters.sessions, [["teacher_id", "t1"], ["station_id", "S2"]]);
  feed.dispose();
});

// ---- wiring contract (the runner does not mount React) ---------------------------------
test("the dashboard resolves the station and passes it to every part", () => {
  const dashboard = readFileSync(new URL("../components/dashboard.tsx", import.meta.url), "utf8");
  assert.ok(dashboard.includes("resolveDefaultStation(client)"));
  assert.ok(dashboard.includes("station={station}"));
  assert.match(dashboard, /personObservationsEnabled,\s*station,\s*liveProgressEnabled,\s*\)/);
  assert.match(dashboard, /reviewsEnabled,\s*station,\s*interventionsEnabled,\s*\)/);
  const page = readFileSync(new URL("../app/dashboard/page.tsx", import.meta.url), "utf8");
  assert.ok(page.includes("CUES_STATION_OVERRIDE"));
  assert.ok(!page.includes("CUES_STATION_ID"));
});

test("explicit unresolved station fails closed without reading any tables", async () => {
  const {client, filters} = feedClient();
  const seen: FeedState[] = [];
  const feed = watchDashboard(client, state => seen.push(state), true, "");
  await settle();
  assert.deepEqual(filters, {});
  assert.equal(seen.at(-1)?.snapshot, null);
  feed.dispose();
});
