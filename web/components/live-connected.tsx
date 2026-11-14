"use client";

import { useEffect, useState } from "react";
import { seatViews, type Snapshot } from "@/lib/dashboard";
import { watchDashboard, type FeedState } from "@/lib/dashboard-feed";
import { nextUp } from "@/lib/next-up";
import {
  inCameraView,
  isFresh,
  observationPresentation,
  type ObservationOptions,
} from "@/lib/observation-presentation";
import { displayName } from "@/lib/simulated-names";
import { createDashboardClient } from "@/lib/supabase";
import { resolveTeacherReview } from "@/lib/teacher-review-actions";
import {
  DISABLED_REVIEWS,
  INITIAL_REVIEWS,
  watchTeacherReviews,
  type ReviewFeedState,
} from "@/lib/teacher-review-feed";
import {
  activityLabel,
  evidenceLabels,
  groupReviewsBySeat,
  priorityLabels,
  resolutionLabels,
  reviewPrompt,
  teacherRationale,
} from "@/lib/teacher-reviews";
import {
  clockTime,
  LiveCameraLink,
  LiveFeed,
  LiveCard,
  LiveClass,
  LiveHero,
  type LiveStatus,
  type LiveStudent,
} from "@/components/live-screen";

// The Live screen on real data (web.live_data). People are the ones the
// station camera sees right now. The feed lists finishes this page has seen
// since it opened (this tab only, never stored or used to decide anything)
// and review times from the backend.
type Finish = { seatId: string; at: number };
type Live = { feed: FeedState; finishes: Finish[] };

const INITIAL_FEED: FeedState = {
  snapshot: null,
  connection: "connecting",
  loading: true,
  error: null,
};

/** Seats that moved to done between two snapshots, timed by the backend. */
function newFinishes(previous: Snapshot | null, next: Snapshot): Finish[] {
  if (!previous) return [];
  const before = new Map(previous.states.map((s) => [s.seat_id, s]));
  return next.states
    .filter((state) => {
      const old = before.get(state.seat_id);
      return state.status === "done" && old && old.status !== "done";
    })
    .map((state) => ({
      seatId: state.seat_id,
      at: Math.min(Date.parse(state.updated_at) || Date.now(), Date.now()),
    }));
}

