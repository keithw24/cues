import type { SupabaseClient } from "@supabase/supabase-js";
import { parseSnapshot, type Snapshot } from "./dashboard.ts";

export type FeedState = {
  snapshot: Snapshot | null;
  connection: "connecting" | "connected" | "disconnected";
  loading: boolean;
  error: string | null;
};

/**
 * Subscribe before loading and resync after every reconnect to close observation gaps.
 * With a `station`, only that station's seats and their observations are read and shown
 * (the signed-in teacher's own station). With none, every readable station is shown.
 */
let subscriptionId = 0;
const REFRESH_MIN_MS = 1500;
type RealtimeChange = {
  eventType: "INSERT" | "UPDATE" | "DELETE";
  new: Record<string, unknown>;
  old: Record<string, unknown>;
};

export function watchDashboard(
  client: SupabaseClient,
  notify: (state: FeedState) => void,
  station?: string,
) {
  const scoped = station?.trim() ?? "";
  if (station !== undefined && !scoped) {
    notify({snapshot: null, loading: false, connection: "connecting",
      error: "Sign in and resolve your station before loading classroom observations."});
    return {refresh: async () => {}, disconnect() {}, dispose() {}};
  }
  let disposed = false;
  let fetching = false;
  let queued = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let lastRefreshAt = 0;
  let initialDone = false;
  let subscribedOnce = false;
  const abort = new AbortController();
  let state: FeedState = {
    snapshot: null,
    connection: "connecting",
    loading: true,
    error: null,
  };
  const publish = (patch: Partial<FeedState>) => {
    if (disposed) return;
    state = { ...state, ...patch };
    notify(state);
  };
  async function refresh() {
    if (disposed) return;
    if (fetching) {
      queued = true;
      return;
    }
    fetching = true;
    lastRefreshAt = Date.now();
    publish({ loading: true });
    try {
      const signal = AbortSignal.any([
        abort.signal,
        AbortSignal.timeout(12000),
      ]);
      let seatQuery = client
        .from("seats")
        .select("id,station_id,side,display_name,is_simulated");
      if (scoped) seatQuery = seatQuery.eq("station_id", scoped);
      let stationQuery = client.from("stations").select("id,name");
      if (scoped) stationQuery = stationQuery.eq("id", scoped);
      const [seats, states, activities, stations] = await Promise.all([
        seatQuery.abortSignal(signal),
        client
          .from("seat_state")
          .select(
            "seat_id,session_id,activity_id,status,task_score,updated_at,session_revision" +
              ",evaluated_progress,tracking_valid,expression_context",
          )
          .abortSignal(signal),
        client.from("activities").select("id,name").abortSignal(signal),
        stationQuery.abortSignal(signal),
      ]);
      if ([seats, states, activities, stations].some((r) => r.error))
        throw new Error("Read failed");
      // Observations belong to seats; keep only this station's.
      const stationSeats = new Set(
        ((seats.data ?? []) as unknown as { id?: unknown }[]).map((seat) => seat.id),
      );
      const stationStates = scoped
        ? ((states.data ?? []) as unknown as { seat_id?: unknown }[]).filter((row) =>
            stationSeats.has(row.seat_id),
          )
        : states.data;
      const snapshot = parseSnapshot(
        {
          seats: seats.data,
          states: stationStates,
          activities: activities.data,
          stations: stations.data,
        },
        true,
      );
      publish({ snapshot, error: null });
    } catch {
      publish({
        error:
          "Seat data could not be loaded. Check your connection and try again.",
      });
    } finally {
      fetching = false;
      initialDone = true;
      publish({ loading: false });
      if (queued && !disposed) {
        queued = false;
        void refresh();
      }
    }
  }
  // A full reload is four reads, so it is the exception: first load, a reconnect, a seat we
  // have not seen, or a row we cannot read. Run at most one per REFRESH_MIN_MS.
  function scheduleRefresh() {
    if (disposed || timer !== undefined) return;
    const wait = Math.max(100, lastRefreshAt + REFRESH_MIN_MS - Date.now());
    timer = setTimeout(() => {
      timer = undefined;
      void refresh();
    }, wait);
  }
  // A realtime event already carries the changed row: merge it into the snapshot we hold
  // instead of re-reading the tables.
  function applyChange(payload: RealtimeChange) {
    const held = state.snapshot;
    const row = payload.eventType === "DELETE" ? payload.old : payload.new;
    const seatId = row?.seat_id;
    if (!held || typeof seatId !== "string") return scheduleRefresh();
    if (!held.seats.some((seat) => seat.id === seatId)) {
      // Another station's person is not ours. A new person on our station needs the seats.
      if (!scoped || seatId.startsWith(`${scoped}-`)) scheduleRefresh();
      return;
    }
    if (payload.eventType === "DELETE") {
      publish({
        snapshot: { ...held, states: held.states.filter((s) => s.seat_id !== seatId) },
      });
      return;
    }
    try {
      const parsed = parseSnapshot(
        { seats: [], states: [row], activities: [], stations: [] },
        true,
      ).states[0];
      const others = held.states.filter((s) => s.seat_id !== seatId);
      publish({ snapshot: { ...held, states: [...others, parsed] } });
    } catch {
      scheduleRefresh();
    }
  }
  // A fresh topic each time: a channel still leaving under the old topic
  // would otherwise be handed back and never report SUBSCRIBED.
  const channel = client.channel(`teacher-dashboard:${++subscriptionId}`);
  channel.on(
    "postgres_changes",
    { event: "*", schema: "public", table: "seat_state" },
    (payload) => applyChange(payload as unknown as RealtimeChange),
  );
  channel.subscribe((status) => {
    if (status === "SUBSCRIBED") {
      publish({ connection: "connected" });
      // The first load is already running; a reload is for a reconnect, whose gap the
      // heartbeat would only fill a second later.
      const reconnect = subscribedOnce || initialDone;
      subscribedOnce = true;
      if (reconnect) void refresh();
    } else if (["CHANNEL_ERROR", "TIMED_OUT", "CLOSED"].includes(status))
      publish({ connection: "disconnected" });
  });
  void refresh();
  return {
    refresh,
    disconnect() {
      publish({ connection: "disconnected" });
    },
    dispose() {
      disposed = true;
      clearTimeout(timer);
      abort.abort();
      void client.removeChannel(channel);
    },
  };
}
