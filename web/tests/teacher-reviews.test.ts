import assert from "node:assert/strict";
import test from "node:test";
import type { SupabaseClient } from "@supabase/supabase-js";
import {
  parseTeacherReviews,
  pendingReviews,
  REVIEW_COLUMNS,
  decisionLabels,
  teacherRationale,
  activityLabel,
} from "../lib/teacher-reviews.ts";
import {
  watchTeacherReviews,
  type ReviewFeedState,
} from "../lib/teacher-review-feed.ts";

const row = {
  id: "11111111-1111-4111-8111-111111111111",
  session_id: "00000000-0000-4000-8000-000000000001",
  seat_id: "S1-L",
  activity_id: "raise_hand",
  created_at: "2026-11-14T12:00:00Z",
  priority: "normal",
  rationale: "Progress has stalled across recent observations.",
  evidence_used: ["current_progress", "recent_progress_history"],
  status: "pending",
  resolved_at: null,
};
const settled = () => new Promise<void>((resolve) => setImmediate(resolve));
test("review details expose only stored evaluated progress and escalation", () => {
  const parsed = parseTeacherReviews([{ ...row, evaluation: {
    progress: { trend: 'stalled', stalled_seconds: 12 },
    escalation: { reason: 'stalled_progress' },
  }}])[0];
  assert.deepEqual(parsed.progress, { trend: 'stalled', stalled_seconds: 12 });
  assert.equal(parsed.escalation_reason, 'stalled_progress');
  const missing = parseTeacherReviews([row])[0];
  assert.equal(missing.progress, undefined);
  const invalid = parseTeacherReviews([{ ...row, evaluation: {
    progress: { trend: 'stalled', stalled_seconds: -1 },
  }}])[0];
  assert.equal(invalid.progress, null);
});
const debounce = () => new Promise<void>((resolve) => setTimeout(resolve, 130));

type Change = { eventType: string; new?: unknown; old?: unknown };

