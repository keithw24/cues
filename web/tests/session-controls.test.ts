import assert from "node:assert/strict";
import test from "node:test";
import type { SupabaseClient } from "@supabase/supabase-js";
import {
  parseSession,
  readSession,
  changeSession,
  sessionOwnership,
  sessionControlState,
  sessionActions,
  type Session,
} from "../lib/session-controls.ts";
import { isEnabled } from "../lib/flags.ts";
const session: Session = {
  id: "11111111-1111-4111-8111-111111111111",
  station_id: "S1",
  current_activity_id: "raise_hand",
  started_at: "2026-11-14T12:00:00Z",
  ended_at: null,
  revision: 2,
};
function mock(data: unknown, error: unknown = null) {
  const calls: { name: string; args: unknown }[] = [];
  return {
    calls,
    client: {
      rpc(name: string, args: unknown) {
        calls.push({ name, args });
        return {
          abortSignal() {
            return Promise.resolve({ data, error });
          },
        };
      },
    } as unknown as SupabaseClient,
  };
}
test("session controls default off", () => {
  assert.equal(isEnabled("web.session_controls", {}), false);
  assert.equal(
    isEnabled("web.session_controls", { CUES_FLAG_WEB_SESSION_CONTROLS: "1" }),
    true,
  );
});
test("session parsing rejects wrong station, identity and invalid lifecycle", () => {
  for (const patch of [
    { station_id: "S2" },
    { id: "bad" },
    { revision: -1 },
    { revision: 0.5 },
    { started_at: "bad" },
    { ended_at: "bad" },
  ])
    assert.throws(() => parseSession({ ...session, ...patch }, "S1"));
});
test("session reads preserve authoritative IDs and catalog; no active session is explicit", async () => {
  const value = mock({
    session,
    activities: [{ id: "raise_hand", name: "Raise hand" }],
  });
  assert.deepEqual((await readSession(value.client, "S1")).session, session);
  assert.equal(
    (await readSession(mock({ session: null, activities: [] }).client, "S1"))
      .session,
    null,
  );
  await assert.rejects(
    readSession(
      mock({
        session: { ...session, ended_at: "2026-11-14T13:00:00Z" },
        activities: [],
      }).client,
      "S1",
    ),
  );
});
test("start uses expected session/revision, not a browser-generated session ID", async () => {
  const value = mock({
    ...session,
    current_activity_id: "thumbs_up",
    revision: 3,
  });
  await changeSession(value.client, "S1", session, "thumbs_up");
  assert.deepEqual(value.calls, [
    {
      name: "start_station_activity",
      args: {
        p_station_id: "S1",
        p_expected_session_id: session.id,
        p_expected_revision: 2,
        p_activity_id: "thumbs_up",
      },
    },
  ]);
  const empty = mock({ ...session, revision: 0 });
  await changeSession(empty.client, "S1", null, "raise_hand");
  assert.deepEqual(empty.calls[0].args, {
    p_station_id: "S1",
    p_expected_session_id: null,
    p_expected_revision: null,
    p_activity_id: "raise_hand",
  });
});
test("end requires current session and confirmed persisted ended timestamp", async () => {
  const value = mock({
    ...session,
    revision: 3,
    ended_at: "2026-11-14T13:00:00Z",
  });
  assert.ok((await changeSession(value.client, "S1", session, null)).ended_at);
  assert.equal(value.calls[0].name, "end_station_session");
  await assert.rejects(changeSession(value.client, "S1", null, null));
  await assert.rejects(
    changeSession(mock(session).client, "S1", session, null),
  );
});
test("denials, conflicts and invalid acknowledgements never produce local success", async () => {
  for (const value of [
    mock(null, { code: "42501", message: "private" }),
    mock(null, { code: "40001" }),
    mock({ ...session, current_activity_id: "other" }),
    mock({ ...session, station_id: "S2" }),
  ])
    await assert.rejects(
      changeSession(value.client, "S1", session, "thumbs_up"),
    );
  assert.equal(session.current_activity_id, "raise_hand");
});

