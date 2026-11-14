import type { SupabaseClient } from "@supabase/supabase-js";
import { parseSnapshot, type Snapshot } from "./dashboard.ts";

export type FeedState = {
  snapshot: Snapshot | null;
  connection: "connecting" | "connected" | "disconnected";
  loading: boolean;
  error: string | null;
};

/** Subscribe before loading and resync after every reconnect to close observation gaps. */
export function watchDashboard(
  client: SupabaseClient,
  notify: (state: FeedState) => void,
  personObservationsEnabled = false,
) {
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
      const [seats, states, activities, stations] = await Promise.all([
        client
          .from("seats")
          .select("id,station_id,side,display_name,is_simulated")
          .abortSignal(signal),
        client
          .from("seat_state")
          .select(
            "seat_id,session_id,activity_id,status,task_score,updated_at" +
              (personObservationsEnabled ? ",tracking_valid" : ""),
          )
          .abortSignal(signal),
        client.from("activities").select("id,name").abortSignal(signal),
        client.from("stations").select("id,name").abortSignal(signal),
      ]);
      if ([seats, states, activities, stations].some((r) => r.error))
        throw new Error("Read failed");
      const snapshot = parseSnapshot(
        {
          seats: seats.data,
          states: states.data,
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
