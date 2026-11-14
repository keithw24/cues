import type { SupabaseClient } from "@supabase/supabase-js";
export type Session = {
  id: string;
  station_id: string;
  current_activity_id: string | null;
  started_at: string;
  ended_at: string | null;
  revision: number;
  /** Present once migration 006 is deployed; null for unowned historical sessions. */
  teacher_id?: string | null;
};
export type StationRuntime = {
  station_id: string;
  session_id: string | null;
  activity_id: string | null;
  revision: number | null;
  status: "ready" | "idle" | "error";
  error: "unsupported_activity" | null;
  updated_at: string;
};
export type SessionSnapshot = {
  latest_session?: Session | null;
  station_runtime?: StationRuntime | null;
  session: Session | null;
  activities: { id: string; name: string }[];
};
/** A successful empty lookup is ready for creation, not a refresh error. */
export function sessionControlState(snapshot: SessionSnapshot | null, refreshRequired: boolean) {
  if (refreshRequired) return 'refresh' as const;
  if (!snapshot) return 'loading' as const;
  return snapshot.session ? 'active' as const : 'ready' as const;
}
/** Which session actions the bar offers: one primary action at a time.
 * Start when there is no session; with a session, End, plus Change only
 * when a different activity is picked. Nothing while loading. */
export function sessionActions(
  snapshot: SessionSnapshot | null,
  selection: string,
): { primary: "start" | "change" | null; end: boolean } {
  if (!snapshot) return { primary: null, end: false };
  const session = snapshot.session;
  if (!session) return { primary: "start", end: false };
  const changed = !!selection && session.current_activity_id !== selection;
  return { primary: changed ? "change" : null, end: true };
}
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export function parseSession(input: unknown, station: string): Session {
  const s = input as Session;
  if (
    !s ||
    typeof s !== "object" ||
    !uuid.test(s.id) ||
    s.station_id !== station ||
    !Number.isInteger(s.revision) ||
    s.revision < 0 ||
    (s.current_activity_id !== null &&
      (typeof s.current_activity_id !== "string" ||
        !s.current_activity_id.trim())) ||
    typeof s.started_at !== "string" ||
    !Number.isFinite(Date.parse(s.started_at)) ||
    (s.ended_at !== null &&
      (typeof s.ended_at !== "string" ||
        !Number.isFinite(Date.parse(s.ended_at)))) ||
    (s.teacher_id != null &&
      (typeof s.teacher_id !== "string" || !uuid.test(s.teacher_id)))
  )
    throw new Error("Invalid session response");
  return {
    id: s.id,
    station_id: s.station_id,
    current_activity_id: s.current_activity_id,
    started_at: s.started_at,
    ended_at: s.ended_at,
    revision: s.revision,
    ...("teacher_id" in s ? { teacher_id: s.teacher_id ?? null } : {}),
  };
}
/** Reviews are readable only for sessions the signed-in teacher owns (migration 006). */
export function sessionOwnership(
  session: Session | null,
  teacherId: string | null,
): "owned" | "unowned" | "other" | "unknown" {
  if (!session || !teacherId || !("teacher_id" in session)) return "unknown";
  if (session.teacher_id == null) return "unowned";
  return session.teacher_id === teacherId ? "owned" : "other";
}
export function parseStationRuntime(
  input: unknown,
  station: string,
): StationRuntime | null {
  if (input == null) return null;
  const r = input as StationRuntime;
  if (
    typeof r !== "object" ||
    r.station_id !== station ||
    (r.session_id !== null &&
      (typeof r.session_id !== "string" || !uuid.test(r.session_id))) ||
    (r.activity_id !== null &&
      (typeof r.activity_id !== "string" || !r.activity_id.trim())) ||
    (r.revision !== null &&
      (!Number.isInteger(r.revision) || r.revision < 0)) ||
    !["ready", "idle", "error"].includes(r.status) ||
    (r.error !== null && r.error !== "unsupported_activity") ||
    typeof r.updated_at !== "string" ||
    !Number.isFinite(Date.parse(r.updated_at))
  )
    throw new Error("Invalid station response");
  return {
    station_id: r.station_id,
    session_id: r.session_id,
    activity_id: r.activity_id,
    revision: r.revision,
    status: r.status,
    error: r.error,
    updated_at: r.updated_at,
  };
}
/** Heartbeat is acknowledgement of configuration, never camera/model readiness. */
export function stationSyncLabel(
  snapshot: SessionSnapshot,
  now: number,
): string {
  const runtime = snapshot.station_runtime;
  const expected = snapshot.session ?? snapshot.latest_session;
  const age = runtime ? now - Date.parse(runtime.updated_at) : Infinity;
  const fresh = age >= -5000 && age <= 5000;
  const matches =
    runtime &&
    runtime.session_id === (expected?.id ?? null) &&
    runtime.revision === (expected?.revision ?? null);
  if (!fresh || !matches)
    return snapshot.session
      ? "Waiting for the camera to sync"
      : expected?.ended_at
        ? "Waiting for the camera to stop"
        : "Waiting for the camera";
  if (runtime.status === "error") return "Activity unavailable on the camera";
  if (!snapshot.session)
    return runtime.status === "idle"
      ? "Camera idle"
      : "Waiting for the camera to stop";
  return runtime.status === "ready" &&
    runtime.activity_id === snapshot.session.current_activity_id
    ? "Activity synced"
    : "Waiting for the camera to sync";
}
export async function readSession(
  client: SupabaseClient,
  station: string,
): Promise<SessionSnapshot> {
  const { data, error } = await client
    .rpc("read_station_session", { p_station_id: station })
    .abortSignal(AbortSignal.timeout(12000));
  if (error?.code === '42501')
    throw new Error("This classroom camera isn't linked to your account yet.");
  if (error || !data || !Array.isArray(data.activities))
    throw new Error(
      "Session could not be loaded. Check your camera link and retry.",
    );
  const activities = data.activities.map((a: { id: string; name: string }) => {
    if (
      !a ||
      typeof a.id !== "string" ||
      !a.id.trim() ||
      typeof a.name !== "string" ||
      !a.name.trim()
    )
      throw new Error("Activity catalog unavailable");
    return { id: a.id, name: a.name };
  });
  const session =
    data.session == null ? null : parseSession(data.session, station);
  if (session?.ended_at) throw new Error("Unexpected ended session");
  return {
    session,
    activities,
    latest_session:
      data.latest_session == null
        ? session
        : parseSession(data.latest_session, station),
    station_runtime: parseStationRuntime(data.station_runtime, station),
  };
}
export async function changeSession(
  client: SupabaseClient,
  station: string,
  session: Session | null,
  activityId: string | null,
  teacherId: string | null = null,
): Promise<Session> {
  if (session?.ended_at || (activityId === null && !session))
    throw new Error("Refresh the session before acting.");
  const { data, error } = await client
    .rpc(
      activityId === null ? "end_station_session" : "start_station_activity",
      {
        p_station_id: station,
        p_expected_session_id: session?.id ?? null,
        p_expected_revision: session?.revision ?? null,
        ...(activityId === null ? {} : { p_activity_id: activityId }),
      },
    )
    .abortSignal(AbortSignal.timeout(12000));
  if (error)
    throw new Error(
      "Action could not be saved. Refresh to check the session before trying again.",
    );
  const result = parseSession(data, station);
  if (
    (session &&
      (result.id !== session.id || result.revision !== session.revision + 1)) ||
    (!session && result.revision !== 0) ||
    // The database sets the owner from auth.uid(); the browser only checks it.
    (!session && teacherId !== null && result.teacher_id !== teacherId) ||
    (!session && "teacher_id" in result && !teacherId) ||
    (session &&
      "teacher_id" in session &&
      result.teacher_id !== session.teacher_id) ||
    (activityId === null
      ? !result.ended_at
      : result.ended_at || result.current_activity_id !== activityId)
  )
    throw new Error(
      "Session result could not be verified. Refresh before trying again.",
    );
  return result;
}
