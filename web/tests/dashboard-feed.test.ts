import assert from "node:assert/strict";
import test from "node:test";
import type { SupabaseClient } from "@supabase/supabase-js";
import { watchDashboard, type FeedState } from "../lib/dashboard-feed.ts";

function harness(enabled = false) {
  const projections: string[] = [];
  const rows: Record<string, Record<string, unknown>[]> = {
    seats: [
      {
        id: "S1-L",
        station_id: "S1",
        side: "left",
        display_name: "Left seat",
        is_simulated: true,
      },
    ],
    seat_state: [
      {
        seat_id: "S1-L",
        session_id: "00000000-0000-4000-8000-000000000001",
        activity_id: "raise_hand",
        status: "idle",
        task_score: null,
        updated_at: "2026-11-14T00:00:00Z",
      },
    ],
    activities: [{ id: "raise_hand", name: "Raise your hand" }],
    stations: [{ id: "S1", name: "Demo station" }],
  };
  let status: (value: string) => void = () => {};
  let change: () => void = () => {};
  let fail = false;
  let reads = 0;
  let removed = 0;
  const signals: AbortSignal[] = [];
  const channel = {
    on(_event: string, _filter: unknown, callback: () => void) {
      change = callback;
      return channel;
    },
    subscribe(callback: (value: string) => void) {
      status = callback;
      return channel;
    },
  };
  const client = {
    channel: () => channel,
    from(table: string) {
      return {
        select: (columns: string) => {
          projections.push(columns);
          return {
            abortSignal: async (signal: AbortSignal) => {
              reads++;
              signals.push(signal);
              return {
                data: structuredClone(rows[table]),
                error: fail ? { message: "private details" } : null,
              };
            },
          };
        },
      };
    },
    removeChannel: async () => {
      removed++;
    },
  } as unknown as SupabaseClient;
  const observed: FeedState[] = [];
  const feed = watchDashboard(client, (s) => observed.push(s), enabled);
  return {
    rows,
    projections,
    feed,
    observed,
    signals,
    status: (s: string) => status(s),
    change: () => change(),
    fail: (value: boolean) => {
      fail = value;
    },
    reads: () => reads,
    removed: () => removed,
  };
}
const settled = () => new Promise<void>((resolve) => setImmediate(resolve));

test("healthy refreshes keep an established subscription connected", async () => {
  const h = harness();
  h.status("SUBSCRIBED");
  await settled();
  const before = h.observed.length;
  await h.feed.refresh();
  assert.ok(
    h.observed.slice(before).every((state) => state.connection === "connected"),
  );
  assert.ok(h.observed.slice(before).some((state) => state.loading));
  h.feed.dispose();
});

test("replacing an offline feed recovers without any callback from the old socket", async () => {
  const old = harness();
  old.status("SUBSCRIBED");
  await settled();
  old.feed.disconnect();
  assert.equal(old.observed.at(-1)?.connection, "disconnected");
  old.feed.dispose();
  // The online handler remounts the feed instead of waiting on the old socket.
  const next = harness();
  next.status("SUBSCRIBED");
  await settled();
  assert.equal(next.observed.at(-1)?.connection, "connected");
  assert.equal(next.observed.at(-1)?.snapshot?.seats.length, 1);
  assert.equal(old.removed(), 1);
  next.feed.dispose();
});

test("reconnect refreshes missed changes; failures preserve the last good snapshot", async () => {
  const h = harness();
  await settled();
  assert.equal(h.observed.at(-1)?.snapshot?.states[0].status, "idle");
  h.status("CHANNEL_ERROR");
  assert.equal(h.observed.at(-1)?.connection, "disconnected");
  Object.assign(h.rows.seat_state[0], { status: "done" });
  h.status("SUBSCRIBED");
  await settled();
  assert.equal(h.observed.at(-1)?.snapshot?.states[0].status, "done");
  h.fail(true);
  await h.feed.refresh();
  assert.equal(h.observed.at(-1)?.snapshot?.states[0].status, "done");
  assert.ok(h.observed.at(-1)?.error);
  assert.ok(!h.observed.at(-1)?.error?.includes("private details"));
  h.feed.dispose();
});
test("realtime events reload state and disposal cancels reads and future callbacks", async () => {
  const h = harness();
  await settled();
  Object.assign(h.rows.seat_state[0], { status: "tracking_lost" });
  h.change();
  await new Promise((resolve) => setTimeout(resolve, 130));
  await settled();
  assert.equal(h.observed.at(-1)?.snapshot?.states[0].status, "tracking_lost");
  const observed = h.observed.length;
  const reads = h.reads();
  h.feed.dispose();
  assert.equal(h.removed(), 1);
  assert.ok(h.signals.every((signal) => signal.aborted));
  h.status("SUBSCRIBED");
  await h.feed.refresh();
  assert.equal(h.observed.length, observed);
  assert.equal(h.reads(), reads);
});

test("person flag gates tracking_valid reads and realtime replacement preserves false", async () => {
  const disabled = harness();
  await settled();
  assert.ok(
    disabled.projections.every(
      (columns) => !columns.includes("tracking_valid"),
    ),
  );
  disabled.feed.dispose();
  const enabled = harness(true);
  await settled();
  assert.ok(
    enabled.projections.some((columns) => columns.includes("tracking_valid")),
  );
  Object.assign(enabled.rows.seat_state[0], {
    tracking_valid: false,
    status: "in_progress",
    task_score: null,
  });
  enabled.change();
  await new Promise((resolve) => setTimeout(resolve, 130));
  await settled();
  assert.equal(
    enabled.observed.at(-1)?.snapshot?.states[0].tracking_valid,
    false,
  );
  enabled.feed.dispose();
});

test("each dashboard subscription joins its own realtime topic", () => {
  const topics: string[] = [];
  const channel = { on: () => channel, subscribe: () => channel };
  const client = {
    channel: (topic: string) => (topics.push(topic), channel),
    from: () => ({ select: () => ({ abortSignal: () => new Promise(() => {}) }) }),
    removeChannel: async () => {},
  } as unknown as SupabaseClient;
  const noop = () => {};
  watchDashboard(client, noop, false, "S1", false).dispose();
  watchDashboard(client, noop, false, "S1", false).dispose();
  assert.equal(topics.length, 2);
  assert.notEqual(topics[0], topics[1]);
});
