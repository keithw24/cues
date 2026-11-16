import type { SupabaseClient } from "@supabase/supabase-js";
import {
  parseTeacherReviews,
  pendingReviews,
  REVIEW_COLUMNS_WITH_INTERVENTIONS,
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
export const SIGN_IN_TO_SEE_REVIEWS =
  "Sign in as a teacher to see reviews for your sessions.";

/**
 * Read-only Supabase feed; queue and selected details share this snapshot.
 * Reviews are readable only by the signed-in teacher who owns their session
 * (migration 006), so reads are scoped to that teacher's sessions. With a `station`,
 * only reviews from that teacher's sessions at that station are shown.
 */
export function watchTeacherReviews(
  client: SupabaseClient,
  notify: (state: ReviewFeedState) => void,
  station?: string,
) {
  const scoped = station?.trim() ?? "";
  if (station !== undefined && !scoped) {
    notify(DISABLED_REVIEWS);
    return { refresh: async () => {}, disconnect() {}, dispose() {} };
  }
  let state = { ...INITIAL_REVIEWS };
  let disposed = false;
  let fetching = false;
  let queued = false;
  let revision = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  // The teacher whose queue is on screen, and the sessions they own.
  let shownTeacher: string | null = null;
  let owned = new Set<string>();
  const abort = new AbortController();
  const signal = () =>
    AbortSignal.any([abort.signal, AbortSignal.timeout(12000)]);
  const publish = (patch: Partial<ReviewFeedState>) => {
    if (disposed) return;
    state = { ...state, ...patch };
    notify(state);
  };
  // Never leave one teacher's queue on screen for another (or for no one).
  const forget = (teacherId: string | null) => {
    if (teacherId === shownTeacher) return;
    shownTeacher = teacherId;
    owned = new Set();
    publish({
      reviews: null,
      error: teacherId ? null : SIGN_IN_TO_SEE_REVIEWS,
    });
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
      const { data: auth } = await client.auth.getSession();
      const teacherId = auth.session?.user.id ?? null;
      forget(teacherId);
      if (!teacherId) {
        publish({ reviews: null, error: SIGN_IN_TO_SEE_REVIEWS });
        return;
      }
      let sessionQuery = client.from("sessions").select("id").eq("teacher_id", teacherId);
      if (scoped) sessionQuery = sessionQuery.eq("station_id", scoped);
      const sessions = await sessionQuery.abortSignal(signal());
      if (sessions.error) throw new Error("Session read failed");
      const ids = (sessions.data ?? [])
        .map((session: { id?: unknown }) => session.id)
        .filter((id): id is string => typeof id === "string");
      let data: unknown[] = [];
      if (ids.length > 0) {
        // RLS (own_teacher_reviews_read) already limits rows to this teacher's
        // sessions; listing every session id would grow the URL without bound.
        const read = await client
          .from("teacher_reviews")
          .select(REVIEW_COLUMNS_WITH_INTERVENTIONS)
          .eq("status", "pending")
          .abortSignal(signal());
        if (read.error) throw new Error("Review read failed");
        data = read.data ?? [];
      }
      // A read started before a row event/reconnect must not undo newer state.
      if (startedAtRevision !== revision) {
        queued = true;
        return;
      }
      owned = new Set(ids);
      publish({
        // Defense in depth: drop any row outside the teacher's own sessions.
        reviews: pendingReviews(parseTeacherReviews(data)).filter((review) =>
          owned.has(review.session_id),
        ),
        error: null,
      });
    } catch {
      // A failure from before a sign-in change must not replace newer state.
      if (startedAtRevision !== revision) {
        queued = true;
        return;
      }
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
          // Only reviews on this teacher's sessions belong in the queue.
          if (!owned.has(review.session_id)) throw new Error("Not owned");
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
  // Signing in or out changes which reviews are readable; reload for the new teacher.
  const { data: authWatch } = client.auth.onAuthStateChange(
    (event, session) => {
      if (
        disposed ||
        event === "INITIAL_SESSION" ||
        event === "TOKEN_REFRESHED"
      )
        return;
      revision++;
      forget(event === "SIGNED_OUT" ? null : (session?.user.id ?? null));
      // Defer: Supabase calls inside this callback can deadlock the auth lock.
      setTimeout(() => void refresh(), 0);
    },
  );
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
      authWatch.subscription.unsubscribe();
      void client.removeChannel(channel);
    },
  };
}