test("station acknowledgement requires matching session/revision/activity and a fresh heartbeat", async () => {
  const { stationSyncLabel, parseStationRuntime } =
    await import("../lib/session-controls.ts");
  const now = Date.parse("2026-11-14T12:00:05Z");
  const runtime = {
    station_id: "S1",
    session_id: session.id,
    activity_id: "raise_hand",
    revision: 2,
    status: "ready" as const,
    error: null,
    updated_at: "2026-11-14T12:00:04Z",
  };
  const snapshot = {
    session,
    activities: [],
    station_runtime: runtime,
    latest_session: session,
  };
  assert.equal(stationSyncLabel(snapshot, now), "Activity synced");
  assert.equal(
    stationSyncLabel(snapshot, now + 6000),
    "Waiting for the camera to sync",
  );
  for (const patch of [
    { revision: 1 },
    { session_id: "22222222-2222-4222-8222-222222222222" },
    { activity_id: "thumbs_up" },
  ])
    assert.equal(
      stationSyncLabel(
        { ...snapshot, station_runtime: { ...runtime, ...patch } },
        now,
      ),
      "Waiting for the camera to sync",
    );
  const ended = { ...session, ended_at: "2026-11-14T12:00:05Z", revision: 3 };
  assert.equal(
    stationSyncLabel(
      { ...snapshot, session: null, latest_session: ended },
      now,
    ),
    "Waiting for the camera to stop",
  );
  assert.equal(
    stationSyncLabel(
      {
        ...snapshot,
        session: null,
        latest_session: ended,
        station_runtime: {
          ...runtime,
          revision: 3,
          status: "idle",
          activity_id: null,
        },
      },
      now,
    ),
    "Camera idle",
  );
  assert.equal(
    stationSyncLabel(
      {
        ...snapshot,
        station_runtime: {
          ...runtime,
          status: "error",
          error: "unsupported_activity",
        },
      },
      now,
    ),
    "Activity unavailable on the camera",
  );
  for (const patch of [
    { station_id: "S2" },
    { revision: -1 },
    { status: "invented" },
    { updated_at: "bad" },
  ])
    assert.throws(() => parseStationRuntime({ ...runtime, ...patch }, "S1"));
});

const teacher = "22222222-2222-4222-8222-222222222222";
test('empty S1 lookup permits Start Session and returns an owned Raise Hand session', async () => {
  const snapshot = await readSession(mock({session: null, activities: [
    {id: 'raise_hand', name: 'Raise your hand'}
  ]}).client, 'S1');
  assert.equal(sessionControlState(snapshot, false), 'ready');
  const created = {...session, revision: 0, teacher_id: teacher};
  const transport = mock(created);
  const result = await changeSession(transport.client, 'S1', snapshot.session, 'raise_hand', teacher);
  assert.equal(result.station_id, 'S1');
  assert.equal(result.current_activity_id, 'raise_hand');
  assert.equal(result.teacher_id, teacher);
  assert.equal(result.ended_at, null);
  assert.equal(JSON.stringify(transport.calls).includes('teacher_id'), false);
  assert.equal(sessionControlState({...snapshot, session: result}, false), 'active');
  assert.equal(sessionControlState(snapshot, true), 'refresh');
});
test('missing session field is empty and historical sessions remain active, never claimed', async () => {
  const empty = await readSession(mock({activities: []}).client, 'S1');
  assert.equal(sessionControlState(empty, false), 'ready');
  const historical = {...session, teacher_id: null};
  assert.equal(sessionControlState({session: historical, activities: []}, false), 'active');
  assert.equal(sessionOwnership(historical, teacher), 'unowned');
});
test("a new session must come back owned by the signed-in teacher", async () => {
  const created = { ...session, revision: 0, teacher_id: teacher };
  const { client, calls } = mock(created);
  const result = await changeSession(client, "S1", null, "raise_hand", teacher);
  assert.equal(result.teacher_id, teacher);
  // The owner comes from auth.uid() in the database, never from the browser.
  assert.equal(JSON.stringify(calls[0].args).includes(teacher), false);
  for (const owner of [null, "33333333-3333-4333-8333-333333333333"])
    await assert.rejects(
      changeSession(
        mock({ ...created, teacher_id: owner }).client,
        "S1",
        null,
        "raise_hand",
        teacher,
      ),
    );
  await assert.rejects(
    changeSession(mock(created).client, "S1", null, "raise_hand", null),
  );
});
test("fresh authenticated sessions require the deployed ownership projection", async () => {
  const { client } = mock({ ...session, revision: 0 });
  await assert.rejects(
    changeSession(client, "S1", null, "raise_hand", teacher),
  );
});
test("session ownership labels", () => {
  assert.equal(
    sessionOwnership({ ...session, teacher_id: teacher }, teacher),
    "owned",
  );
  assert.equal(
    sessionOwnership({ ...session, teacher_id: null }, teacher),
    "unowned",
  );
  assert.equal(
    sessionOwnership(
      { ...session, teacher_id: "33333333-3333-4333-8333-333333333333" },
      teacher,
    ),
    "other",
  );
  assert.throws(() => parseSession({ ...session, teacher_id: "nobody" }, "S1"));
});