function harness(
  enabled = true,
  initialFailure = false,
  initialRows: unknown = [row],
) {
  let rows: unknown = initialRows;
  let nextReadGate: Promise<void> | undefined;
  let fail = initialFailure;
  let reads = 0;
  let channels = 0;
  let removed = 0;
  let change: (payload: Change) => void = () => {};
  let status: (value: string) => void = () => {};
  let filter: unknown;
  const signals: AbortSignal[] = [];
  const channel = {
    on(_event: string, config: unknown, callback: (payload: Change) => void) {
      filter = config;
      change = callback;
      return channel;
    },
    subscribe(callback: (status: string) => void) {
      status = callback;
      return channel;
    },
  };
  const client = {
    channel() {
      channels++;
      return channel;
    },
    from(table: string) {
      assert.equal(table, "teacher_reviews");
      return {
        select(columns: string) {
          assert.equal(columns, REVIEW_COLUMNS);
          return {
            eq(column: string, value: string) {
              assert.equal(column, "status");
              assert.equal(value, "pending");
              return {
                abortSignal: async (signal: AbortSignal) => {
                  reads++;
                  signals.push(signal);
                  const data = structuredClone(rows);
                  const gate = nextReadGate;
                  nextReadGate = undefined;
                  await gate;
                  return {
                    data,
                    error: fail
                      ? { message: "private database internals" }
                      : null,
                  };
                },
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
  const observed: ReviewFeedState[] = [];
  const feed = watchTeacherReviews(
    client,
    (state) => observed.push(state),
    enabled,
  );
  return {
    feed,
    observed,
    rows: (value: unknown) => {
      rows = value;
    },
    fail: () => {
      fail = true;
    },
    change: (payload: Change = { eventType: "UPDATE" }) => change(payload),
    holdNextRead() {
      let release!: () => void;
      nextReadGate = new Promise<void>((resolve) => {
        release = resolve;
      });
      return () => release();
    },
    status: (value: string) => status(value),
    reads: () => reads,
    channels: () => channels,
    removed: () => removed,
    filter: () => filter,
    signals,
  };
}

test("read projection preserves trusted fields and orders only pending reviews", () => {
  const elevated = {
    ...row,
    id: "22222222-2222-4222-8222-222222222222",
    priority: "elevated",
    created_at: "2026-11-14T13:00:00Z",
  };
  const rows = parseTeacherReviews([
    row,
    elevated,
    {
      ...row,
      id: "33333333-3333-4333-8333-333333333333",
      status: "confirmed",
      resolved_at: "2026-11-14T14:00:00Z",
    },
  ]);
  assert.deepEqual(
    pendingReviews(rows).map((review) => review.id),
    [elevated.id, row.id],
  );
  assert.equal(rows[0].rationale, row.rationale);
  assert.deepEqual(rows[0].evidence_used, row.evidence_used);
  assert.deepEqual(
    parseTeacherReviews([{ ...row, evidence_used: null }])[0].evidence_used,
    [],
  );
});
test("malformed or incompatible review data fails instead of fabricating evidence", () => {
  for (const patch of [
    { priority: "urgent" },
    { evidence_used: ["expression_context"] },
    { status: "approved" },
    { created_at: "yesterday" },
    { rationale: " " },
    { session_id: "not-a-session" },
  ]) {
    assert.throws(() => parseTeacherReviews([{ ...row, ...patch }]));
  }
  assert.throws(() => parseTeacherReviews([row, row]));
});
test("flag off creates no review requests or subscriptions", async () => {
  const h = harness(false);
  await h.feed.refresh();
  h.feed.dispose();
  assert.equal(h.reads(), 0);
  assert.equal(h.channels(), 0);
  assert.equal(h.removed(), 0);
  assert.equal(h.observed.at(-1)?.connection, "disabled");
});
test("initial read and reconnect load real pending rows, independent of seats", async () => {
  const h = harness();
  await settled();
  assert.equal(h.observed.at(-1)?.reviews?.[0].seat_id, "S1-L");
  h.status("SUBSCRIBED");
  await settled();
  assert.equal(h.observed.at(-1)?.connection, "connected");
  h.status("CHANNEL_ERROR");
  h.rows([]);
  h.status("SUBSCRIBED");
  await settled();
  assert.deepEqual(h.observed.at(-1)?.reviews, []);
  h.feed.dispose();
});
test("all row events reload pending query including confirmed/dismissed exits and deletion", async () => {
  const h = harness();
  await settled();
  assert.deepEqual(h.filter(), {
    event: "*",
    schema: "public",
    table: "teacher_reviews",
  });
  for (const status of ["confirmed", "dismissed"]) {
    h.rows([{ ...row, status }]);
    h.change();
    await debounce();
    assert.deepEqual(h.observed.at(-1)?.reviews, []);
    h.rows([row]);
    h.change();
    await debounce();
    assert.equal(h.observed.at(-1)?.reviews?.length, 1);
  }
  h.rows([]);
  h.change();
  await debounce();
  assert.deepEqual(h.observed.at(-1)?.reviews, []);
  h.feed.dispose();
});
test("missing table/read failures preserve stale reviews with sanitized error; disposal cancels work", async () => {
  const h = harness();
  await settled();
  h.fail();
  await h.feed.refresh();
  assert.equal(h.observed.at(-1)?.reviews?.length, 1);
  assert.ok(h.observed.at(-1)?.error);
  assert.ok(!h.observed.at(-1)?.error?.includes("private"));
  const before = h.observed.length,
    reads = h.reads();
  h.feed.dispose();
  h.status("SUBSCRIBED");
  h.change();
  await h.feed.refresh();
  await debounce();
  assert.equal(h.observed.length, before);
  assert.equal(h.reads(), reads);
  assert.equal(h.removed(), 1);
  assert.ok(h.signals.every((signal) => signal.aborted));
});

test("missing persistence on first read is unavailable, never an empty healthy queue", async () => {
  const h = harness(true, true);
  await settled();
  assert.equal(h.observed.at(-1)?.reviews, null);
  assert.ok(h.observed.at(-1)?.error);
  assert.equal(h.observed.at(-1)?.loading, false);
  h.feed.dispose();
});

test("assessment projection uses only explicit backend decisions and excludes internal traces", () => {
  for (const decision of [
    "continue_monitoring",
    "teacher_review_warranted",
  ] as const) {
    const parsed = parseTeacherReviews([
      {
        ...row,
        decision,
        prompt: "private prompt",
        chain_of_thought: "private trace",
        assessment: { trace: "private" },
      },
    ])[0];
    assert.equal(parsed.decision, decision);
    assert.equal("prompt" in parsed, false);
    assert.equal("chain_of_thought" in parsed, false);
    assert.equal("assessment" in parsed, false);
  }
  assert.equal(parseTeacherReviews([row])[0].decision, null);
  assert.equal(
    parseTeacherReviews([{ ...row, decision: "unknown_engine_code" }])[0]
      .decision,
    null,
  );
  assert.ok(REVIEW_COLUMNS.includes(",decision,"));
});
test("teacher-facing labels preserve decisions without exposing engineering codes", () => {
  assert.equal(
    decisionLabels.teacher_review_warranted,
    "Teacher check-in recommended",
  );
  assert.equal(decisionLabels.continue_monitoring, "Continue monitoring");
  assert.equal(
    teacherRationale("stalled_progress_with_expression_context"),
    "Repeated stalled progress",
  );
  assert.equal(
    teacherRationale("Reason: stalled_progress."),
    "Reason: Repeated stalled progress.",
  );
  assert.equal(
    teacherRationale("unknown_engine_code"),
    "additional review context",
  );
  assert.equal(teacherRationale(row.rationale), row.rationale);
  assert.equal(activityLabel("thumbs_up"), "Thumbs up");
  assert.equal(activityLabel("unknown_activity"), "Activity unavailable");
  assert.equal(
    activityLabel("custom", "Practice greeting"),
    "Practice greeting",
  );
});

test("pending insert and duplicate events update the queue immediately without duplicate items", async () => {
  const h = harness(true, false, []);
  await settled();
  assert.deepEqual(h.observed.at(-1)?.reviews, []);
  const reads = h.reads();
  h.rows([row]);
  h.change({ eventType: "INSERT", new: row });
  assert.equal(h.reads(), reads); // no SELECT needed to show the insert
  assert.equal(h.observed.at(-1)?.reviews?.length, 1);
  h.change({ eventType: "INSERT", new: row });
  h.change({ eventType: "INSERT", new: row });
  assert.equal(h.observed.at(-1)?.reviews?.length, 1);
  await debounce();
  assert.equal(h.reads(), reads + 1);
  assert.equal(h.observed.at(-1)?.reviews?.length, 1);
  h.feed.dispose();
});

test("pending updates replace detail data and resolutions immediately clear the selected queue identity", async () => {
  for (const status of ["confirmed", "dismissed"]) {
    const h = harness();
    await settled();
    const selectedId = row.id;
    const updated = {
      ...row,
      rationale: "Updated assessment.",
      priority: "elevated",
    };
    h.change({ eventType: "UPDATE", new: updated });
    assert.equal(
      h.observed.at(-1)?.reviews?.find((item) => item.id === selectedId)?.rationale,
      "Updated assessment.",
    );
    h.rows([]);
    const resolved = { ...updated, status, resolved_at: "2026-11-14T13:00:00Z" };
    h.change({ eventType: "UPDATE", new: resolved });
    assert.deepEqual(h.observed.at(-1)?.reviews, []);
    assert.equal(
      h.observed.at(-1)?.reviews?.find((item) => item.id === selectedId),
      undefined,
    );
    h.change({ eventType: "UPDATE", new: resolved });
    assert.deepEqual(h.observed.at(-1)?.reviews, []);
    h.feed.dispose();
  }
});

test("delete with only the primary key removes a review immediately", async () => {
  const h = harness();
  await settled();
  h.change({ eventType: "DELETE", old: { id: row.id } });
  assert.deepEqual(h.observed.at(-1)?.reviews, []);
  h.feed.dispose();
});

test("a stale in-flight snapshot cannot resurrect a realtime resolution", async () => {
  const h = harness();
  await settled();
  const release = h.holdNextRead();
  const refresh = h.feed.refresh(); // captures the old pending row
  h.rows([]);
  h.change({
    eventType: "UPDATE",
    new: { ...row, status: "confirmed", resolved_at: "2026-11-14T13:00:00Z" },
  });
  const afterResolution = h.observed.length;
  release();
  await refresh;
  await settled();
  assert.ok(
    h.observed.slice(afterResolution).every((state) => state.reviews?.length === 0),
  );
  h.feed.dispose();
});

test("a stale empty read cannot hide a newly inserted review", async () => {
  const h = harness(true, false, []);
  await settled();
  const release = h.holdNextRead();
  const refresh = h.feed.refresh();
  h.rows([row]);
  h.change({ eventType: "INSERT", new: row });
  const afterInsert = h.observed.length;
  release();
  await refresh;
  await settled();
  assert.ok(
    h.observed.slice(afterInsert).every((state) => state.reviews?.length === 1),
  );
  h.feed.dispose();
});

test("partial row events fall back to a pending snapshot without corrupting the queue", async () => {
  const h = harness();
  await settled();
  h.rows([]);
  h.change({ eventType: "UPDATE", new: { id: row.id } });
  assert.equal(h.observed.at(-1)?.reviews?.length, 1);
  await debounce();
  assert.deepEqual(h.observed.at(-1)?.reviews, []);
  h.feed.dispose();
});

test("reconnect replaces the snapshot with missed changes and never appends duplicates", async () => {
  const h = harness();
  await settled();
  h.status("SUBSCRIBED");
  await settled();
  const release = h.holdNextRead();
  const refresh = h.feed.refresh();
  h.status("CHANNEL_ERROR");
  const inserted = { ...row, id: "22222222-2222-4222-8222-222222222222" };
  h.rows([inserted]);
  h.status("SUBSCRIBED");
  release();
  await refresh;
  await settled();
  assert.deepEqual(h.observed.at(-1)?.reviews?.map((item) => item.id), [
    inserted.id,
  ]);
  h.change({ eventType: "INSERT", new: inserted });
  h.status("SUBSCRIBED");
  await settled();
  assert.deepEqual(h.observed.at(-1)?.reviews?.map((item) => item.id), [
    inserted.id,
  ]);
  assert.equal(h.channels(), 1);
  h.rows([]);
  h.status("SUBSCRIBED");
  await settled();
  assert.deepEqual(h.observed.at(-1)?.reviews, []);
  h.feed.dispose();
});