export default function LiveConnected({
  personObservationsEnabled = false,
  reviewsEnabled = false,
  reviewActionsEnabled = false,
  teacherLoginEnabled = false,
  simulatedNamesEnabled = false,
}: {
  personObservationsEnabled?: boolean;
  reviewsEnabled?: boolean;
  reviewActionsEnabled?: boolean;
  teacherLoginEnabled?: boolean;
  simulatedNamesEnabled?: boolean;
}) {
  // Clock values are set after mount, so the server and first render agree.
  const [openedAt, setOpenedAt] = useState<number | null>(null);
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    const tick = () => setNow(Date.now());
    const first = window.setTimeout(() => {
      setOpenedAt(Date.now());
      tick();
    }, 0);
    const timer = window.setInterval(tick, 1000);
    return () => {
      window.clearTimeout(first);
      window.clearInterval(timer);
    };
  }, []);

  const [client] = useState(() => {
    try {
      // Keep the teacher's sign-in, as the dashboard does: reviews are only
      // readable by the signed-in teacher who owns the session.
      return createDashboardClient(teacherLoginEnabled || reviewActionsEnabled);
    } catch {
      return null;
    }
  });
  const [live, setLive] = useState<Live>({
    feed: INITIAL_FEED,
    finishes: [],
  });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!client) return;
    const subscription = watchDashboard(
      client,
      (state) =>
        setLive((previous) => {
          const snapshot = state.snapshot ?? previous.feed.snapshot;
          const finishes =
            state.snapshot && state.snapshot !== previous.feed.snapshot
              ? [
                  ...previous.finishes,
                  ...newFinishes(previous.feed.snapshot, state.snapshot),
                ]
              : previous.finishes;
          return {
            feed: { ...state, snapshot },
            finishes,
          };
        }),
      personObservationsEnabled,
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
  }, [attempt, client, personObservationsEnabled]);

  const [reviews, setReviews] = useState<ReviewFeedState>(
    reviewsEnabled ? INITIAL_REVIEWS : DISABLED_REVIEWS,
  );
  const [reviewAttempt, setReviewAttempt] = useState(0);
  useEffect(() => {
    if (!client) return;
    const subscription = watchTeacherReviews(
      client,
      setReviews,
      reviewsEnabled,
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
  }, [client, reviewsEnabled, reviewAttempt]);

  // The teacher's decision on a model review, as on the dashboard (PRD §13):
  // Support needed saves it as confirmed, No support needed as dismissed,
  // through the review action when that is enabled. Decisions are keyed by the review and
  // its seat, never by a display name. A task-progress flag without a review
  // has no model call to decide on, so it gets no buttons.
  type Decision = "confirmed" | "dismissed";
  const [decisions, setDecisions] = useState<
    {
      reviewId: string;
      seatId: string;
      decision: Decision;
      saved: boolean;
      at: number;
    }[]
  >([]);
  const [shown, setShown] = useState<string | null>(null);
  const [saving, setSaving] = useState<Decision | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const { feed, finishes } = live;
  const options: ObservationOptions = {
    enabled: personObservationsEnabled,
    now,
    connected: feed.connection === "connected" && !feed.error,
  };
  const seats = feed.snapshot
    ? seatViews(feed.snapshot).map((seat) => ({
        ...seat,
        display_name: displayName(seat, simulatedNamesEnabled),
      }))
    : [];
  const nameOf = (seatId: string) =>
    seats.find((seat) => seat.id === seatId)?.display_name ?? seatId;
  const activityOf = (id: string) =>
    activityLabel(id, feed.snapshot?.activities.find((a) => a.id === id)?.name);
  const inView = seats.filter((seat) => inCameraView(seat.state, options));
  const cameraReporting = seats.some((seat) => isFresh(seat.state, options));
  const decidedSeat = (seatId: string) =>
    decisions.findLast((item) => item.seatId === seatId);
  const queue = (reviews.reviews ?? []).filter(
    (review) => !decisions.some((item) => item.reviewId === review.id),
  );
  const groups = groupReviewsBySeat(queue);
  const flagged = inView.filter(
    (seat) =>
      observationPresentation(seat.state, options).needsReview &&
      !groups.some((group) => group.seat_id === seat.id),
  );
  const next = nextUp({
    reviews: groups.map((group) => ({
      name: nameOf(group.seat_id),
      activity: activityOf(group.reviews[0].activity_id),
      count: group.reviews.length,
      elevated: group.elevated,
    })),
    flagged: flagged.map((seat) => ({
      name: seat.display_name,
      activity: seat.activity,
    })),
    inView: inView.length,
    cameraReporting,
  });

  const statusOf = (seat: (typeof seats)[number]): [LiveStatus, string] => {
    const presentation = observationPresentation(seat.state, options);
    if (groups.some((group) => group.seat_id === seat.id))
      return ["needs", "Review waiting"];
    if (decidedSeat(seat.id)?.decision === "confirmed")
      return ["checking", resolutionLabels.confirmed];
    if (presentation.needsReview) return ["needs", "Needs you"];
    if (presentation.currentStatus === "done") return ["finished", "Finished"];
    if (presentation.currentStatus === "in_progress")
      return ["working", "Working"];
    if (presentation.currentStatus === "idle") return ["ready", "Ready"];
    return ["quiet", presentation.label];
  };
  const students: LiveStudent[] = inView.map((seat, index) => {
    const [status, label] = statusOf(seat);
    return {
      id: seat.id,
      name: seat.display_name,
      status,
      label,
      details: [
        observationPresentation(seat.state, options).detail,
        `${seat.activity} · position ${index + 1} from the left`,
      ],
    };
  });

  const doneNow = students.filter((s) => s.status === "finished").length;
  const working = students.filter(
    (s) => s.status === "working" || s.status === "checking",
  ).length;
  // Everyone still waiting on your answer.
  const waiting = new Set([
    ...groups.map((group) => nameOf(group.seat_id)),
    ...flagged.map((seat) => seat.display_name),
  ]).size;
  const counts = new Map<string, number>();
  for (const seat of inView)
    counts.set(seat.activity, (counts.get(seat.activity) ?? 0) + 1);
  const activity =
    [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? "Live";
  const simulated =
    seats.length > 0 && seats.every((seat) => seat.is_simulated);

  const start = openedAt ?? 0;

  const items = [
    ...finishes.map((item) => ({
      id: `finish-${item.seatId}-${item.at}`,
      text: `${nameOf(item.seatId)} finished`,
      at: item.at,
    })),
    ...queue
      .map((review) => ({
        id: `review-${review.id}`,
        text: `${nameOf(review.seat_id)} flagged for review`,
        at: Date.parse(review.created_at),
      }))
      .filter((item) => item.at >= start),
    ...decisions.map((item) => ({
      id: `decided-${item.reviewId}`,
      text: `${nameOf(item.seatId)}: ${resolutionLabels[item.decision].toLowerCase()}`,
      at: item.at,
    })),
  ]
    .filter((item) => Number.isFinite(item.at))
    .sort((a, b) => b.at - a.at)
    .slice(0, 6)
    .map((item) => ({
      id: item.id,
      text: item.text,
      time: clockTime(item.at),
      dateTime: new Date(item.at).toISOString(),
    }));

  // The card shows exactly what the model returned for the lead review.
  const leadGroup = groups[0];
  const lead = leadGroup?.reviews[0];
  const decide = async (decision: Decision) => {
    if (!lead) return;
    setActionError(null);
    let saved = false;
    if (reviewActionsEnabled && client) {
      setSaving(decision);
      try {
        await resolveTeacherReview(client, lead, decision);
        saved = true;
      } catch (error) {
        setActionError(
          error instanceof Error ? error.message : "Could not save.",
        );
        setSaving(null);
        return;
      }
      setSaving(null);
    }
    setDecisions((list) => [
      ...list,
      {
        reviewId: lead.id,
        seatId: lead.seat_id,
        decision,
        saved,
        at: Date.now(),
      },
    ]);
    setShown(lead.id);
  };
  const last = decisions.find((item) => item.reviewId === shown);

  let card;
  if (!client)
    card = (
      <>
        <p className="live-card-title">Live data isn’t set up</p>
        <p className="live-card-note">
          This environment has no Supabase connection, so no one can be shown.
        </p>
      </>
    );
  else if (last)
    card = (
      <>
        <p className="live-card-title">
          {`${nameOf(last.seatId)}: ${resolutionLabels[last.decision].toLowerCase()}`}
        </p>
        <p className="live-card-note">
          {last.saved
            ? "Saved to the review queue."
            : "Not saved: review actions are off here, so this is noted on this screen only."}
        </p>
        <div className="live-card-actions">
          <button
            type="button"
            className="live-btn"
            onClick={() => setShown(null)}
          >
            {lead ? `Next review: ${nameOf(lead.seat_id)}` : "Done"}
          </button>
        </div>
      </>
    );
  else if (lead && leadGroup)
    card = (
      <>
        <div className="live-card-who">
          <span className="live-avatar is-needs" aria-hidden="true">
            {nameOf(lead.seat_id).slice(0, 1)}
          </span>
          <div>
            <p className="live-card-title">
              {nameOf(lead.seat_id)} may need support
            </p>
            <p className="live-card-note">
              {activityOf(lead.activity_id)} ·{" "}
              {clockTime(Date.parse(lead.created_at))}
              {lead.priority === "elevated"
                ? ` · ${priorityLabels.elevated}`
                : ""}
              {leadGroup.reviews.length > 1
                ? ` · ${leadGroup.reviews.length} reviews waiting`
                : ""}
            </p>
          </div>
        </div>
        <p className="live-card-rationale">{reviewPrompt.detail}</p>
        <p className="live-card-note">
          Cues: {teacherRationale(lead.rationale)}
          {lead.evidence_used.length
            ? ` Based on ${lead.evidence_used
                .map((source) => evidenceLabels[source].toLowerCase())
                .join(", ")}.`
            : ""}
        </p>
        <div className="live-card-actions">
          <button
            type="button"
            className="live-btn is-primary"
            disabled={saving !== null}
            onClick={() => void decide("confirmed")}
          >
            {saving === "confirmed" ? "Saving…" : resolutionLabels.confirmed}
          </button>
          <button
            type="button"
            className="live-btn"
            disabled={saving !== null}
            onClick={() => void decide("dismissed")}
          >
            {saving === "dismissed" ? "Saving…" : resolutionLabels.dismissed}
          </button>
        </div>
        {actionError ? (
          <p className="live-card-error" role="alert">
            {actionError}
          </p>
        ) : null}
      </>
    );
  else if (reviews.error)
    card = (
      <>
        <p className="live-card-title">Reviews aren’t available</p>
        <p className="live-card-note">{reviews.error}</p>
      </>
    );
  else if (flagged.length)
    card = (
      <>
        <p className="live-card-title">
          Task progress flagged{" "}
          {flagged.map((seat) => seat.display_name).join(", ")}
        </p>
        <p className="live-card-note">
          No review from Cues yet. A review appears here when the agent requests
          one.
        </p>
      </>
    );
  else
    card = (
      <>
        <p className="live-card-title">
          {!inView.length ? "No one in view" : "Everyone’s working"}
        </p>
        <p className="live-card-note">
          {next.kind === "calm" ? next.message : "Nothing needs you right now."}
        </p>
      </>
    );

  const summary = feed.error ? (
    <span className="live-up">{feed.error}</span>
  ) : (
    <>
      {waiting ? (
        <span className="live-up">
          {waiting} need{waiting === 1 ? "s" : ""} you
        </span>
      ) : (
        <span>No one waiting</span>
      )}
      <span>
        {" "}
        · {working} working
        {openedAt === null ? "" : ` · since ${clockTime(openedAt)}`}
      </span>
    </>
  );

  return (
    <div className="live">
      <div className="live-main-col">
        <LiveHero
          activity={activity}
          simulated={simulated}
          count={feed.snapshot ? doneNow : "—"}
          total={inView.length || null}
          noun="finished"
          summary={summary}
        />
        <LiveCard>{card}</LiveCard>
        <LiveFeed
          title={
            openedAt === null
              ? "Since you opened this"
              : `Since ${clockTime(openedAt)}`
          }
          items={items}
          empty="Nothing has happened since you opened this page."
        />
      </div>
      <LiveClass
        students={students}
        empty={
          !client || feed.error
            ? "Seat data is unavailable."
            : feed.loading && !feed.snapshot
              ? "Loading…"
              : cameraReporting
                ? "No one is in view right now."
                : "The camera is off. People appear here when the station camera sees them."
        }
        action={<LiveCameraLink />}
      />
    </div>
  );
}
