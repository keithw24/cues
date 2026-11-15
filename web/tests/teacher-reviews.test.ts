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
  SIGN_IN_TO_SEE_REVIEWS,
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

const TEACHER = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";

function harness(
  enabled = true,
  initialFailure = false,
  initialRows: unknown = [row],
  {
    signedIn = true,
    ownedSessions = { [TEACHER]: [row.session_id] } as Record<string, string[]>,
  } = {},
) {
  let rows: unknown = initialRows;
  let teacher: string | null = signedIn ? TEACHER : null;
  let authChange: (
    event: string,
    session: { user: { id: string } } | null,
  ) => void = () => {};
  let authUnsubscribed = false;
  let sessionsFail = false;
  const calls = { getSession: 0, sessions: 0, authWatchers: 0 };
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
    auth: {
      getSession: async () => {
        calls.getSession++;
        return {
          data: { session: teacher ? { user: { id: teacher } } : null },
        };
      },
      onAuthStateChange(callback: typeof authChange) {
        calls.authWatchers++;
        authChange = callback;
        return {
          data: {
            subscription: {
              unsubscribe() {
                authUnsubscribed = true;
              },
            },
          },
        };
      },
    },
    from(table: string) {
      if (table === "sessions")
        return {
          select(columns: string) {
            assert.equal(columns, "id");
            return {
              eq(column: string, value: string) {
                assert.equal(column, "teacher_id");
                assert.equal(value, teacher);
                calls.sessions++;
                return {
                  abortSignal: async () => ({
                    data: sessionsFail
                      ? null
                      : (ownedSessions[value] ?? []).map((id) => ({ id })),
                    error: sessionsFail ? { message: "denied" } : null,
                  }),
                };
              },
            };
          },
        };
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
    calls,
    failSessions() {
      sessionsFail = true;
    },
    signIn(id = TEACHER) {
      teacher = id;
      authChange("SIGNED_IN", { user: { id } });
    },
    signOut() {
      teacher = null;
      authChange("SIGNED_OUT", null);
    },
    authUnsubscribed: () => authUnsubscribed,
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
  assert.deepEqual(h.calls, { getSession: 0, sessions: 0, authWatchers: 0 });
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

test("reviews are read only for sessions the signed-in teacher owns", async () => {
  const foreign = {
    ...row,
    id: "55555555-5555-4555-8555-555555555555",
    session_id: "00000000-0000-4000-8000-000000000099",
  };
  // Even if the server returned another teacher's row, it never reaches the queue.
  const h = harness(true, false, [row, foreign]);
  await settled();
  assert.deepEqual(
    h.observed.at(-1)?.reviews?.map((review) => review.id),
    [row.id],
  );
  assert.equal(h.observed.at(-1)?.error, null);
  h.feed.dispose();
  assert.equal(h.authUnsubscribed(), true);
});
test("signed out, the queue asks the teacher to sign in instead of failing", async () => {
  const h = harness(true, false, [row], { signedIn: false });
  await settled();
  assert.equal(h.reads(), 0);
  assert.equal(h.observed.at(-1)?.reviews, null);
  assert.equal(h.observed.at(-1)?.error, SIGN_IN_TO_SEE_REVIEWS);
  h.signIn();
  await debounce();
  assert.equal(h.observed.at(-1)?.reviews?.length, 1);
  assert.equal(h.observed.at(-1)?.error, null);
  const readsBeforeSignOut = h.reads();
  h.signOut();
  assert.equal(h.observed.at(-1)?.reviews, null);
  assert.equal(h.observed.at(-1)?.error, SIGN_IN_TO_SEE_REVIEWS);
  await debounce();
  assert.equal(h.observed.at(-1)?.reviews, null);
  assert.equal(h.observed.at(-1)?.error, SIGN_IN_TO_SEE_REVIEWS);
  assert.equal(h.reads(), readsBeforeSignOut);
  h.feed.dispose();
});
test("a teacher with no sessions sees an empty queue without querying reviews", async () => {
  const h = harness(true, false, [row], { ownedSessions: {} });
  await settled();
  assert.equal(h.reads(), 0);
  assert.deepEqual(h.observed.at(-1)?.reviews, []);
  assert.equal(h.observed.at(-1)?.error, null);
  h.feed.dispose();
});
test("realtime rows from another teacher's session never enter the queue", async () => {
  const h = harness(true, false, []);
  await settled();
  h.change({
    eventType: "INSERT",
    new: {
      ...row,
      id: "44444444-4444-4444-8444-444444444444",
      session_id: "00000000-0000-4000-8000-000000000099",
    },
  });
  assert.deepEqual(h.observed.at(-1)?.reviews, []);
  h.feed.dispose();
});
test("switching teachers clears the previous teacher's queue at once", async () => {
  const OTHER = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
  const h = harness(true, false, [row], { ownedSessions: { [TEACHER]: [row.session_id] } });
  await settled();
  assert.equal(h.observed.at(-1)?.reviews?.length, 1);
  // Teacher B signs in over teacher A, with no sign-out in between.
  h.signIn(OTHER);
  assert.equal(h.observed.at(-1)?.reviews, null);
  await debounce();
  // B owns no sessions, so A's review never comes back.
  assert.deepEqual(h.observed.at(-1)?.reviews, []);
  h.feed.dispose();
});
test("a failed session read shows the load error, not the sign-in message", async () => {
  const h = harness();
  h.failSessions();
  await settled();
  assert.equal(h.reads(), 0);
  assert.equal(h.observed.at(-1)?.reviews, null);
  assert.match(h.observed.at(-1)?.error ?? "", /could not be loaded/);
  h.feed.dispose();
});
test("a read that fails after sign-out cannot replace the sign-in message", async () => {
  const h = harness();
  await settled();
  const release = h.holdNextRead();
  h.fail();
  void h.feed.refresh();
  await settled();
  const signedOutAt = h.observed.length;
  h.signOut();
  release();
  await debounce();
  assert.equal(h.observed.at(-1)?.reviews, null);
  assert.equal(h.observed.at(-1)?.error, SIGN_IN_TO_SEE_REVIEWS);
  // The stale failure never flashes the load error after sign-out.
  assert.ok(
    h.observed
      .slice(signedOutAt)
      .every((state) => !/could not be loaded/.test(state.error ?? "")),
  );
  h.feed.dispose();
});
test("teacher A's in-flight read and realtime rows never reach teacher B", async () => {
  const OTHER = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
  const otherSession = "00000000-0000-4000-8000-000000000002";
  const otherRow = {
    ...row,
    id: "66666666-6666-4666-8666-666666666666",
    session_id: otherSession,
  };
  const h = harness(true, false, [row, otherRow], {
    ownedSessions: { [TEACHER]: [row.session_id], [OTHER]: [otherSession] },
  });
  await settled();
  // Hold A's next review read, then switch to B before it returns.
  const release = h.holdNextRead();
  void h.feed.refresh();
  await settled();
  const switchedAt = h.observed.length;
  h.signIn(OTHER);
  // A realtime row for A's session arrives mid-switch.
  h.change({
    eventType: "INSERT",
    new: { ...row, id: "77777777-7777-4777-8777-777777777777" },
  });
  release();
  await debounce();
  const after = h.observed.slice(switchedAt);
  assert.ok(
    after.every(
      (state) =>
        !state.reviews?.some((review) => review.session_id === row.session_id),
    ),
  );
  assert.deepEqual(
    h.observed.at(-1)?.reviews?.map((review) => review.id),
    [otherRow.id],
  );
  h.feed.dispose();
});

test("a review closed automatically when its session ended is valid but never in the queue", () => {
  const closed = parseTeacherReviews([
    { ...row, status: "expired", resolved_at: "2026-11-14T13:00:00Z" },
  ]);
  assert.equal(closed[0].status, "expired");
  assert.deepEqual(pendingReviews(closed), []); // nothing "waiting" for an ended session
  assert.throws(() => parseTeacherReviews([{ ...row, status: "archived" }]));
});
