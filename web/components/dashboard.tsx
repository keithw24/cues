"use client";

import { useEffect, useRef, useState } from "react";
import { seatViews, type SeatView } from "@/lib/dashboard";
import {
  INITIAL_REVIEWS,
  DISABLED_REVIEWS,
  watchTeacherReviews,
  type ReviewFeedState,
} from "@/lib/teacher-review-feed";
import { activityLabel, groupReviewsBySeat } from "@/lib/teacher-reviews";
import { ProgressContext } from "@/components/progress-context";
import { TeacherReviewDetails } from "@/components/teacher-review-details";
import { watchDashboard, type FeedState } from "@/lib/dashboard-feed";
import { createDashboardClient } from "@/lib/supabase";
import { Card } from "@/components/ui/card";
import { TeacherReviewActions } from "@/components/teacher-review-actions";
import { SessionControls } from "@/components/session-controls";
import LocalClassroomFeed from "@/components/local-classroom-feed";
import {
  inCameraView,
  isFresh,
  observationPresentation,
  type ObservationOptions,
} from "@/lib/observation-presentation";
import { WorkspaceSidebar } from "@/components/workspace-sidebar";
import { WorkspaceIcon } from "@/components/workspace-icon";
import { ClassroomRoom, type RoomPerson } from "@/components/classroom-room";
import { NextUpCard } from "@/components/next-up";
import { LessonTimeline } from "@/components/lesson-timeline";
import { nextUp } from "@/lib/next-up";
import {
  PersonRowContent,
  ReviewRowContent,
} from "@/components/workspace-rows";
import { displayName } from "@/lib/simulated-names";

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
type Presentation = ReturnType<typeof observationPresentation>;
const statusTone = (presentation: Presentation): RoomPerson["tone"] =>
  presentation.needsReview
    ? "review"
    : presentation.currentStatus === "done"
      ? "done"
      : presentation.currentStatus === "in_progress"
        ? "working"
        : "quiet";
