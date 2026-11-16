import { useEffect, useState, type MutableRefObject } from "react";
import type { SupabaseClient } from "@supabase/supabase-js";
import { watchDashboard, type FeedState } from "@/lib/dashboard-feed";
import {
  INITIAL_REVIEWS,
  watchTeacherReviews,
  type ReviewFeedState,
} from "@/lib/teacher-review-feed";

export const INITIAL_FEED: FeedState = {
  snapshot: null,
  connection: "connecting",
  loading: true,
  error: null,
};

type Options = {
  client: SupabaseClient | null;
  station: string;
  /** Reviews the teacher just resolved, hidden until the database catches up. */
  resolvedReviewIds: MutableRefObject<Set<string>>;
};

/** The classroom's seats and its review requests, kept live. Reconnects when the browser
 * comes back online. The setters let the caller clear both when the station changes. */
export function useDashboardFeeds({
  client,
  station,
  resolvedReviewIds,
}: Options) {
  const [feed, setFeed] = useState<FeedState>(INITIAL_FEED);
  const [attempt, setAttempt] = useState(0);
  const [reviews, setReviews] = useState<ReviewFeedState>(
    INITIAL_REVIEWS,
  );
  const [reviewAttempt, setReviewAttempt] = useState(0);
  useEffect(() => {
    if (!client) return;
    const subscription = watchDashboard(
      client,
      (state) => {
        setFeed((previous) => ({
          ...state,
          snapshot: station ? (state.snapshot ?? previous.snapshot) : null,
        }));
      },
      station,
    );
    const offline = () => subscription.disconnect();
    const online = () => setAttempt((n) => n + 1);
    window.addEventListener("offline", offline);
    window.addEventListener("online", online);
    return () => {
      window.removeEventListener("offline", offline);
      window.removeEventListener("online", online);
      subscription.dispose();
    };
  }, [attempt, client, station]);
  useEffect(() => {
    if (!client) return;
    const subscription = watchTeacherReviews(
      client,
      (state) =>
        setReviews({
          ...state,
          reviews:
            state.reviews?.filter(
              (review) => !resolvedReviewIds.current.has(review.id),
            ) ?? null,
        }),
      station,
    );
    const offline = () => subscription.disconnect();
    const online = () => setReviewAttempt((n) => n + 1);
    window.addEventListener("offline", offline);
    window.addEventListener("online", online);
    return () => {
      window.removeEventListener("offline", offline);
      window.removeEventListener("online", online);
      subscription.dispose();
    };
  }, [client, reviewAttempt, station, resolvedReviewIds]);
  const retryFeed = () => setAttempt((n) => n + 1);
  const retryReviews = () => setReviewAttempt((n) => n + 1);
  return { feed, setFeed, reviews, setReviews, retryFeed, retryReviews };
}
