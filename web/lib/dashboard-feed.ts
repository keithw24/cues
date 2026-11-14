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
export function watchDashboard(
  client: SupabaseClient,
  notify: (state: FeedState) => void,
  personObservationsEnabled = false,
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
            "seat_id,session_id,activity_id,status,task_score,updated_at" +
              (personObservationsEnabled ? ",tracking_valid,expression_context" : ""),
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
        personObservationsEnabled,
      );
      publish({ snapshot, error: null });
    } catch {
      publish({
        error:
          "Seat data could not be loaded. Check your connection and try again.",
      });
    } finally {
      fetching = false;
      publish({ loading: false });
      if (queued && !disposed) {
        queued = false;
        void refresh();
      }
    }
  }
  function scheduleRefresh() {
    if (disposed) return;
    clearTimeout(timer);
    timer = setTimeout(() => {
      void refresh();
    }, 100);
  }
  const channel = client.channel("teacher-dashboard");
  channel.on(
    "postgres_changes",
    { event: "*", schema: "public", table: "seat_state" },
    scheduleRefresh,
  );
  channel.subscribe((status) => {
    if (status === "SUBSCRIBED") {
      publish({ connection: "connected" });
      void refresh();
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