const statusIcon = (presentation: Presentation) =>
  presentation.needsReview
    ? "flag"
    : presentation.currentStatus === "done"
      ? "check"
      : presentation.currentStatus === "in_progress"
        ? "working"
        : presentation.currentStatus === "tracking_lost" ||
            presentation.label.startsWith("Tracking")
          ? "hidden"
          : presentation.unavailable
            ? "paused"
            : "time";

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
          <div>
            <dt>Person / activity ID</dt>
            <dd>
              {seat.id} / {seat.state?.activity_id ?? "None"}
            </dd>
          </div>
          <div>
            <dt>Tracking valid</dt>
            <dd>
              {seat.state?.tracking_valid == null
                ? "Unknown"
                : seat.state.tracking_valid
                  ? "Yes"
                  : "Tracking unavailable"}
            </dd>
          </div>
          <div>
            <dt>Supporting expression context</dt>
            <dd>
              {seat.state?.expression_context
                ? `${seat.state.expression_context.label}: ${seat.state.expression_context.probability.toFixed(2)} (model output only)`
                : "Unavailable"}
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
  simulatedNamesEnabled = false,
  roomViewEnabled = false,
  themeToggleEnabled = false,
  liveViewEnabled = false,
}: {
  personObservationsEnabled?: boolean;
  sessionControlsEnabled?: boolean;
  stationId?: string;
  reviewsEnabled?: boolean;
  reviewActionsEnabled?: boolean;
  teacherLoginEnabled?: boolean;
  simulatedNamesEnabled?: boolean;
  roomViewEnabled?: boolean;
  themeToggleEnabled?: boolean;
  liveViewEnabled?: boolean;
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
  const [drawerOpen, setDrawerOpen] = useState(false);
  const drawerToggle = useRef<HTMLButtonElement>(null);
  const drawerClose = useRef<HTMLButtonElement>(null);
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
        sessionControlsEnabled || teacherLoginEnabled || reviewActionsEnabled,
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

  const seats = feed.snapshot
    ? seatViews(feed.snapshot).map((seat) => ({
        ...seat,
        display_name: displayName(seat, simulatedNamesEnabled),
      }))
    : [];
  const reviewActivity = (id: string) =>
    activityLabel(
      id,
      feed.snapshot?.activities.find((item) => item.id === id)?.name,
    );
  const reviewName = (seatId: string) =>
    seats.find((seat) => seat.id === seatId)?.display_name ?? seatId;
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
  const reviewGroups = groupReviewsBySeat(queue);
  const countStatus = (status: string) =>
    feed.snapshot && hasCurrentTaskObservations
      ? seats.filter(
          (seat) =>
            observationPresentation(seat.state, observationOptions)
              .currentStatus === status,
        ).length
      : "—";
  // People come from the camera: only those it sees right now are listed.
  const inView = seats.filter((seat) =>
    inCameraView(seat.state, observationOptions),
  );
  const cameraReporting = seats.some((seat) =>
    isFresh(seat.state, observationOptions),
  );
  const peopleCount = feed.snapshot ? inView.length : "—";
  const workingCount = countStatus("in_progress");
  const completedCount = countStatus("done");
  const reviewCount =
    reviews.reviews && !reviews.error && reviews.connection === "connected"
      ? queue.length
      : "—";
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

  const activityPopover = (
    <details className="activity-popover">
      <summary>
        Manage activity
        <WorkspaceIcon name="chevronDown" />
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
  );
  const allSimulated =
    seats.length > 0 && seats.every((seat) => seat.is_simulated);
  const simulatedChip =
    seats.length > 0 && seats.every((seat) => seat.is_simulated) ? (
      <span className="status-chip">Simulated data</span>
    ) : null;
  const roomPeople: RoomPerson[] = inView.map((seat) => {
    const presentation = observationPresentation(
      seat.state,
      observationOptions,
    );
    return {
      id: seat.id,
      name: seat.display_name,
      status: presentation.label,
      tone: statusTone(presentation),
      activity: seat.activity,
      selected: selected?.id === seat.id,
    };
  });
  const next = nextUp({
    reviews: reviewGroups.map((group) => ({
      name: reviewName(group.seat_id),
      activity: reviewActivity(group.reviews[0].activity_id),
      count: group.reviews.length,
      elevated: group.elevated,
    })),
    flagged: inView
      .filter(
        (seat) =>
          observationPresentation(seat.state, observationOptions).needsReview,
      )
      .map((seat) => ({ name: seat.display_name, activity: seat.activity })),
    inView: inView.length,
    cameraReporting,
  });
  const openNext = () => {
    detailOpener.current =
      document.activeElement instanceof HTMLButtonElement
        ? document.activeElement
        : null;
    const lead = reviewGroups[0];
    if (lead) {
      setSelectedId(null);
      setSelectedReviewId(lead.reviews[0].id);
    } else {
      const seat = inView.find(
        (item) =>
          observationPresentation(item.state, observationOptions).needsReview,
      );
      if (!seat) return;
      setSelectedReviewId(null);
      setSelectedId(seat.id);
    }
    setDrawerOpen(true);
  };
  // Closing returns focus to whatever opened the drawer: a person in the room,
  // the next-up card, or the toggle.
  const closeDrawer = () => {
    setDrawerOpen(false);
    setSelectedId(null);
    setSelectedReviewId(null);
    const opener = detailOpener.current;
    requestAnimationFrame(() =>
      (opener?.isConnected ? opener : drawerToggle.current)?.focus(),
    );
  };
  // Details opened from the room or the next-up card close the whole drawer;
  // ones opened from the drawer's own lists go back to those lists.
  const closeInDrawer = (inside: () => void) => {
    if (detailOpener.current?.closest(".room-drawer")) inside();
    else closeDrawer();
  };
  const timelineMarks = queue.map((review) => ({
    id: review.id,
    at: review.created_at,
    label: `${reviewName(review.seat_id)} flagged`,
  }));

  return (
    <div className="dashboard-shell">
      <WorkspaceSidebar
        accountEnabled={teacherLoginEnabled}
        themeToggle={themeToggleEnabled}
        liveView={liveViewEnabled}
        onReviews={() => {
          setSelectedId(null);
          setSelectedReviewId(null);
        }}
      />
      <main id="main-content" className="dashboard-main">
        {roomViewEnabled ? (
          <header className="room-header">
            <div>
              <h1>your classroom</h1>
              <p className="room-subtitle">
                {activity}
                {allSimulated ? " · simulated class" : null}
              </p>
            </div>
            <div className="room-actions">
              {activityPopover}
              <button
                type="button"
                className="room-details-toggle"
                aria-expanded={drawerOpen}
                aria-controls="room-drawer"
                ref={drawerToggle}
                onClick={() => {
                  detailOpener.current = drawerToggle.current;
                  setDrawerOpen(true);
                  requestAnimationFrame(() => drawerClose.current?.focus());
                }}
              >
                <WorkspaceIcon name="camera" />
                Camera and details
              </button>
            </div>
          </header>
        ) : (
          <>
            <div className="ws-hero">
              <span className="ws-grain" aria-hidden="true" />
              <header className="page-intro">
                <div>
                  <p className="page-breadcrumb">
                    Workspace <span>/</span> Classroom
                  </p>
                  <h1>your classroom</h1>
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
              <section
                className="classroom-summary"
                aria-label="Classroom summary"
              >
                <dl className="overview-metrics">
                  <div>
                    <dd>{peopleCount}</dd>
                    <dt>People in view</dt>
                  </div>
                  <div>
                    <dd>{workingCount}</dd>
                    <dt>In progress</dt>
                  </div>
                  <div>
                    <dd>{completedCount}</dd>
                    <dt>Completed</dt>
                  </div>
                  <div>
                    <dd>{reviewCount}</dd>
                    <dt>Pending reviews</dt>
                  </div>
                </dl>
              </section>
            </div>
            <div className="workspace-toolbar">
              <div className="current-activity">
                <span className="toolbar-label">Current activity</span>
                <strong>{activity}</strong>
              </div>
              {activityPopover}
              {simulatedChip}
            </div>
          </>
        )}
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
        {roomViewEnabled ? (
          <>
            <div className="room-layout">
              <ClassroomRoom
                people={roomPeople}
                emptyMessage={
                  !feed.snapshot
                    ? "Loading the room…"
                    : cameraReporting
                      ? "No one is in view right now."
                      : "The camera is off. People appear here when the station camera sees them."
                }
                onSelect={(id, opener) => {
                  const seat = seats.find((item) => item.id === id);
                  if (!seat) return;
                  selectSeat(seat, opener);
                  setDrawerOpen(true);
                }}
              />
              <NextUpCard
                next={next}
                summary={
                  typeof peopleCount === "number" &&
                  typeof workingCount === "number" &&
                  typeof completedCount === "number"
                    ? `${peopleCount} in view · ${workingCount} working · ${completedCount} finished`
                    : undefined
                }
                onOpen={openNext}
              />
            </div>
            <LessonTimeline marks={timelineMarks} />
            <div
              id="room-drawer"
              className="room-drawer"
              data-open={drawerOpen || undefined}
              inert={!drawerOpen}
              onKeyDown={(event) => {
                if (event.key === "Escape" && !selectedId && !selectedReviewId)
                  closeDrawer();
              }}
            >
              <div className="room-drawer-head">
                <h2>Camera and details</h2>
                <button
                  type="button"
                  className="text-button"
                  ref={drawerClose}
                  onClick={closeDrawer}
                >
                  Close
                </button>
              </div>
              <div className="monitor-workspace">
                <div className="monitor-main">
                  <LocalClassroomFeed activity={activity} />
                  <section
                    className="seat-strip people-card"
                    aria-labelledby="seats-heading"
                  >
                    <header className="strip-heading">
                      <h2 id="seats-heading">People</h2>
                    </header>
                    {!feed.snapshot ? (
                      <p className="strip-empty" role="status">
                        {feed.loading && !configurationError
                          ? "Loading observations…"
                          : "Seat observations unavailable"}
                      </p>
                    ) : inView.length === 0 ? (
                      <p className="strip-empty" role="status">
                        {cameraReporting
                          ? "No one is in view right now."
                          : "The camera is off. People appear here when the station camera sees them."}
                      </p>
                    ) : (
                      <div className="seat-items">
                        {inView.map((seat) => {
                          const presentation = observationPresentation(
                            seat.state,
                            observationOptions,
                          );
                          return (
                            <button
                              className={`seat-item is-${statusTone(presentation)} ${presentation.needsReview ? "needs-review" : ""} ${selected?.id === seat.id ? "is-selected" : ""}`}
                              key={seat.id}
                              ref={(node) => {
                                if (node)
                                  seatButtons.current.set(seat.id, node);
                                else seatButtons.current.delete(seat.id);
                              }}
                              type="button"
                              aria-pressed={selected?.id === seat.id}
                              onClick={(event) =>
                                selectSeat(seat, event.currentTarget)
                              }
                            >
                              <PersonRowContent
                                name={seat.display_name}
                                status={presentation.label}
                                icon={statusIcon(presentation)}
                                activity={seat.activity}
                              />
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
                      stale={
                        !!reviews.error || reviews.connection === "disconnected"
                      }
                      close={() => closeInDrawer(closeReview)}
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
                      close={() => closeInDrawer(closeDetails)}
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
                          <WorkspaceIcon name="review" />
                          Teacher reviews
                        </h2>
                        <span
                          className={
                            queue.length
                              ? "attention-count has-items"
                              : "attention-count"
                          }
                        >
                          {typeof reviewCount === "number"
                            ? `${reviewCount} pending`
                            : "Not connected"}
                        </span>
                      </header>
                      {!reviewsEnabled || configurationError ? (
                        <div className="queue-empty">
                          <p>Teacher reviews not connected</p>
                          <span>
                            Pending reviews will appear here when the review
                            data source is available.
                          </span>
                        </div>
                      ) : (
                        <>
                          {reviews.error ||
                          reviews.connection === "disconnected" ? (
                            <div className="review-feed-notice" role="alert">
                              <p>
                                {reviews.error ??
                                  "Live review updates are disconnected."}
                              </p>
                              {reviews.reviews ? (
                                <p>
                                  Showing the last loaded reviews. Resolved
                                  items may still appear.
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
                              {reviewGroups.map((group) => {
                                const lead = group.reviews[0];
                                const tasks = new Set(
                                  group.reviews.map(
                                    (review) => review.activity_id,
                                  ),
                                );
                                return (
                                  <li key={group.seat_id}>
                                    <button
                                      type="button"
                                      className="review-entry"
                                      id={`review-${lead.id}`}
                                      onClick={(event) => {
                                        detailOpener.current =
                                          event.currentTarget;
                                        setSelectedId(null);
                                        setSelectedReviewId(lead.id);
                                      }}
                                    >
                                      <ReviewRowContent
                                        name={reviewName(group.seat_id)}
                                        meta={`${
                                          tasks.size > 1
                                            ? `${tasks.size} tasks`
                                            : reviewActivity(lead.activity_id)
                                        }${
                                          group.reviews.length > 1
                                            ? ` · ${group.reviews.length} reviews`
                                            : ""
                                        }`}
                                        time={group.latest}
                                        elevated={group.elevated}
                                      />
                                      <span className="sr-only">
                                        View review
                                      </span>
                                    </button>
                                  </li>
                                );
                              })}
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
            </div>
            {drawerOpen ? (
              <button
                type="button"
                className="room-scrim"
                aria-label="Close camera and details"
                onClick={closeDrawer}
              />
            ) : null}
          </>
        ) : (
          <>
            <div className="monitor-workspace">
              <div className="monitor-main">
                <LocalClassroomFeed activity={activity} />
                <section
                  className="seat-strip people-card"
                  aria-labelledby="seats-heading"
                >
                  <header className="strip-heading">
                    <h2 id="seats-heading">People</h2>
                  </header>
                  {!feed.snapshot ? (
                    <p className="strip-empty" role="status">
                      {feed.loading && !configurationError
                        ? "Loading observations…"
                        : "Seat observations unavailable"}
                    </p>
                  ) : inView.length === 0 ? (
                    <p className="strip-empty" role="status">
                      {cameraReporting
                        ? "No one is in view right now."
                        : "The camera is off. People appear here when the station camera sees them."}
                    </p>
                  ) : (
                    <div className="seat-items">
                      {inView.map((seat) => {
                        const presentation = observationPresentation(
                          seat.state,
                          observationOptions,
                        );
                        return (
                          <button
                            className={`seat-item is-${statusTone(presentation)} ${presentation.needsReview ? "needs-review" : ""} ${selected?.id === seat.id ? "is-selected" : ""}`}
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
                            <PersonRowContent
                              name={seat.display_name}
                              status={presentation.label}
                              icon={statusIcon(presentation)}
                              activity={seat.activity}
                            />
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
                    stale={
                      !!reviews.error || reviews.connection === "disconnected"
                    }
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
                        <WorkspaceIcon name="review" />
                        Teacher reviews
                      </h2>
                      <span
                        className={
                          queue.length
                            ? "attention-count has-items"
                            : "attention-count"
                        }
                      >
                        {typeof reviewCount === "number"
                          ? `${reviewCount} pending`
                          : "Not connected"}
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
                        {reviews.error ||
                        reviews.connection === "disconnected" ? (
                          <div className="review-feed-notice" role="alert">
                            <p>
                              {reviews.error ??
                                "Live review updates are disconnected."}
                            </p>
                            {reviews.reviews ? (
                              <p>
                                Showing the last loaded reviews. Resolved items
                                may still appear.
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
                            {reviewGroups.map((group) => {
                              const lead = group.reviews[0];
                              const tasks = new Set(
                                group.reviews.map(
                                  (review) => review.activity_id,
                                ),
                              );
                              return (
                                <li key={group.seat_id}>
                                  <button
                                    type="button"
                                    className="review-entry"
                                    id={`review-${lead.id}`}
                                    onClick={() => {
                                      setSelectedId(null);
                                      setSelectedReviewId(lead.id);
                                    }}
                                  >
                                    <ReviewRowContent
                                      name={reviewName(group.seat_id)}
                                      meta={`${
                                        tasks.size > 1
                                          ? `${tasks.size} tasks`
                                          : reviewActivity(lead.activity_id)
                                      }${
                                        group.reviews.length > 1
                                          ? ` · ${group.reviews.length} reviews`
                                          : ""
                                      }`}
                                      time={group.latest}
                                      elevated={group.elevated}
                                    />
                                    <span className="sr-only">View review</span>
                                  </button>
                                </li>
                              );
                            })}
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
          </>
        )}
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
