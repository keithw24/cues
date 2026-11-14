"use client";

import { useEffect, useRef, useState } from "react";
import { seatViews, type SeatView } from "@/lib/dashboard";
import {
  INITIAL_REVIEWS,
  DISABLED_REVIEWS,
  watchTeacherReviews,
  type ReviewFeedState,
} from "@/lib/teacher-review-feed";
import { activityLabel, priorityLabels } from "@/lib/teacher-reviews";
import { ProgressContext } from "@/components/progress-context";
import { TeacherReviewDetails } from "@/components/teacher-review-details";
import { watchDashboard, type FeedState } from "@/lib/dashboard-feed";
import { createDashboardClient } from "@/lib/supabase";
import { Card } from "@/components/ui/card";
import { TeacherReviewActions } from "@/components/teacher-review-actions";
import { SessionControls } from "@/components/session-controls";
import LocalClassroomFeed from "@/components/local-classroom-feed";
import {
  observationPresentation,
  type ObservationOptions,
} from "@/lib/observation-presentation";
import { WorkspaceSidebar } from "@/components/workspace-sidebar";
import { WorkspaceIcon } from "@/components/workspace-icon";

const INITIAL: FeedState = {
  snapshot: null,
  connection: "connecting",
  loading: true,
  error: null,
};
const observationTime = (value: string) =>
  new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));

function SeatDetails({
  seat,
  close,
  headingRef,
  observationOptions,
}: {
  observationOptions?: ObservationOptions;
  seat: SeatView;
  close: () => void;
  headingRef: React.RefObject<HTMLHeadingElement | null>;
}) {
  const presentation = observationPresentation(seat.state, observationOptions);
  return (
    <section
      className="seat-details"
      aria-labelledby="detail-heading"
      onKeyDown={(event) => {
        if (event.key === "Escape") close();
      }}
    >
      <header className="panel-heading">
        <h2 id="detail-heading" ref={headingRef} tabIndex={-1}>
          {seat.display_name}
        </h2>
        <button className="text-button" onClick={close} type="button">
          Close details
        </button>
      </header>
      <div className="detail-body">
        <p
          className={`detail-status ${presentation.needsReview ? "needs-review" : ""}`}
        >
          {presentation.label}
        </p>
        <p className="detail-description">{presentation.detail}</p>
        <dl className="detail-facts">
          <div>
            <dt>Current activity</dt>
            <dd>{seat.activity}</dd>
          </div>
          <div>
            <dt>Match score</dt>
            <dd>
              {presentation.score == null
                ? "Unavailable"
                : presentation.score.toFixed(2)}
            </dd>
          </div>
          <div>
            <dt>Last observation</dt>
            <dd>
              {seat.state ? (
                <time dateTime={seat.state.updated_at}>
                  {observationTime(seat.state.updated_at)}
                </time>
              ) : (
                "No observation yet"
              )}
            </dd>
          </div>
        </dl>
        {seat.is_simulated ? (
          <p className="detail-simulation">Simulated seat · {seat.id}</p>
        ) : null}
        <ProgressContext
          observation={seat.state}
          scope={seat.state ?? undefined}
          observationOptions={observationOptions}
        />
        <section className="detail-section">
          <h3>Agent assessment</h3>
          <p>Pending assessments are listed in Teacher reviews.</p>
        </section>
        <p className="detail-footnote">
          Match scores describe gesture similarity, not probabilities.
        </p>
      </div>
    </section>
  );
}