test("retiring a seeded unowned session never claims it", async () => {
  const old = { ...session, teacher_id: null };
  const ended = {
    ...old,
    revision: old.revision + 1,
    ended_at: "2026-11-14T13:00:00Z",
  };
  const value = mock(ended);
  assert.equal(
    (await changeSession(value.client, "S1", old, null, teacher)).teacher_id,
    null,
  );
  assert.deepEqual(value.calls[0], {
    name: "end_station_session",
    args: {
      p_station_id: "S1",
      p_expected_session_id: old.id,
      p_expected_revision: old.revision,
    },
  });
  await assert.rejects(
    changeSession(
      mock({ ...ended, teacher_id: teacher }).client,
      "S1",
      old,
      null,
      teacher,
    ),
  );
});

test("seeded end -> fresh owned start -> read/refresh -> end -> new UUID uses only existing RPCs", async () => {
  let active: Session | null = { ...session, teacher_id: null };
  let latest = active;
  let sequence = 0;
  const calls: { name: string; args: Record<string, unknown> }[] = [];
  const client = {
    rpc(name: string, args: Record<string, unknown>) {
      calls.push({ name, args });
      assert.equal(Object.hasOwn(args, "teacher_id"), false);
      assert.equal(Object.hasOwn(args, "p_teacher_id"), false);
      let data: unknown;
      if (name === "read_station_session")
        data = {
          session: active,
          latest_session: latest,
          activities: [{ id: "raise_hand", name: "Raise hand" }],
        };
      else {
        assert.equal(args.p_expected_session_id, active?.id ?? null);
        assert.equal(args.p_expected_revision, active?.revision ?? null);
        if (name === "end_station_session") {
          data = latest = {
            ...active!,
            revision: active!.revision + 1,
            ended_at: "2026-11-14T13:00:00Z",
          };
          active = null;
        } else {
          active = active
            ? {
                ...active,
                revision: active.revision + 1,
                current_activity_id: String(args.p_activity_id),
              }
            : {
                ...session,
                id: `00000000-0000-4000-8000-${String(++sequence).padStart(12, "0")}`,
                revision: 0,
                teacher_id: teacher,
                current_activity_id: String(args.p_activity_id),
              };
          data = latest = active;
        }
      }
      return { abortSignal: () => Promise.resolve({ data, error: null }) };
    },
  } as unknown as SupabaseClient;
  const old = (await readSession(client, "S1")).session!;
  assert.equal(old.teacher_id, null);
  await changeSession(client, "S1", old, null, teacher);
  assert.equal((await readSession(client, "S1")).session, null);
  const first = await changeSession(client, "S1", null, "raise_hand", teacher);
  assert.equal(first.teacher_id, teacher);
  assert.equal(first.station_id, "S1");
  assert.equal(first.ended_at, null);
  assert.equal(first.current_activity_id, "raise_hand");
  assert.notEqual(first.id, old.id);
  assert.deepEqual((await readSession(client, "S1")).session, first);
  assert.ok((await changeSession(client, "S1", first, null, teacher)).ended_at);
  const second = await changeSession(client, "S1", null, "raise_hand", teacher);
  assert.notEqual(first.id, second.id);
  assert.equal(second.teacher_id, teacher);
});

test("the session bar offers one primary action per state", () => {
  const running = {
    id: "00000000-0000-4000-8000-000000000001",
    current_activity_id: "raise_hand",
  } as unknown as Session;
  const base = { activities: [], station_runtime: null, latest_session: null };
  // Loading: nothing to act on yet, so no Start flashes.
  assert.deepEqual(sessionActions(null, ""), { primary: null, end: false });
  // Ready: Start only.
  assert.deepEqual(sessionActions({ ...base, session: null } as never, ""), {
    primary: "start",
    end: false,
  });
  // Running, same or no activity picked: End only.
  for (const pick of ["", "raise_hand"])
    assert.deepEqual(
      sessionActions({ ...base, session: running } as never, pick),
      { primary: null, end: true },
    );
  // Running, a different activity picked: Change plus End.
  assert.deepEqual(
    sessionActions({ ...base, session: running } as never, "thumbs_up"),
    { primary: "change", end: true },
  );
});

test("the primary button style list stays one complete rule", async () => {
  const { readFileSync } = await import("node:fs");
  const css = readFileSync(
    new URL("../components/workspace.css", import.meta.url),
    "utf8",
  );
  // The pill style must reach the primary buttons; a rule pasted into the
  // middle of this selector list once stripped it.
  assert.match(
    css,
    /\.dashboard-shell \.primary-button,\n\.dashboard-shell \.session-controls \.session-primary,\n\.dashboard-shell \.review-action-buttons button:first-child \{\n  min-height: 40px;[\s\S]*?border-radius: 999px;/,
  );
});
