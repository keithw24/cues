import assert from "node:assert/strict";
import test from "node:test";
import type { SupabaseClient } from "@supabase/supabase-js";
import {
  parseSession,
  readSession,
  changeSession,
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
    "Waiting for station to sync",
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
      "Waiting for station to sync",
    );
  const ended = { ...session, ended_at: "2026-11-14T12:00:05Z", revision: 3 };
  assert.equal(
    stationSyncLabel(
      { ...snapshot, session: null, latest_session: ended },
      now,
    ),
    "Waiting for station to stop",
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
    "Station idle",
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
    "Activity unavailable on station",
  );
  for (const patch of [
    { station_id: "S2" },
    { revision: -1 },
    { status: "invented" },
    { updated_at: "bad" },
  ])
    assert.throws(() => parseStationRuntime({ ...runtime, ...patch }, "S1"));
});