export default function Dashboard({
  personObservationsEnabled = false,
  sessionControlsEnabled = false,
  stationId = "",
  reviewsEnabled = false,
  reviewActionsEnabled = false,
  teacherLoginEnabled = false,
}: {
  personObservationsEnabled?: boolean;
  sessionControlsEnabled?: boolean;
  stationId?: string;
  reviewsEnabled?: boolean;
  reviewActionsEnabled?: boolean;
  teacherLoginEnabled?: boolean;
}) {
  const [observationNow, setObservationNow] = useState<number | null>(null);
  useEffect(() => {
    if (!personObservationsEnabled) return;
    const tick = () => setObservationNow(Date.now());
    const initial = setTimeout(tick, 0);
    const timer = setInterval(tick, 1000);
    const visible = () => {
      if (!document.hidden) tick();
    };
    document.addEventListener("visibilitychange", visible);
    return () => {
      clearTimeout(initial);
      clearInterval(timer);
      document.removeEventListener("visibilitychange", visible);
    };
  }, [personObservationsEnabled]);
  const [sessionActivity, setSessionActivity] = useState("Session unavailable");
  const [feed, setFeed] = useState<FeedState>(INITIAL);
  const [attempt, setAttempt] = useState(0);
  const [selectedReviewId, setSelectedReviewId] = useState<string | null>(null);
  const attentionHeading = useRef<HTMLHeadingElement>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [reviews, setReviews] = useState<ReviewFeedState>(
    reviewsEnabled ? INITIAL_REVIEWS : DISABLED_REVIEWS,
  );
  const resolvedReviewIds = useRef(new Set<string>());
  const [reviewAttempt, setReviewAttempt] = useState(0);
  const detailsHeading = useRef<HTMLHeadingElement>(null);
  const detailOpener = useRef<HTMLButtonElement | null>(null);
  const seatButtons = useRef(new Map<string, HTMLButtonElement>());
  const [client] = useState(() => {
    try {
      return createDashboardClient(
        sessionControlsEnabled || teacherLoginEnabled,
      );
    } catch {
      return null;
    }
  });
  const configurationError = client === null;
  useEffect(() => {
    if (!client) return;
    const subscription = watchDashboard(
      client,
      (state) => {
        if (personObservationsEnabled)
          setFeed((previous) => ({
            ...state,
            snapshot: state.snapshot ?? previous.snapshot,
          }));
        else setFeed(state);
      },
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
  useEffect(() => {
    if (selectedId || selectedReviewId) detailsHeading.current?.focus();
  }, [selectedId, selectedReviewId]);

  const seats = feed.snapshot ? seatViews(feed.snapshot) : [];
  const observationOptions: ObservationOptions = {
    enabled: personObservationsEnabled,
    now: observationNow,
    connected: feed.connection === "connected" && !feed.error,
  };
  const selected = seats.find((seat) => seat.id === selectedId);
  const hasCurrentTaskObservations =
    !personObservationsEnabled ||
    seats.some(
      (seat) =>
        observationPresentation(seat.state, observationOptions)
          .currentStatus !== null,
    );
  const queue = reviews.reviews ?? [];
  const selectedReview = queue.find((item) => item.id === selectedReviewId);
  const activityNames = [
    ...new Set(
      seats
        .filter((seat) => seat.state?.activity_id)
        .map((seat) => seat.activity),
    ),
  ];
  const observationActivity = !feed.snapshot
    ? "Activity unavailable"
    : activityNames.length > 1
      ? "Multiple activities"
      : (activityNames[0] ?? "No activity assigned");
  const activity = sessionControlsEnabled
    ? sessionActivity
    : observationActivity;
  const selectSeat = (seat: SeatView, opener: HTMLButtonElement) => {
    detailOpener.current = opener;
    setSelectedReviewId(null);
    setSelectedId(seat.id);
  };
  const closeReview = () => {
    setSelectedReviewId(null);
    requestAnimationFrame(() => {
      const opener = document.getElementById(`review-${selectedReviewId}`);
      if (opener instanceof HTMLButtonElement) opener.focus();
      else attentionHeading.current?.focus();
    });
  };
  const closeDetails = () => {
    setSelectedId(null);
    const opener = detailOpener.current;
    if (opener?.isConnected) opener.focus();
    else if (selectedId) seatButtons.current.get(selectedId)?.focus();
  };

  return (
    <div className="dashboard-shell">
      <WorkspaceSidebar
        accountEnabled={teacherLoginEnabled}
        onReviews={() => {
          setSelectedId(null);
          setSelectedReviewId(null);
        }}
      />
      <main id="main-content" className="dashboard-main">
        <div className="page-breadcrumb">
          Workspace <span>/</span> Classroom
        </div>
        <header className="page-intro">
          <div>
            <h1>Your classroom.</h1>
            <p>A clear view of who’s ready and who needs a hand.</p>
          </div>
          <button
            className="refresh-button"
            type="button"
            onClick={() => {
              setAttempt((n) => n + 1);
              setReviewAttempt((n) => n + 1);
            }}
            disabled={!client || feed.loading}
          >
            <WorkspaceIcon name="refresh" />
            {feed.loading && client ? "Refreshing…" : "Refresh"}
          </button>
        </header>
        <section className="classroom-summary" aria-label="Classroom summary">
          <dl className="overview-metrics">
            <div>
              <dd>
                {feed.snapshot
                  ? seats.filter((seat) => seat.state).length
                  : "—"}
              </dd>
              <dt>People observed</dt>
            </div>
            <div>
              <dd>
                {feed.snapshot && hasCurrentTaskObservations
                  ? seats.filter(
                      (seat) =>
                        observationPresentation(seat.state, observationOptions)
                          .currentStatus === "in_progress",
                    ).length
                  : "—"}
              </dd>
              <dt>In progress</dt>
            </div>
            <div>
              <dd>
                {feed.snapshot && hasCurrentTaskObservations
                  ? seats.filter(
                      (seat) =>
                        observationPresentation(seat.state, observationOptions)
                          .currentStatus === "done",
                    ).length
                  : "—"}
              </dd>
              <dt>Completed</dt>
            </div>
            <div>
              <dd>
                {reviews.reviews &&
                !reviews.error &&
                reviews.connection === "connected"
                  ? queue.length
                  : "—"}
              </dd>
              <dt>Pending reviews</dt>
            </div>
          </dl>
        </section>
        <div className="workspace-toolbar">
          <div className="current-activity">
            <span className="toolbar-label">Current activity</span>
            <strong>{activity}</strong>
          </div>
          <details className="activity-popover">
            <summary>
              Manage activity{" "}
              <svg
                viewBox="0 0 16 16"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                aria-hidden="true"
              >
                <path d="m4 6 4 4 4-4" />
              </svg>
            </summary>
            <div className="activity-popover-body">
              <h2>Session controls</h2>
              {sessionControlsEnabled && client ? (
                <SessionControls
                  client={client}
                  station={stationId}
                  onActivity={setSessionActivity}
                  teacherLoginEnabled={teacherLoginEnabled}
                />
              ) : (
                <p>Session controls are not connected in this environment.</p>
              )}
            </div>
          </details>
          {seats.length > 0 && seats.every((seat) => seat.is_simulated) ? (
            <span className="status-chip">Simulated data</span>
          ) : null}
        </div>
        {configurationError ||
        feed.error ||
        feed.connection === "disconnected" ? (
          <section className="notice" role="alert">
            <div>
              <h2>
                {configurationError
                  ? "Seat updates are not configured"
                  : feed.error
                    ? "Seat data could not be refreshed"
                    : "Seat updates are disconnected"}
              </h2>
              <p>
                {configurationError
                  ? "Connect this dashboard to the classroom data source."
                  : feed.snapshot
                    ? "Showing the last loaded observations. Recent changes may be missing."
                    : "Check your connection and try again."}
              </p>
            </div>
            {!configurationError ? (
              <button
                type="button"
                disabled={feed.loading}
                onClick={() => setAttempt((n) => n + 1)}
              >
                Reconnect updates
              </button>
            ) : null}
          </section>
        ) : null}
        <div className="monitor-workspace">
          <div className="monitor-main">
            <LocalClassroomFeed activity={activity} />
            <section className="seat-strip" aria-labelledby="seats-heading">
              <header className="strip-heading">
                <h2 id="seats-heading">People</h2>
              </header>
              {!feed.snapshot ? (
                <p className="strip-empty" role="status">
                  {feed.loading && !configurationError
                    ? "Loading observations…"
                    : "Seat observations unavailable"}
                </p>
              ) : seats.length === 0 ? (
                <p className="strip-empty">No people observed yet.</p>
              ) : (
                <div className="seat-items">
                  {seats.map((seat) => {
                    const presentation = observationPresentation(
                      seat.state,
                      observationOptions,
                    );
                    return (
                      <button
                        className={`seat-item ${presentation.needsReview ? "needs-review" : ""} ${selected?.id === seat.id ? "is-selected" : ""}`}
                        key={seat.id}
                        ref={(node) => {
                          if (node) seatButtons.current.set(seat.id, node);
                          else seatButtons.current.delete(seat.id);
                        }}
                        type="button"
                        aria-pressed={selected?.id === seat.id}
                        onClick={(event) =>
                          selectSeat(seat, event.currentTarget)
                        }
                      >
                        <span className="seat-item-name">
                          {seat.display_name}
                        </span>
                        <span className="seat-item-status">
                          {presentation.label}
                        </span>
                        <span className="seat-item-activity">
                          {seat.activity}
                        </span>
                        {personObservationsEnabled &&
                        presentation.unavailable &&
                        seat.state ? (
                          <time
                            className="seat-item-time"
                            dateTime={seat.state.updated_at}
                          >
                            Last observed{" "}
                            {observationTime(seat.state.updated_at)}
                          </time>
                        ) : null}
                        {seat.is_simulated ? (
                          <span className="sim-badge">SIM</span>
                        ) : null}
                      </button>
                    );
                  })}
                </div>
              )}
            </section>
          </div>
          <Card
            role="complementary"
            className="attention-panel"
            id="attention-panel"
            aria-label={
              selectedReviewId
                ? "Review details"
                : selected
                  ? "Seat details"
                  : "Teacher reviews"
            }
          >
            {selectedReviewId ? (
              <TeacherReviewDetails
                review={selectedReview}
                observationOptions={observationOptions}
                seats={seats}
                activities={feed.snapshot?.activities ?? []}
                stale={!!reviews.error || reviews.connection === "disconnected"}
                close={closeReview}
                headingRef={detailsHeading}
              >
                {reviewActionsEnabled && client && selectedReview ? (
                  <TeacherReviewActions
                    key={selectedReviewId}
                    client={client}
                    review={selectedReview}
                    onResolved={(resolved) => {
                      resolvedReviewIds.current.add(resolved.id);
                      setReviews((state) => ({
                        ...state,
                        reviews:
                          state.reviews?.filter(
                            (item) => item.id !== resolved.id,
                          ) ?? null,
                      }));
                    }}
                  />
                ) : null}
              </TeacherReviewDetails>
            ) : selected ? (
              <SeatDetails
                seat={selected}
                observationOptions={observationOptions}
                close={closeDetails}
                headingRef={detailsHeading}
              />
            ) : (
              <section aria-labelledby="attention-heading">
                <header className="panel-heading">
                  <h2
                    id="attention-heading"
                    ref={attentionHeading}
                    tabIndex={-1}
                  >
                    Teacher reviews
                  </h2>
                  <span
                    className={
                      queue.length
                        ? "attention-count has-items"
                        : "attention-count"
                    }
                  >
                    {reviews.reviews &&
                    !reviews.error &&
                    reviews.connection === "connected"
                      ? queue.length
                      : "—"}
                  </span>
                </header>
                {!reviewsEnabled || configurationError ? (
                  <div className="queue-empty">
                    <p>Teacher reviews not connected</p>
                    <span>
                      Pending reviews will appear here when the review data
                      source is available.
                    </span>
                  </div>
                ) : (
                  <>
                    {reviews.error || reviews.connection === "disconnected" ? (
                      <div className="review-feed-notice" role="alert">
                        <p>
                          {reviews.error ??
                            "Live review updates are disconnected."}
                        </p>
                        {reviews.reviews ? (
                          <p>
                            Showing the last loaded reviews. Resolved items may
                            still appear.
                          </p>
                        ) : null}
                        <button
                          type="button"
                          disabled={reviews.loading}
                          onClick={() => setReviewAttempt((n) => n + 1)}
                        >
                          Retry reviews
                        </button>
                      </div>
                    ) : null}
                    {queue.length ? (
                      <ul className="attention-list">
                        {queue.map((review) => (
                          <li key={review.id}>
                            <button
                              type="button"
                              className="review-entry"
                              id={`review-${review.id}`}
                              onClick={() => {
                                setSelectedId(null);
                                setSelectedReviewId(review.id);
                              }}
                            >
                              <span className="attention-item-heading">
                                <span className="review-person">
                                  {seats.find(
                                    (seat) => seat.id === review.seat_id,
                                  )?.display_name ?? review.seat_id}
                                </span>
                                <span
                                  className={`review-label ${review.priority === "elevated" ? "is-elevated" : ""}`}
                                >
                                  {priorityLabels[review.priority]}
                                </span>
                                <svg
                                  className="review-chevron"
                                  viewBox="0 0 16 16"
                                  fill="none"
                                  stroke="currentColor"
                                  strokeWidth="1.5"
                                  aria-hidden="true"
                                >
                                  <path d="m6 4 4 4-4 4" />
                                </svg>
                              </span>
                              <span className="review-metadata">
                                <span>
                                  {activityLabel(
                                    review.activity_id,
                                    feed.snapshot?.activities.find(
                                      (item) => item.id === review.activity_id,
                                    )?.name,
                                  )}
                                </span>
                                <time dateTime={review.created_at}>
                                  {new Intl.DateTimeFormat(undefined, {
                                    month: "short",
                                    day: "numeric",
                                    hour: "numeric",
                                    minute: "2-digit",
                                  }).format(new Date(review.created_at))}
                                </time>
                              </span>
                              <span className="sr-only">View review</span>
                            </button>
                          </li>
                        ))}
                      </ul>
                    ) : !reviews.error &&
                      reviews.connection !== "disconnected" ? (
                      <div className="queue-empty" role="status">
                        <p>
                          {reviews.reviews === null
                            ? "Loading teacher reviews…"
                            : "No pending teacher reviews"}
                        </p>
                        <span>
                          {reviews.reviews === null
                            ? "Checking the review queue."
                            : "New pending reviews will appear here automatically."}
                        </span>
                      </div>
                    ) : null}
                  </>
                )}
              </section>
            )}
          </Card>
        </div>
        <footer className="workspace-footer">
          <span>
            Student camera images and video stay on the station laptop.
          </span>
          <span>
            {sessionControlsEnabled
              ? "Session controls use saved station state."
              : "Session controls are not connected."}
          </span>
        </footer>
      </main>
    </div>
  );
}
