import type { SupabaseClient } from "@supabase/supabase-js";
import {
  parseTeacherReviews,
  pendingReviews,
  REVIEW_COLUMNS,
  type TeacherReview,
} from "./teacher-reviews.ts";

export type ReviewFeedState = {
  reviews: TeacherReview[] | null;
  connection: "disabled" | "connecting" | "connected" | "disconnected";
  loading: boolean;
  error: string | null;
};
export const INITIAL_REVIEWS: ReviewFeedState = {
  reviews: null,
  connection: "connecting",
  loading: true,
  error: null,
};
export const DISABLED_REVIEWS: ReviewFeedState = {
  reviews: null,
  connection: "disabled",
  loading: false,
  error: null,
};
let subscriptionId = 0;

/** Read-only Supabase feed; queue and selected details share this snapshot. */
export function watchTeacherReviews(
  client: SupabaseClient,
  notify: (state: ReviewFeedState) => void,
  enabled: boolean,
) {
  if (!enabled) {
    notify(DISABLED_REVIEWS);
    return { refresh: async () => {}, disconnect() {}, dispose() {} };
  }
  let state = { ...INITIAL_REVIEWS };
  let disposed = false;
  let fetching = false;
  let queued = false;
  let revision = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const abort = new AbortController();
  const publish = (patch: Partial<ReviewFeedState>) => {
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
    const startedAtRevision = revision;
    publish({ loading: true });
    try {
      const { data, error } = await client
        .from("teacher_reviews")
        .select(REVIEW_COLUMNS)
        .eq("status", "pending")
        .abortSignal(
          AbortSignal.any([abort.signal, AbortSignal.timeout(12000)]),
        );
      if (error) throw new Error("Review read failed");
      // A read started before a row event/reconnect must not undo newer state.
      if (startedAtRevision !== revision) {
        queued = true;
        return;
      }
      publish({
        reviews: pendingReviews(parseTeacherReviews(data)),
        error: null,
      });
    } catch {
      publish({
        error:
          "Teacher reviews could not be loaded. Seat observations are still available.",
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
  // Watch all row changes: filtering Realtime to pending would miss status exits.
  const channel = client.channel(`teacher-reviews:${++subscriptionId}`);
  channel.on(
    "postgres_changes",
    { event: "*", schema: "public", table: "teacher_reviews" },
    (payload) => {
      if (disposed) return;
      revision++;
      try {
        if (payload.eventType === "DELETE") {
          const id = payload.old.id;
          if (typeof id === "string" && state.reviews !== null)
            publish({ reviews: state.reviews.filter((row) => row.id !== id) });
        } else if (
          payload.eventType === "INSERT" || payload.eventType === "UPDATE"
        ) {
          const [review] = parseTeacherReviews([payload.new]);
          // Upsert by identity rather than append: duplicate events are harmless.
          const remaining = (state.reviews ?? []).filter(
            (row) => row.id !== review.id,
          );
          publish({ reviews: pendingReviews([...remaining, review]) });
        }
      } catch {
        // Partial/incompatible payloads are reconciled by the authorized SELECT.
      }
      clearTimeout(timer);
      timer = setTimeout(() => {
        void refresh();
      }, 100);
    },
  );
  channel.subscribe((status) => {
    if (disposed) return;
    if (status === "SUBSCRIBED") {
      revision++;
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
